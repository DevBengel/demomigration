"""Read-only Webex Hunt Group API validation, with fail-closed comparisons."""
import argparse
import json
from pathlib import Path
from webex_client import WebexClient, acquire_token


def compare(expected, actual):
    checks = []
    for key in ('name', 'extension', 'enabled'):
        want = expected.get(key)
        got = actual.get(key)
        checks.append({'field': key, 'expected': want, 'actual': got,
                       'status': 'MATCH' if type(want) is type(got) and want == got else 'MISMATCH'})
    policy = (expected.get('callPolicies') or {}).get('policy')
    actual_policy = (actual.get('callPolicies') or {}).get('policy')
    checks.append({'field':'callPolicies.policy','expected':policy,'actual':actual_policy,
                   'status':'MATCH' if policy and policy == actual_policy else 'MISMATCH'})
    want_agents = [a.get('id') for a in expected.get('agents', [])]
    got_agents = [a.get('id') for a in actual.get('agents', [])]
    checks.append({'field':'agents.order','expected':want_agents,'actual':got_agents,
                   'status':'MATCH' if want_agents and want_agents == got_agents else 'MISMATCH'})
    return {'status':'MATCH' if all(c['status']=='MATCH' for c in checks) else 'REVIEW_REQUIRED',
            'checks':checks,'behaviorValidated':False,'rnaValidated':False}


def inspect(client, plan, name, group_id):
    items = [x for x in plan.get('objects',[]) if x.get('name') == name]
    if len(items) != 1:
        raise ValueError('Exactly one matching planned Hunt Group required')
    item = items[0]
    if not item.get('locationId') or not item.get('payload'):
        raise ValueError('Planned group lacks location or payload')
    # Explicitly never write; this can inspect a separately created test object.
    detail = client.hunt_group_details(item['locationId'],group_id)
    result = compare(item['payload'],detail)
    return {'schemaVersion':1,'mode':'READ_ONLY_EXISTING_TEST_GROUP',
            'plannedName':name,'inspectedGroupId':group_id,'locationId':item['locationId'],
            'planStatus':item['status'],'planReasons':item.get('reasons',[]),
            'comparison':result,'provisioningPerformed':False,
            'note':'API readback does not prove call routing semantics or RNA timing.'}


def main():
    parser=argparse.ArgumentParser(description='Read-only Webex Hunt Group readback validation')
    parser.add_argument('--plan',required=True)
    parser.add_argument('--name',required=True)
    parser.add_argument('--existing-test-id',required=True,help='ID of a separately created test Hunt Group')
    parser.add_argument('--out',default='webex-test-readback.json')
    args=parser.parse_args()
    plan=json.loads(Path(args.plan).read_text(encoding='utf-8-sig'))
    result=inspect(WebexClient(acquire_token()),plan,args.name,args.existing_test_id)
    Path(args.out).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Webex readback: '+result['comparison']['status']+'; NO CHANGES MADE; '+args.out)

if __name__=='__main__':
    main()
