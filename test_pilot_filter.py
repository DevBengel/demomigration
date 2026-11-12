import unittest
from pilot_filter import select

G = [{'pilot':'9872','partition':'PT-A'}, {'pilot':'9872','partition':'PT-B'},
     {'pilot':'9873','partition':'PT-A'}, {'pilot':'1234','partition':''}]

class TestSelection(unittest.TestCase):
    def test_default_requires_selection(self):
        with self.assertRaises(ValueError): select(G)
    def test_exact_and_partition(self):
        self.assertEqual(len(select(G,include=['9872'],partitions=['PT-A'])),1)
    def test_glob_and_exclusion(self):
        self.assertEqual(len(select(G,include=['98*'],exclude=['9873'])),2)
    def test_regex(self):
        self.assertEqual(len(select(G,regex=r'^1234$')),1)
    def test_all(self):
        self.assertEqual(len(select(G,all_pilots=True)),4)
    def test_conflicting_all(self):
        with self.assertRaises(ValueError): select(G,include=['98*'],all_pilots=True)

if __name__ == '__main__': unittest.main()
