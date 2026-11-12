#!/usr/bin/env python3
"""CUCM BAT or read-only AXL -> loss-aware Webex Calling migration assessment."""
import argparse, csv, io, json, os, re, tarfile
from collections import defaultdict
from pathlib import Path
from chain_planner import build_chains
from webex_client import WebexClient, WebexError, acquire_token, preflight
from member_resolver import resolve_members
from provisioner import prepare, apply_one
from rna_mapping import load_calibration
from location_mapper import resolve_locations, load_mapping, MappingError


def load_env(path):
    if not path.exists(): return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1); k=k.strip();v=v.strip().strip('"').strip("'")
        os.environ.setdefault(k,v)

def clean(v):
    if isinstance(v,dict): return clean(v.get('_value_1') or v.get('name') or v.get('pattern') or v.get('uuid'))
    if isinstance(v,list): return ','.join(map(clean,v))
    v=str(v if v is not None else '').strip()
    return '' if v.upper() in ('NULL','NONE') else v

def read_csvs(path):
    result={}
    if path.is_dir(): sources=[(p.name,p.read_bytes()) for p in path.glob('*.csv')]
    else:
        with tarfile.open(path,'r:*') as tf:
            sources=[(Path(m.name).name,tf.extractfile(m).read()) for m in tf.getmembers() if m.isfile() and m.name.lower().endswith('.csv') and Path(m.name).name==m.name]
    for name,raw in sources:
        try: content=raw.decode('utf-8-sig')
        except UnicodeDecodeError: content=raw.decode('cp1252')
        result[name.lower()]=list(csv.DictReader(io.StringIO(content)))
    return result

def indexed(row,field,order_prefix):
    out=[]
    for k,v in row.items():
        m=re.fullmatch(re.escape(field)+r'\s*(\d+)',k.strip(),re.I)
        if not m or not clean(v): continue
        idx=int(m.group(1)); order=clean(row.get(f'{order_prefix} {idx}'))
        # CUCM BAT selection order 0 is a valid position; never silently drop it.
        seq=int(order) if re.fullmatch(r'\d+',order) else idx
        out.append((seq,idx,clean(v)))
    return sorted(out)

def bat_to_graph(data):
    lists={clean(r.get('NAME')):r for r in data.get('huntlist.csv',[])}
    groups={clean(r.get('NAME')):r for r in data.get('linegroup.csv',[])}
    graph=[]
    for hp in data.get('huntpilot.csv',[]):
        hls=[]
        for _,_,hn in indexed(hp,'HUNT LIST','SELECTION ORDER'):
            hl=lists.get(hn); lgitems=[]
            if hl:
                for seq,_,gn in indexed(hl,'LINE GROUP','SELECTION ORDER'):
                    lg=groups.get(gn); mem=[]
                    if lg:
                        for order,idx,dn in indexed(lg,'DN OR PATTERN','LINE SELECTION ORDER'):
                            mem.append({'extension':dn,'partition':clean(lg.get(f'ROUTE PARTITION {idx}')),'selectionOrder':order})
                    lgitems.append({'name':gn,'order':seq,'found':bool(lg),'settings':lg or {},'members':mem})
            hls.append({'name':hn,'found':bool(hl),'settings':hl or {},'lineGroups':lgitems})
        graph.append({'pilot':clean(hp.get('HUNT PILOT')),'partition':clean(hp.get('ROUTE PARTITION')),'settings':hp,'huntLists':hls})
    return graph

def normalize_axl(value):
    """Convert Zeep objects into plain nested JSON-compatible structures."""
    from zeep.helpers import serialize_object
    return serialize_object(value, target_cls=dict)

def seq(value):
    if value is None:return []
    if isinstance(value,list):return value
    if isinstance(value,dict):
        for k in ('member','lineGroup','huntList','huntListMember','lineGroupMember','members','lineGroups','huntLists'):
            if k in value:return seq(value[k])
        return [value]
    return [value]

def get_nested(obj,*names):
    if not isinstance(obj,dict):return None
    for name in names:
        for k,v in obj.items():
            if k.lower()==name.lower():return v
    return None

def name_of(obj):
    if isinstance(obj,str):return obj
    if isinstance(obj,dict):
        for key in ('name','lineGroupName','huntListName','_value_1','pattern','uuid'):
            v=get_nested(obj,key)
            if v:return clean(v)
    return clean(obj)

