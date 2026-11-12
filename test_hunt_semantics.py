import unittest
from hunt_semantics import assess, EXPECTED
class TestHuntSemantics(unittest.TestCase):
    def test_single_stage_review_not_approved(self):
        options = {k:EXPECTED for k in ('huntAlgorithmNoAnswer','huntAlgorithmBusy','huntAlgorithmNotAvailable')}
        options['autoLogOffHunt']='false'
        result=assess(options,1,{})
        self.assertEqual(result['status'],'REVIEW_REQUIRED')
        self.assertEqual(len(result['checks']),6)
    def test_boolean_false_is_not_unknown(self):
        options = {k:EXPECTED for k in ('huntAlgorithmNoAnswer','huntAlgorithmBusy','huntAlgorithmNotAvailable')}
        options['autoLogOffHunt'] = False
        result = assess(options,1,{})
        self.assertEqual(next(x for x in result['checks'] if x['check']=='autoLogOffHunt')['status'],'REVIEW')
    def test_missing_auto_logoff_blocks(self):
        self.assertEqual(next(x for x in assess({},1,{})['checks'] if x['check']=='autoLogOffHunt')['status'],'BLOCK')
    def test_multistage_block(self):
        self.assertEqual(assess({},2,{})['status'],'BLOCKED')
    def test_forwarding_block(self):
        self.assertEqual(assess({},1,{'forwardHuntNoAnswer':{'destination':'9711002'}})['status'],'BLOCKED')
