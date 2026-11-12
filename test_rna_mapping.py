import unittest
from rna_mapping import assess

class TestRna(unittest.TestCase):
    def test_unmeasured(self):
        r=assess(20)
        self.assertEqual(r['status'],'MEASUREMENT_REQUIRED')
        self.assertIsNone(r['webexRings'])
    def test_measured(self):
        r=assess(20,{'measuredSecondsPerRing':5,'measurementNotes':'Four live test calls'})
        self.assertEqual(r['webexRings'],4)
        self.assertEqual(r['estimatedDeviationSeconds'],0)
    def test_10_seconds(self):
        self.assertEqual(assess(10,{'measuredSecondsPerRing':4,'measurementNotes':'tested'})['webexRings'],3)
    def test_invalid(self):
        self.assertEqual(assess(-1)['status'],'INVALID_CUCM_TIMEOUT')
if __name__=='__main__': unittest.main()
