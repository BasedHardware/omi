import unittest

from testing.finalization_replay.ordinary_sync_diag import _stored_sync_cases
from testing.finalization_replay.ordinary_sync_diag_report import enrich, family_for_path


class OrdinarySyncDiagnosticTests(unittest.TestCase):
    def test_projection_preserves_explicit_revision_and_labels_repeat_gap(self):
        cases = _stored_sync_cases(
            [
                {
                    'name': 'revision-two',
                    'recording': {'segments': [{'text': 'Synthetic replay'}]},
                    'document': {'sync_content_revision': 2},
                    'trigger': 'server_recovery',
                    'repeat': True,
                    'final_attempt': True,
                }
            ]
        )
        row = cases[0]['document']
        self.assertEqual(row['status'], 'completed')
        self.assertEqual(row['sync_content_revision'], 2)
        self.assertEqual(cases[0]['trigger'], 'server_recovery')
        self.assertTrue(cases[0]['repeat'])
        self.assertTrue(cases[0]['final_attempt'])

    def test_family_classifier_and_report_totals(self):
        self.assertEqual(family_for_path('/provider_calls/memory-l1'), 'Memory source and metering')
        self.assertEqual(family_for_path('/webhooks/sample/0/payload'), 'Apps')
        self.assertEqual(family_for_path('/derived_documents/users~1u~1goals~1g/title'), 'Goals')
        self.assertEqual(family_for_path('/conversation/summary_due_at'), 'Digest, minimum and relevance')
        report = {
            'commit_sha': 'a' * 40,
            'unexplained_differences': 2,
            'cases': [
                {
                    'differences': [
                        {'path': '/provider_calls/memory-l1', 'kind': 'different_value'},
                        {'path': '/webhooks/sample/0/payload', 'kind': 'different_value'},
                        {'path': '/conversation/home_source_version', 'kind': 'different_value', 'reason': 'bound'},
                    ]
                }
            ],
            'cost_table': [{'case': 'synthetic', 'python': {}, 'go': {}}],
        }
        enriched = enrich(report)
        counts = enriched['diagnostic']['family_counts']
        self.assertEqual(counts['Memory source and metering']['unexplained'], 1)
        self.assertEqual(counts['Apps']['unexplained'], 1)
        self.assertEqual(counts['Other']['allowed'], 1)
        self.assertEqual(enriched['diagnostic']['allowed_by_rule'], {'bound': 1})
        self.assertEqual(
            enriched['diagnostic']['approved_rule_reference'],
            'backend-go/tools/replay/comparison-rules.md',
        )
        self.assertNotIn('cost_table', enriched)
        self.assertNotIn('cost', enriched['cases'][0])


if __name__ == '__main__':
    unittest.main()