def pilot_matches(pattern, prefixes=(), excludes=()):
    """Literal, case-sensitive line-prefix matching; never interpret as regex."""
    pattern = str(pattern).strip()
    return (not prefixes or any(pattern.startswith(p) for p in prefixes)) and not any(
        pattern.startswith(p) for p in excludes)


def parse_prefixes(value):
    return tuple(dict.fromkeys(p.strip() for p in str(value or '').split(',') if p.strip()))


def filter_graph(graph, prefixes=(), excludes=()):
    return [item for item in graph if pilot_matches(item['pilot'], prefixes, excludes)]


def axl_to_graph(service, prefixes=(), excludes=()):
    """Uses supported AXL list/get operations, no executeSQLQuery and no writes."""
    results=[]
    response=normalize_axl(service.listHuntPilot(searchCriteria={'pattern':'%'},returnedTags={'pattern':'','routePartitionName':''}))
    listings=seq(get_nested(get_nested(response,'return') or response,'huntPilot'))
    cache_hl={};cache_lg={}
    for item in listings:
        pattern=clean(get_nested(item,'pattern'));partition=name_of(get_nested(item,'routePartitionName'))
        if not pattern or not pilot_matches(pattern, prefixes, excludes):continue
        # UUID avoids ambiguous patterns across partitions when available.
        uid=get_nested(item,'uuid')
        kwargs={'uuid':uid} if uid else {'pattern':pattern,'routePartitionName':partition or None}
        hp=normalize_axl(service.getHuntPilot(**kwargs))
        hp=get_nested(get_nested(hp,'return') or hp,'huntPilot') or hp
        hls=[]
        for hidx,href in enumerate(seq(get_nested(hp,'huntListName','huntLists','huntList'))):
            hn=name_of(href)
            if not hn:continue
            if hn not in cache_hl:
                raw=normalize_axl(service.getHuntList(name=hn))
                cache_hl[hn]=get_nested(get_nested(raw,'return') or raw,'huntList') or raw
            hl=cache_hl[hn]; lgs=[]
            for i,lr in enumerate(seq(get_nested(hl,'members','lineGroups','lineGroupMembers'))):
                gn=name_of(get_nested(lr,'lineGroupName','lineGroup') or lr)
                if not gn:continue
                if gn not in cache_lg:
                    raw=normalize_axl(service.getLineGroup(name=gn))
                    cache_lg[gn]=get_nested(get_nested(raw,'return') or raw,'lineGroup') or raw
                lg=cache_lg[gn];members=[]
                for j,m in enumerate(seq(get_nested(lg,'members','lineGroupMembers'))):
                    dn=name_of(get_nested(m,'directoryNumber','dnOrPattern','pattern') or m)
                    pt=name_of(get_nested(m,'routePartitionName','partition'))
                    if dn:members.append({'extension':dn,'partition':pt,'selectionOrder':get_nested(m,'selectionOrder','index') if isinstance(m,dict) else j})
                lgs.append({'name':gn,'order':get_nested(lr,'selectionOrder','index') if isinstance(lr,dict) else i,'found':True,'settings':lg,'members':members})
            hls.append({'name':hn,'found':True,'settings':hl,'lineGroups':lgs})
        results.append({'pilot':pattern,'partition':partition,'settings':hp,'huntLists':hls})
    return results

def read_axl(prefixes=(), excludes=()):
    try:
        from zeep import Client,Settings
        from zeep.transports import Transport
        from requests import Session
        from requests.auth import HTTPBasicAuth
    except ImportError as e:raise SystemExit('AXL benötigt: pip install -r requirements.txt') from e
    host=os.getenv('CUCM_HOST','198.18.133.33');version=os.getenv('CUCM_AXL_VERSION','14.0')
    wsdl=os.getenv('CUCM_AXL_WSDL','').strip()
    if not wsdl:raise SystemExit('CUCM_AXL_WSDL muss auf eine lokale AXLAPI.wsdl der CUCM-Version zeigen.')
    if not Path(wsdl).is_file():raise SystemExit('AXL WSDL nicht gefunden: '+wsdl)
    username=os.getenv('CUCM_USERNAME');password=os.getenv('CUCM_PASSWORD')
    if not username or not password:raise SystemExit('CUCM_USERNAME und CUCM_PASSWORD in .env setzen')
    session=Session();session.auth=HTTPBasicAuth(username,password)
    verify=os.getenv('CUCM_VERIFY_TLS','true').lower() in ('1','yes','true','on')
    session.verify=os.getenv('CUCM_CA_BUNDLE') if verify and os.getenv('CUCM_CA_BUNDLE') else verify
    client=Client(wsdl,transport=Transport(session=session,timeout=int(os.getenv('CUCM_TIMEOUT','30'))),settings=Settings(strict=True,xml_huge_tree=False))
    binding=os.getenv('CUCM_AXL_BINDING','{http://www.cisco.com/AXLAPIService/}AXLAPIBinding')
    service=client.create_service(binding,f'https://{host}:8443/axl/')
    return axl_to_graph(service, prefixes, excludes)

