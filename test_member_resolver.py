import unittest
from member_resolver import resolve_members

class Client:
    def calling_people(self, location_id=None, org_id=None):
        return [{'id':'p1','extension':'6016','displayName':'One'}, {'id':'p2','extension':'6017'}]
    def calling_workspaces(self, location_id=None, org_id=None):
        return [{'id':'w1','extension':'6017'}]

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
