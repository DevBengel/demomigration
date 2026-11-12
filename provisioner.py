"""Fail-closed Hunt Group creation. Never silently convert CUCM queueing or stages."""
import json
import re
from pathlib import Path
from rna_mapping import assess

ALGORITHMS = {'Longest Idle Time': 'UNIFORM', 'Top Down': 'REGULAR',
              'Circular': 'CIRCULAR', 'Broadcast': 'SIMULTANEOUS'}

def _configured_forwarding(settings):
    for item in (settings or {}).values():
        if isinstance(item, dict):
            if item.get('destination') or str(item.get('usePersonalPreferences', '')).lower() == 'true':
                return True
        elif item:
            return True
    return False

def prepare(chains, location_report, member_report, plans, existing, numbers, calibration=None):
    locations = {r['sourceKey']: r for r in location_report['resolutions']}
    member_rows = {(r['sourceKey'], r['huntGroup']): r for r in member_report['reports']}
    sources = {json.dumps([p['source']['huntPilot'],p['source']['partition']],separators=(',',':')):p['source'] for p in plans}
    occupied = {(str(x.get('locationId') or ''),str(x.get('extension') or '')) for x in numbers if x.get('extension')}
    # The number inventory is not guaranteed to contain every reservation: API may reject POST.
    result = []
    for chain in chains:
        loc = locations.get(chain['sourceKey'], {})
        source = sources.get(chain['sourceKey'], {})
        for group in chain['huntGroups']:
            reasons = []
            lid = loc.get('locationId')
            if not lid or loc.get('status') != 'RESOLVED': reasons.append('LOCATION_UNRESOLVED')
            row = member_rows.get((chain['sourceKey'],group['name']), {})
            if row.get('status') != 'RESOLVED': reasons.append('MEMBERS_UNRESOLVED')
            if len(chain['huntGroups']) != 1: reasons.append('MULTISTAGE_ROUTING_NOT_SUPPORTED')
            if source.get('rawHuntPilot', {}).get('queueCalls') or chain.get('originalQueueSettings'):
                reasons.append('CUCM_QUEUE_CONFIGURATION_REQUIRES_REVIEW')
            if _configured_forwarding(chain.get('originalForwardSettings')):
                reasons.append('CUCM_FORWARDING_NOT_MAPPED')
            options = group.get('huntOptions') or {}
            timing = assess(options.get('rnaReversionTimeOut'), calibration)
            if timing['status'] != 'NOT_CONFIGURED':
                reasons.append('CUCM_RNA_WEBEX_MAPPING_NOT_API_VALIDATED')
            for key in ('huntAlgorithmNoAnswer','huntAlgorithmBusy','huntAlgorithmNotAvailable'):
                if options.get(key): reasons.append('CUCM_HUNT_OPTION_REQUIRES_SEMANTIC_REVIEW')
            policy = ALGORITHMS.get(group.get('distributionAlgorithm'))
            if not policy: reasons.append('UNSUPPORTED_DISTRIBUTION_ALGORITHM')
            ext = str(group.get('extension') or '')
            if not re.fullmatch(r'\d{2,10}', ext): reasons.append('INVALID_EXTENSION')
            if (lid,ext) in occupied: reasons.append('EXTENSION_IN_NUMBER_INVENTORY')
            for existing_group in existing.get(lid, []):
                if str(existing_group.get('name','')).casefold() == group['name'].casefold(): reasons.append('NAME_EXISTS')
                if str(existing_group.get('extension') or '') == ext: reasons.append('EXTENSION_IN_HUNT_GROUP')
            candidates = [m['candidates'][0] for m in row.get('members', []) if m.get('status')=='RESOLVED' and len(m.get('candidates',[]))==1]
            if len(candidates) != len(group.get('members',[])) or not candidates: reasons.append('AGENT_LIST_INCOMPLETE')
            if any(m['type'] not in ('PEOPLE','WORKSPACE') for m in candidates): reasons.append('UNSUPPORTED_AGENT_TYPE')
            payload = {'name':group['name'],'extension':ext,'enabled':False,
                       'callPolicies':{'policy':policy},
                       'agents':[{'id':m['id']} for m in candidates]} if policy and candidates else None
            result.append({'sourceKey':chain['sourceKey'],'name':group['name'],'locationId':lid,
                           'status':'BLOCKED' if reasons else 'READY', 'reasons':sorted(set(reasons)),
                           'payload':payload,'rnaTiming':timing})
    return {'schemaVersion':1,'mode':'CREATE_DISABLED_ONLY','objects':result}

def apply_one(client, plan, confirmation, output):
    ready = [x for x in plan['objects'] if x['status']=='READY']
    if len(plan['objects']) != 1 or len(ready) != 1:
        raise ValueError('Apply requires exactly ONE ready Hunt Group; filter to one single-stage pilot')
    item = ready[0]
    if confirmation != item['name']:
        raise ValueError('Explicit --confirm-create must match '+item['name'])
    location = item['locationId']
    # Check immediately before POST to avoid predictable duplicates.
    if any(g.get('name','').casefold()==item['name'].casefold() or str(g.get('extension'))==item['payload']['extension'] for g in client.hunt_groups(location)):
        raise ValueError('Hunt Group name/extension already exists; no POST performed')
    journal = Path(output)/'apply-result.json'
    journal.write_text(json.dumps({'status':'ATTEMPTING_CREATE','name':item['name'],'locationId':location},indent=2),encoding='utf-8')
    try:
        created = client.create_hunt_group(location, item['payload'])
        new_id = created.get('id')
        if not new_id:
            matches = [g for g in client.hunt_groups(location) if g.get('name')==item['name']]
            if len(matches)!=1: raise RuntimeError('POST returned without ID; inspect Control Hub before retrying')
            new_id = matches[0]['id']
        detail = client.hunt_group_details(location,new_id)
        if detail.get('name') != item['name'] or str(detail.get('extension')) != item['payload']['extension']:
            raise RuntimeError('Created but readback mismatch; manual verification required')
        result = {'status':'CREATED_DISABLED','id':new_id,'name':item['name'],'locationId':location,
                  'readback':detail}
        journal.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
        return result
    except Exception as exc:
        journal.write_text(json.dumps({'status':'UNKNOWN_CHECK_WEBEX_BEFORE_RETRY','name':item['name'],
                                      'error':str(exc)[:500]},indent=2),encoding='utf-8')
        raise
