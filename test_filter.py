import unittest
from migrate import pilot_matches,parse_prefixes,filter_graph,axl_to_graph
from unittest.mock import patch

class FilterTests(unittest.TestCase):
    def test_literal(self):
        self.assertTrue(pilot_matches('9872',('98',)))
        self.assertFalse(pilot_matches('19872',('98',)))
        self.assertFalse(pilot_matches('9872',('98',),('987',)))
        self.assertTrue(pilot_matches('9872'))
    def test_parse(self):
        self.assertEqual(parse_prefixes(' 98,99,98, '),('98','99'))
    def test_graph(self):
        graph=[{'pilot':'9872'},{'pilot':'8812'}]
        self.assertEqual(filter_graph(graph,('98',)),graph[:1])
    def test_axl_filters_before_detail(self):
        class Service:
            def __init__(self):self.detail=[]
            def listHuntPilot(self,**kw):return {'return':{'huntPilot':[{'pattern':'9872'},{'pattern':'8812'}]}}
            def getHuntPilot(self,**kw):
                self.detail.append(kw)
                return {'return':{'huntPilot':{}}}
        s=Service()
        with patch('migrate.normalize_axl', side_effect=lambda x:x):
            result=axl_to_graph(s,('98',))
        self.assertEqual(len(result),1)
        self.assertEqual(len(s.detail),1)

if __name__=='__main__':unittest.main()
