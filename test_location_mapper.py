import unittest
from location_mapper import resolve_locations, MappingError

LOC = [{'id':'ffm','name':'Frankfurt'}, {'id':'ham','name':'Hamburg'}]
CHAINS = [{'sourceKey':'A','huntGroups':[{'name':'HG-9872-01','extension':'9872','members':[]}, {'name':'HG-9872-02','extension':'89000','members':[]}]}, {'sourceKey':'B','huntGroups':[{'name':'HG-7310-01','extension':'7310','members':[]}]}]

class LocationTests(unittest.TestCase):
    def test_longest_prefix(self):
        r=resolve_locations(CHAINS, LOC, mode='prefix', mapping={'9':'ham','98':'ffm','73':'ham'})
        self.assertEqual([x['locationId'] for x in r['resolutions']], ['ffm','ham'])
        self.assertEqual(len(r['resolutions'][0]['huntGroups']),2)
    def test_missing_prefix_review(self):
        r=resolve_locations(CHAINS, LOC, mode='prefix', mapping={'98':'ffm'})
        self.assertEqual(r['reviewRequired'],1)
    def test_auto_ambiguous(self):
        r=resolve_locations(CHAINS[:1], LOC, mode='auto', numbers=[{'extension':'9872','locationId':'ffm'},{'extension':'9872','locationId':'ham'}])
        self.assertEqual(r['reviewRequired'],1)
    def test_auto_inventory(self):
        r=resolve_locations(CHAINS[:1], LOC, mode='auto', numbers=[{'extension':'9872','locationId':'ffm'}])
        self.assertEqual(r['resolutions'][0]['locationId'],'ffm')
    def test_fixed_invalid(self):
        with self.assertRaises(MappingError): resolve_locations(CHAINS,LOC,mode='fixed',default_location='unknown')

if __name__=='__main__': unittest.main()
