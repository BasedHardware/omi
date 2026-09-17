#!/usr/bin/env python3
import unittest
from check_mobile_boundaries import counts, violations

RULES = [{'id': 'wake', 'pattern': r'\.\s*instance\s*\.\s*wake\s*\(', 'paths': ['app/lib/'],
          'remedy': 'Inject CaptureRecoveryRequests; see capture/OWNERSHIP.md'}]


class BoundaryTests(unittest.TestCase):
    def test_comments_strings_whitespace_and_new_paths(self):
        text = 'x . instance\n .wake(a); // x.instance.wake()\n"x.instance.wake()"'
        self.assertEqual(counts(text, RULES, 'app/lib/new.dart'), {'wake': 1})
        self.assertEqual(counts(text, RULES, 'unrelated.dart'), {})
        self.assertTrue(violations('app/lib/new.dart', text, None, RULES, {}))

    def test_baseline_is_not_permission_to_reintroduce_removed_debt(self):
        self.assertTrue(violations('app/lib/a.dart', 'x.instance.wake()', '', RULES, {'wake': 10}))
        self.assertFalse(violations('app/lib/a.dart', '', 'x.instance.wake()', RULES, {'wake': 1}))
        self.assertFalse(violations('app/lib/a.dart', 'x.instance.wake()', 'x.instance.wake()', RULES, {'wake': 1}))

    def test_new_alias_spelling_and_comment_boundary(self):
        self.assertEqual(counts('x /*comment*/ .instance.wake();', RULES, 'app/lib/a.dart')['wake'], 1)
        errors = violations('app/lib/a.dart', 'x.instance.wake()', '', RULES, {})
        self.assertIn('CaptureRecoveryRequests', errors[0])


if __name__ == '__main__':
    unittest.main()
