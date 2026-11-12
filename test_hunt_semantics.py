import unittest
from hunt_semantics import assess, EXPECTED
class TestHuntSemantics(unittest.TestCase):
    def test_single_stage_review_not_approved(self):
        options = {k:EXPECTED for k in ('huntAlgorithmNoAnswer','huntAlgorithmBusy','huntAlgorithmNotAvailable')}
        options['autoLogOffHunt']='false'
        result=assess(options,1,{})
        self.assertEqual(result['status'],'REVIEW_REQUIRED')
        self.assertEqual(len(result['checks']),6)
    def test_multistage_block(self):
        self.assertEqual(assess({},2,{})['status'],'BLOCKED')
    def test_forwarding_block(self):
        self.assertEqual(assess({},1,{'forwardHuntNoAnswer':{'destination':'9711002'}})['status'],'BLOCKED')
