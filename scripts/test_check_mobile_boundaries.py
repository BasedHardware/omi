#!/usr/bin/env python3
import json
from pathlib import Path
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
        self.assertTrue(violations('app/lib/a.dart', 'x.instance.wake()', '', RULES, {'wake': 10}, ['wake']))
        self.assertFalse(violations('app/lib/a.dart', '', 'x.instance.wake()', RULES, {'wake': 1}, ['wake']))
        self.assertFalse(violations('app/lib/a.dart', 'x.instance.wake()', 'x.instance.wake()', RULES, {'wake': 1}, ['wake']))

    def test_api_rules_detect_new_legacy_calls_and_null_swallowing(self):
        config = json.loads((Path(__file__).resolve().parents[1] /
                             'app/contracts/api-result/boundary-baseline.json').read_text())
        rules = config['rules']
        path = 'app/lib/backend/http/api/new.dart'
        source = 'await makeApiCall (url: x); try { load(); } catch (e) { return null; } x ?? [];'
        self.assertEqual(counts(source, rules, path), {'legacy-nullable-http': 1, 'null-swallow-patterns': 3})
        self.assertEqual(len(violations(path, source, None, rules, {})), 2)
        self.assertFalse(violations(path, source, '', rules, {}))  # existing legacy file
        self.assertEqual(len(violations(path, source, '', rules, {},
                                       ['legacy-nullable-http', 'null-swallow-patterns'])), 2)
        self.assertEqual(counts('// return null; makeApiCall();\n"catch (x)"', rules, path),
                         {'legacy-nullable-http': 0, 'null-swallow-patterns': 0})
        # A new caller outside today's inventory is still held to the legacy-call rule.
        self.assertTrue(violations('app/lib/new_feature.dart', 'makeApiCall()', None, rules, {}))

    def test_legacy_growth_is_allowed_until_explicit_adoption(self):
        self.assertFalse(violations('app/lib/a.dart', 'x.instance.wake(); x.instance.wake();',
                                    'x.instance.wake();', RULES, {'wake': 1}))
        self.assertTrue(violations('app/lib/a.dart', 'x.instance.wake();', '', RULES, {}, ['wake']))

    def test_new_alias_spelling_and_comment_boundary(self):
        self.assertEqual(counts('x /*comment*/ .instance.wake();', RULES, 'app/lib/a.dart')['wake'], 1)
        errors = violations('app/lib/a.dart', 'x.instance.wake()', '', RULES, {}, ['wake'])
        self.assertIn('CaptureRecoveryRequests', errors[0])


if __name__ == '__main__':
    unittest.main()
