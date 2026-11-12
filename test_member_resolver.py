import unittest
from member_resolver import resolve_members

class Client:
    def calling_people(self, location_id=None, org_id=None):
        return [{'id':'p1','extension':'6016','displayName':'One','locationId':'loc'}, {'id':'p2','extension':'6017','locationId':'loc'}]
    def calling_workspaces(self, location_id=None, org_id=None):
        return [{'id':'w1','extension':'6017','locationId':'loc'}]

class Broken(Client):
    def calling_workspaces(self, location_id=None, org_id=None):
        raise RuntimeError('403')

class Tests(unittest.TestCase):
    def run_case(self, client, extensions, lid='loc'):
        chains=[{'sourceKey':'a','huntGroups':[{'name':'HG-9872-01','members':[{'extension':x} for x in extensions]}]}]
        result=resolve_members(chains,client,{'resolutions':[{'sourceKey':'a','locationId':lid}]})
        return result,chains
    def test_unique(self):
        r,c=self.run_case(Client(),['6016'])
        self.assertEqual(r['resolvedGroups'],1)
        self.assertEqual(c[0]['huntGroups'][0]['resolvedMembers'][0]['id'],'p1')
    def test_ambiguous(self):
        r,c=self.run_case(Client(),['6017'])
        self.assertEqual(r['reports'][0]['members'][0]['status'],'AMBIGUOUS')
    def test_missing(self):
        r,c=self.run_case(Client(),['9999'])
        self.assertEqual(r['reports'][0]['members'][0]['status'],'MISSING')
    def test_location(self):
        r,c=self.run_case(Client(),['6016'],None)
        self.assertEqual(r['reports'][0]['members'][0]['status'],'LOCATION_UNRESOLVED')
    def test_partial_inventory(self):
        r,c=self.run_case(Broken(),['6016'])
        self.assertEqual(r['reports'][0]['members'][0]['status'],'INVENTORY_INCOMPLETE')

if __name__=='__main__': unittest.main()

class DirectoryRequestTests(unittest.TestCase):
    def test_directory_requests_do_not_send_org_id(self):
        from webex_client import WebexClient
        class Stub(WebexClient):
            def __init__(self): pass
            def list(self, path, params=None, key=None):
                self.calls.append((path, params, key)); return []
        c=Stub();c.calls=[]
        c.calling_people(location_id='loc',org_id='bad-uuid')
        c.calling_workspaces(location_id='loc',org_id='bad-uuid')
        self.assertEqual(c.calls[0],('/people',{'callingData':'true','max':100},'items'))
        self.assertEqual(c.calls[1],('/workspaces',None,'items'))

class StaleCallingIdentityTests(unittest.TestCase):
    class Stale(Client):
        def calling_people(self, **kwargs):
            return super().calling_people(**kwargs) + [{'id': 'stale', 'displayName': 'Deleted'}]
        def calling_person_details(self, person_id):
            raise RuntimeError('Webex API HTTP 404: {"message":"User not found."}')

    class Uncertain(Stale):
        def calling_person_details(self, person_id):
            raise RuntimeError('Webex API HTTP 403: scope missing')

    def test_stale_calling_user_does_not_block_verified_match(self):
        result, _ = Tests().run_case(self.Stale(), ['6016'])
        self.assertEqual(result['resolvedGroups'], 1)
        self.assertEqual(result['reports'][0]['inventoryErrors'], [])
        self.assertEqual(result['reports'][0]['inventoryWarnings'][0]['reason'], 'STALE_DIRECTORY_IDENTITY')

    def test_other_api_failure_still_blocks(self):
        result, _ = Tests().run_case(self.Uncertain(), ['6016'])
        self.assertEqual(result['resolvedGroups'], 0)
        self.assertEqual(result['reports'][0]['members'][0]['status'], 'INVENTORY_INCOMPLETE')

    def test_missing_stays_missing_with_stale_user(self):
        result, _ = Tests().run_case(self.Stale(), ['9999'])
        self.assertEqual(result['reports'][0]['members'][0]['status'], 'MISSING')
