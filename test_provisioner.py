import unittest
from provisioner import prepare, apply_one

class ProvisionTests(unittest.TestCase):
    def fixtures(self):
        chains=[{'sourceKey':'["1234",""]','huntGroups':[{'name':'HG-1234-01','extension':'1234','distributionAlgorithm':'Longest Idle Time','members':[{'extension':'6001'}],'huntOptions':{}}],'originalForwardSettings':{}}]
        locations={'resolutions':[{'sourceKey':'["1234",""]','locationId':'LOC','status':'RESOLVED'}]}
        members={'reports':[{'sourceKey':'["1234",""]','huntGroup':'HG-1234-01','status':'RESOLVED','members':[{'status':'RESOLVED','candidates':[{'id':'P1','type':'PEOPLE'}]}]}]}
        plans=[{'source':{'huntPilot':'1234','partition':'','rawHuntPilot':{}}}]
        return chains,locations,members,plans
    def test_ready_disabled(self):
        x=prepare(*self.fixtures(),{'LOC':[]},[] )['objects'][0]
        self.assertEqual(x['status'],'READY')
        self.assertFalse(x['payload']['enabled'])
        self.assertEqual(x['payload']['callPolicies']['policy'],'UNIFORM')
    def test_queue_blocks(self):
        f=self.fixtures(); f[3][0]['source']['rawHuntPilot']['queueCalls']={'maxCallersInQueue':32}
        self.assertEqual(prepare(*f,{'LOC':[]},[])['objects'][0]['status'],'BLOCKED')
    def test_multistage_blocks(self):
        f=self.fixtures();f[0][0]['huntGroups'].append(dict(f[0][0]['huntGroups'][0],name='HG-1234-02'))
        self.assertEqual(prepare(*f,{'LOC':[]},[])['objects'][0]['status'],'BLOCKED')
    def test_existing_blocks(self):
        self.assertEqual(prepare(*self.fixtures(),{'LOC':[{'name':'HG-1234-01'}]},[])['objects'][0]['status'],'BLOCKED')
    def test_confirm_required(self):
        class C: pass
        with self.assertRaises(ValueError): apply_one(C(),prepare(*self.fixtures(),{'LOC':[]},[]),'WRONG','.')
if __name__=='__main__':unittest.main()
