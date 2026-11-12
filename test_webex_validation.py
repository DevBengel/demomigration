import unittest
from webex_validation import compare, inspect

class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.payload={'name':'TEST','extension':'89001','enabled':False,'callPolicies':{'policy':'REGULAR'},'agents':[{'id':'A'},{'id':'B'}]}
    def test_match(self):
        self.assertEqual(compare(self.payload,self.payload)['status'],'MATCH')
    def test_wrong_order(self):
        other=dict(self.payload,agents=[{'id':'B'},{'id':'A'}])
        self.assertEqual(compare(self.payload,other)['status'],'REVIEW_REQUIRED')
    def test_missing_enabled(self):
        other=dict(self.payload);other.pop('enabled')
        self.assertEqual(compare(self.payload,other)['status'],'REVIEW_REQUIRED')
    def test_read_only(self):
        class Fake:
            def hunt_group_details(self,location,id):
                assert location=='LOC' and id=='ID'
                return self.payload
        fake=Fake();fake.payload=self.payload
        plan={'objects':[{'name':'TEST','locationId':'LOC','payload':self.payload,'status':'BLOCKED','reasons':['RNA']} ]}
        result=inspect(fake,plan,'TEST','ID')
        self.assertFalse(result['provisioningPerformed'])
        self.assertEqual(result['comparison']['status'],'MATCH')
        self.assertEqual(result['planStatus'],'BLOCKED')
    def test_unknown_name_fails(self):
        with self.assertRaises(ValueError): inspect(None,{'objects':[]},'TEST','ID')
if __name__=='__main__': unittest.main()