def extract_settings(settings):
    # Keep the full source as well; flatten only for review, not as authoritative API mapping.
    if not isinstance(settings,dict):return {}
    return {str(k):v for k,v in settings.items() if any(t in k.lower().replace(' ','') for t in ('forward','hunt','queue','overflow','rna','busy','down','distribution','algorithm','timer','timeout','maxwait','maxnumber','logout','logoff','enabled','routepartition','css','presentation','mask','moh','announcement','selection'))}

def migrate(graph):
    plans=[]
    for item in graph:
        warnings=[]; stages=[]; unique=[]; seen=set()
        for hl in item['huntLists']:
            if not hl['found']:warnings.append('Hunt List missing: '+hl['name'])
            for lg in hl['lineGroups']:
                if not lg['found']:warnings.append('Line Group missing: '+lg['name'])
                s=lg['settings'];alg=clean(s.get('TYPE DISTRIBUTION ALGORITHM') or s.get('distributionAlgorithm'))
                stage={'huntList':hl['name'],'lineGroup':lg['name'],'order':lg['order'],'algorithm':alg,'members':lg['members'],'huntOptions':extract_settings(s),'rawLineGroup':s}
                stages.append(stage)
                for m in lg['members']:
                    key=(m['extension'],m['partition'])
                    if key not in seen:unique.append(m);seen.add(key)
        hp=item['settings'];queues={k:v for k,v in hp.items() if ('QUEUE' in k.upper() or 'queue' in k) and v is not None}
        # CUCM may return queueCalls defaults even when queueing is disabled.
        # Preserve them, but never infer active queueing from mere presence.
        forward={k:v for k,v in hp.items() if 'FORWARD' in k.upper() or 'forward' in k.lower()}
        hunt={k:v for k,v in hp.items() if any(x in k.upper() for x in ('HUNT','TIMER','CALLING SEARCH SPACE','CSS'))}
        if len(stages)>1:warnings.append('Multiple ordered Line Groups: sequential fallthrough cannot be represented faithfully by flattening to one Hunt Group; architecture review required')
        algs={s['algorithm'].lower() for s in stages if s['algorithm']}
        routing={'longest idle time':'LONGEST_IDLE','circular':'CIRCULAR','broadcast':'SIMULTANEOUS','top down':'REGULAR'}.get(next(iter(algs)),'') if len(algs)==1 else ''
        if not routing:warnings.append('Mixed or unknown distribution algorithms; mapping requires review')
        if queues:warnings.append('CUCM queue fields preserved (possibly defaults); verify whether queueing is enabled before choosing Hunt Group vs Call Queue')
        if any(clean(v) for v in forward.values()):warnings.append('Forward settings require semantic validation: Busy/No Answer and CSS are not automatically equivalent to Webex forwarding')
        if any(m['partition'] for m in unique):warnings.append('Resolve partition-qualified DNs to Webex user/workspace/virtual-line IDs')
        warnings.append('Hunt options (busy/RNA/down, logout, timers) must be validated against target feature; no automatic lossless mapping')
        warnings.append('No Webex write payload generated until location, member identities, routing and forward targets are verified')
        plans.append({'source':{'huntPilot':item['pilot'],'partition':item['partition'],'huntLists':item['huntLists'],'orderedStages':stages,'forwardSettings':forward,'huntOptions':hunt,'queueSettings':queues,'rawHuntPilot':hp},'proposal':{'feature':'HUNT_GROUP_OR_CALL_QUEUE_REVIEW' if queues else 'HUNT_GROUP_REVIEW','name':'Migrated HP '+item['pilot'],'extension':item['pilot'],'routingCandidate':routing,'members':unique,'locationId':None,'memberIds':None},'warnings':list(dict.fromkeys(warnings)),'status':'REVIEW_REQUIRED'})
    return plans

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',choices=['bat','axl'],default=os.getenv('SOURCE','bat'))
    p.add_argument('archive',nargs='?',type=Path,help='BAT TAR archive or CSV folder (BAT mode)')
    p.add_argument('--env',type=Path,default=Path('.env'))
    p.add_argument('--out',type=Path,default=None)
    p.add_argument('--pilot-prefix',default=None,help='Comma-separated literal DN prefixes, e.g. 98,99; overrides .env')
    p.add_argument('--exclude-prefix',default=None,help='Comma-separated excluded DN prefixes')
    p.add_argument('--list-only',action='store_true',help='Print matching Hunt Pilots; do not write plans or allocations')
    p.add_argument('--resolve-members', action='store_true', help='Resolve Calling people/workspaces by extension; requires --webex-check')
    p.add_argument('--rna-calibration', default=None, help='JSON with measuredSecondsPerRing, validatedByTestCalls and measurementNotes; advisory only')
    p.add_argument('--apply', action='store_true', help='Create ONE validated Hunt Group, disabled, with explicit confirmation')
    p.add_argument('--confirm-create', default='', help='Exact Hunt Group name to authorize creation')
    p.add_argument('--webex-check', action='store_true', help='Connect to Webex, inspect location and target inventory (read-only)')
    p.add_argument('--location-mode', choices=['fixed','prefix','auto'], default=None, help='Override WEBEX_LOCATION_MODE')
    p.add_argument('--location-mapping', type=Path, default=None, help='JSON prefix -> Webex location ID')
    p.add_argument('--export-location-mapping', type=Path, help='Fetch Webex locations and generate editable JSON with names, IDs and prefix placeholders')
    p.add_argument('--webex-locations', action='store_true', help='List Webex locations, then exit; no CUCM access')
    args=p.parse_args();load_env(args.env)
    if args.apply and not (args.webex_check and args.resolve_members):
        p.error('--apply requires --webex-check --resolve-members')
    if args.resolve_members and not args.webex_check:
        p.error('--resolve-members requires --webex-check')
    if args.export_location_mapping:
        try:
            client = WebexClient(acquire_token())
            locations = client.locations()
            if not locations:
                raise WebexError('No locations returned; refusing to overwrite mapping')
            target = args.export_location_mapping
            if target.exists():
                raise WebexError(f'{target} already exists; refusing to overwrite manually maintained prefixes')
            payload = {'locations': [{'id': loc['id'], 'name': loc.get('name', ''), 'extensionPrefix': '__SET_PREFIX__'} for loc in sorted(locations, key=lambda x: (x.get('name') or '').casefold()) if loc.get('id')] }
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'Created {target} with {len(payload["locations"])} locations. Fill extensionPrefix values manually.')
        except Exception as exc:
            raise SystemExit(f'Location mapping export failed: {exc}') from exc
        return
    if args.webex_locations:
        try:
            client=WebexClient(acquire_token())
            print(json.dumps([{'id': l.get('id'), 'name': l.get('name')} for l in client.locations()], indent=2, ensure_ascii=False))
        except (WebexError, Exception) as exc:
            raise SystemExit(f'Webex discovery failed: {exc}') from exc
        return
    out=args.out or Path(os.getenv('OUTPUT_DIR','migration-output'))
    prefixes=parse_prefixes(args.pilot_prefix if args.pilot_prefix is not None else os.getenv('CUCM_HUNT_PILOT_PREFIXES',''))
    excludes=parse_prefixes(args.exclude_prefix if args.exclude_prefix is not None else os.getenv('CUCM_HUNT_PILOT_EXCLUDE_PREFIXES',''))
    if args.source=='axl':graph=read_axl(prefixes, excludes)
    else:
        if not args.archive:p.error('BAT mode requires an archive or CSV directory')
        graph=filter_graph(bat_to_graph(read_csvs(args.archive)), prefixes, excludes)
    print(f'Filter: include={prefixes or "ALL"}, exclude={excludes or "NONE"}; selected={len(graph)}')
    if args.list_only:
        for item in sorted(graph,key=lambda x:(x['pilot'],x['partition'])):
            print(f"{item['pilot']}  partition={item['partition'] or '<none>'}")
        return
    if not graph:
        print('No matching Hunt Pilots. No output or allocation files modified.')
        return
    plans=migrate(graph);out.mkdir(parents=True,exist_ok=True)
    chains=build_chains(plans,
        start=int(os.getenv('WEBEX_HG_EXTENSION_START','89000')),
        end=int(os.getenv('WEBEX_HG_EXTENSION_END','89999')),
        prefix=os.getenv('WEBEX_HG_PREFIX','HG'),
        allocation_file=Path(os.getenv('WEBEX_ALLOCATION_FILE', str(out/'extension-allocations.json'))))
    if args.webex_check:
        mode = args.location_mode or os.getenv('WEBEX_LOCATION_MODE', 'fixed')
        mapping_path = args.location_mapping or Path(os.getenv('WEBEX_LOCATION_MAPPING', './location-mapping.json'))
        try:
            client = WebexClient(acquire_token())
            locations = client.locations()
            mapping = load_mapping(mapping_path) if mode == 'prefix' else {}
            org_id = os.getenv('WEBEX_ORG_ID', '').strip() or None
            inventory = client.numbers(org_id) if mode == 'auto' else []
            location_report = resolve_locations(chains, locations, mode=mode, mapping=mapping,
                default_location=os.getenv('WEBEX_LOCATION_ID', '').strip(), numbers=inventory)
            (out/'location-resolution.json').write_text(json.dumps(location_report, ensure_ascii=False, indent=2), encoding='utf-8')
            if args.resolve_members:
                member_report = resolve_members(chains, client, location_report, org_id)
                (out/'member-resolution.json').write_text(json.dumps(member_report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f'Member resolution: {member_report["resolvedGroups"]} groups resolved; {member_report["reviewRequired"]} require review')
            report = preflight(chains, client, location_report, org_id)
            if args.resolve_members:
                lids = sorted({r['locationId'] for r in location_report['resolutions'] if r.get('locationId')})
                existing = {lid:client.hunt_groups(lid,org_id) for lid in lids}
                numbers = client.numbers(org_id)
                create_plan = prepare(chains,location_report,member_report,plans,existing,numbers,load_calibration(args.rna_calibration))
                (out/'webex-create-plan.json').write_text(json.dumps(create_plan,ensure_ascii=False,indent=2),encoding='utf-8')
                print('Create plan: '+str(sum(x['status']=='READY' for x in create_plan['objects']))+' ready, '+str(sum(x['status']=='BLOCKED' for x in create_plan['objects']))+' blocked')
                if args.apply:
                    result = apply_one(client,create_plan,args.confirm_create,out)
                    print('CREATED DISABLED: '+result['name']+' ID='+result['id'])
            (out/'webex-preflight.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'Location resolution: {location_report["resolved"]} resolved, {location_report["reviewRequired"]} need review')
            print(f'Webex preflight: {len(report["checks"])} objects checked; '+('APPLY REQUESTED' if args.apply else 'NO CHANGES MADE'))
        except (WebexError, MappingError) as exc:
            raise SystemExit(f'Webex preflight failed: {exc}') from exc
    (out/'webex-chain-plan.json').write_text(json.dumps({
        'schemaVersion':3,'mode':'DRY_RUN_ONLY','source':args.source,
        'webexProvisioningPerformed':False,'chains':chains
    },ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    with (out/'chain-review.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['Source Key','Stage','Webex Hunt Group','Extension','Extension Status','Next Hunt Group','Status'])
        for chain in chains:
            groups=chain['huntGroups']
            for i,g in enumerate(groups):
                w.writerow([chain['sourceKey'],g['position'],g['name'],g['extension'],g['extensionStatus'],groups[i+1]['name'] if i+1<len(groups) else '',chain['status']])
    (out/'migration-plan.json').write_text(json.dumps({'schemaVersion':2,'source':args.source,'plans':plans},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    with (out/'review.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['Hunt Pilot','Target','Line Groups (ordered)','Members','Warnings','Status'])
        for plan in plans:w.writerow([plan['source']['huntPilot'],plan['proposal']['feature'],' > '.join(s['lineGroup'] for s in plan['source']['orderedStages']),';'.join(m['extension'] for m in plan['proposal']['members']),' | '.join(plan['warnings']),plan['status']])
    print(f'{len(plans)} Hunt Pilots analyzed; reports in {out.resolve()}')

if __name__=='__main__':main()
