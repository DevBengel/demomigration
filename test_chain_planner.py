import json
import tempfile
import unittest
from pathlib import Path
from chain_planner import build_chains


def plan(pilot='9872', partition='PT-A', count=3):
    return {'source': {'huntPilot': pilot, 'partition': partition,
        'orderedStages': [{'huntList':'HL', 'lineGroup':f'LG-{i}', 'order':i,
            'algorithm':'Top Down', 'members':[{'extension':str(6000+i),'partition':'PT-A'}],
            'rawLineGroup':{'huntOptionNoAnswer':'Try next group in Hunt List'}}
            for i in range(count)],
        'forwardSettings': {'forwardHuntNoAnswer':'9999'},
        'huntOptions':{'huntListName':'HL'},'queueSettings':{}}}

class ChainPlannerTests(unittest.TestCase):
    def test_stable_and_ordered(self):
        with tempfile.TemporaryDirectory() as d:
            manifest=Path(d)/'alloc.json'
            first=build_chains([plan()],allocation_file=manifest)
            second=build_chains([plan()],allocation_file=manifest)
            self.assertEqual(first,second)
            names=[x['name'] for x in first[0]['huntGroups']]
            self.assertEqual(names,['HG-9872-01','HG-9872-02','HG-9872-03'])
            self.assertEqual(len(first[0]['transitions']),2)
            self.assertEqual(first[0]['originalForwardSettings']['forwardHuntNoAnswer'],'9999')
            self.assertFalse(first[0]['transitions'][0]['provisioningAllowed'])
    def test_partition_collisions(self):
        chains=build_chains([plan(partition='A'),plan(partition='B')])
        self.assertNotEqual(chains[0]['huntGroups'][0]['name'],chains[1]['huntGroups'][0]['name'])
    def test_pool_exhaustion(self):
        with self.assertRaises(ValueError):
            build_chains([plan(count=4)],start=89000,end=89001)
    def test_empty(self):
        p=plan(count=0)
        self.assertEqual(build_chains([p])[0]['status'],'BLOCKED')

if __name__=='__main__':unittest.main()


class HuntOptionPreservationTests(unittest.TestCase):
    def test_explicit_false_survives_filter(self):
        from chain_planner import _hunt_options
        from migrate import extract_settings
        raw={'autoLogOffHunt':False, 'huntAlgorithmBusy':'Try next member; then, try next group in Hunt List'}
        self.assertIn('autoLogOffHunt', extract_settings(raw))
        self.assertIs(_hunt_options(extract_settings(raw))['autoLogOffHunt'], False)
