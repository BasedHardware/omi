import unittest
from check_mobile_perf_budgets import violations


class BudgetRatchetTests(unittest.TestCase):
    def test_bootstrap_new_count_budgets_and_measured_tightening(self):
        self.assertEqual(violations({}, {'_gate': {'home': 10}}), [])
        self.assertEqual(violations({'_gate': {'home': 10}}, {'_gate': {'home': 9}}), [])

    def test_increase_or_removal_fails(self):
        before = {'_gate': {'home': {'semantics': 0, 'rebuilds': 12}}}
        self.assertTrue(violations(before, {'_gate': {'home': {'semantics': 1, 'rebuilds': 12}}}))
        self.assertTrue(violations(before, {'_gate': {'home': {'semantics': 0}}}))

    def test_empty_or_nonfinite_caps_fail(self):
        self.assertTrue(violations({}, {'_gate': {}}))
        for value in (float('nan'), float('inf'), -1, True, 'unlimited'):
            with self.assertRaises(ValueError):
                violations({}, {'_gate': {'home': value}})


if __name__ == '__main__':
    unittest.main()
