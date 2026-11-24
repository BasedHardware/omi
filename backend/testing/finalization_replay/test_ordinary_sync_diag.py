import unittest

from testing.finalization_replay.ordinary_sync_diag import _stored_sync_cases
from testing.finalization_replay.ordinary_sync_diag_report import (
    enrich,
    family_for_path,
    unlabelled_groups,
    unreadable_terminal_consequences,
)


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
            'unexplained_differences': 5,
            'cases': [
                {
                    'name': 'receipt-trace',
                    'home_dirty_receipt_trace': {
                        'python': {'set_true': 2, 'set_false': 1, 'deleted': 0, 'other_write': 0},
                        'go': {'set_true': 1, 'set_false': 0, 'deleted': 1, 'other_write': 0},
                    },
                    'differences': [
                        {'path': '/provider_calls/memory-l1', 'kind': 'different_value'},
                        {'path': '/webhooks/sample/0/payload', 'kind': 'different_value'},
                        {'path': '/conversation/home_source_version', 'kind': 'different_value', 'reason': 'bound'},
                        {
                            'path': 'go/conversation/home_source_version',
                            'kind': 'invalid_token_binding',
                            'failure_reason': 'home_dirty_receipt_missing',
                        },
                        {'path': '/conversation/go_finalization_notes_input_hash', 'kind': 'missing_in_python'},
                        {
                            'path': '/conversation/finalization_job_id',
                            'kind': 'missing_in_python',
                            'reason': 'Go finalization job ID binds to its admitted queue job',
                        },
                    ],
                }
            ],
            'cost_table': [{'case': 'synthetic', 'python': {}, 'go': {}}],
        }
        enriched = enrich(report)
        counts = enriched['diagnostic']['family_counts']
        self.assertEqual(counts['Memory source and metering']['unexplained'], 1)
        self.assertEqual(counts['Apps']['unexplained'], 1)
        self.assertEqual(counts['Other']['allowed'], 1)
        self.assertEqual(counts['Other']['unexplained'], 1)
        self.assertEqual(counts['Other']['go_gap'], 2)
        self.assertEqual(enriched['diagnostic']['allowed_by_rule'], {'bound': 1})
        self.assertEqual(enriched['diagnostic']['label_counts']['go_gap'], 2)
        self.assertEqual(enriched['diagnostic']['home_dirty_receipt_missing']['rows'], 1)
        self.assertEqual(enriched['diagnostic']['home_dirty_receipt_missing']['label'], 'unlabelled')
        self.assertEqual(enriched['diagnostic']['home_dirty_receipt_missing']['writes_set_true'], 1)
        self.assertEqual(enriched['diagnostic']['home_dirty_receipt_missing']['writes_set_false'], 0)
        self.assertEqual(enriched['diagnostic']['home_dirty_receipt_missing']['deletes'], 1)
        self.assertEqual(
            enriched['diagnostic']['approved_rule_reference'],
            'backend-go/tools/replay/comparison-rules.md',
        )
        self.assertNotIn('cost_table', enriched)
        self.assertNotIn('cost', enriched['cases'][0])
        token_row = enriched['cases'][0]['differences'][3]
        self.assertEqual(token_row['failure_reason'], 'home_dirty_receipt_missing')

    def test_unreadable_park_requires_terminal_custody_and_excuses_only_the_status(self):
        report = {
            'unexplained_differences': 2,
            'cases': [
                {
                    'name': 'unreadable-ciphertext-dead-letters',
                    'python_status': 'parked',
                    'go_status': 'failure',
                    'go_ciphertext_kept': True,
                    'python_retry': {
                        'outcome': 'parked',
                        'reason': 'age_gate_72h',
                        'ciphertext_kept': True,
                        'attempts': 3,
                        'callback_pending_attempts': 2,
                    },
                    'differences': [
                        {'path': '/status', 'kind': 'different_value'},
                        {'path': '/conversation/transcript_segments', 'kind': 'different_value'},
                    ],
                }
            ],
        }
        enriched = enrich(report)
        status_row, transcript_row = enriched['cases'][0]['differences']
        self.assertEqual(status_row['label'], 'python_bug:unreadable_ciphertext_retry_until_age_gate')
        self.assertEqual(status_row['issue'], 'SCA-4178')
        self.assertIsNone(transcript_row['label'])
        self.assertEqual(enriched['unexplained_differences'], 1)
        self.assertEqual(
            enriched['diagnostic']['unexplained_gate']['python_bug_exceptions'],
            {'unreadable_ciphertext_retry_until_age_gate': 1},
        )

        report['cases'][0]['python_retry']['ciphertext_kept'] = False
        with self.assertRaisesRegex(ValueError, 'stale or missing evidence'):
            enrich(report)

    def test_unreadable_consequences_require_same_ciphertext_and_no_provider_calls(self):
        uid, cid = 'fixture', 'capture'
        attention = f'users/{uid}/processing_attention_items/conv-summary:{cid}:terminal'
        case = {
            'go_evidence': {'job': {'state': 'dead_letter', 'cause': 'conversation_unreadable'}},
            'go': {
                'owner_id': uid,
                'conversation_id': cid,
                'conversation': {'finalization_status': 'dead_letter', 'transcript_segments': 'ciphertext'},
                'derived_documents': {attention: {'failure_code': 'conversation_unreadable'}},
                'provider_calls': [],
            },
            'python': {
                'conversation': {'transcript_segments': 'ciphertext'},
                'derived_documents': {
                    'sync_reprocess_outbox/parked': {'uid': uid, 'conversation_id': cid, 'age_gate_parked': True},
                    'sync_reprocess_outbox/unrelated': {'uid': uid, 'conversation_id': 'other', 'age_gate_parked': True},
                },
                'provider_calls': [],
            },
        }
        paths = {path for path, _ in unreadable_terminal_consequences(case)}
        self.assertIn('/derived_documents/sync_reprocess_outbox~1parked', paths)
        self.assertIn('/derived_documents/' + attention.replace('/', '~1'), paths)
        self.assertNotIn('/derived_documents/sync_reprocess_outbox~1unrelated', paths)
        case['python']['provider_calls'] = ['notes']
        self.assertEqual(unreadable_terminal_consequences(case), set())
        case['python']['provider_calls'] = []
        case['python']['conversation']['transcript_segments'] = 'other-ciphertext'
        self.assertEqual(unreadable_terminal_consequences(case), set())

    def test_operation_table_separates_r7_overages_from_field_rows(self):
        report = {
            'unexplained_differences': 1,
            'cases': [
                {
                    'name': 'synthetic-overage',
                    'cost': {
                        'python': {
                            'firestore_operations': {
                                'document_reads': 2,
                                'query_documents': 1,
                                'writes': 2,
                                'deletes': 1,
                            }
                        },
                        'go': {
                            'firestore_operations': {
                                'document_reads': 4,
                                'query_documents': 0,
                                'writes': 4,
                                'deletes': 1,
                            }
                        },
                    },
                    'go': {
                        'firestore_operation_sources': {
                            'users/u/episode_links/c': {'reads': 3, 'writes': 1, 'deletes': 0},
                            'users/u/conversations/c': {'reads': 1, 'writes': 3, 'deletes': 1},
                        }
                    },
                    'differences': [{'path': '/conversation/title', 'kind': 'different_value'}],
                }
            ],
        }
        enriched = enrich(report)
        self.assertEqual(enriched['diagnostic']['label_counts']['unlabelled'], 1)
        self.assertEqual(enriched['diagnostic']['label_counts']['go_gap:ops'], 1)
        self.assertEqual(enriched['diagnostic']['r7_operation_budget']['over_budget_case_count'], 1)
        self.assertEqual(enriched['diagnostic']['r7_operation_budget']['status'], 'blocked')
        self.assertEqual(enriched['diagnostic']['cohort_gate'], 'closed')
        self.assertEqual(
            enriched['operation_table'][0],
            {
                'case': 'synthetic-overage',
                'python_reads': 3,
                'python_writes': 2,
                'python_deletes': 1,
                'go_reads': 4,
                'go_writes': 4,
                'go_deletes': 1,
                'python_operations': 6,
                'go_operations': 9,
                'difference': 3,
                'label': 'go_gap:ops',
                'go_top_operation_sources': [
                    {
                        'document_path': 'users/u/conversations/c',
                        'reads': 1,
                        'writes': 3,
                        'deletes': 1,
                        'operations': 5,
                    },
                    {
                        'document_path': 'users/u/episode_links/c',
                        'reads': 3,
                        'writes': 1,
                        'deletes': 0,
                        'operations': 4,
                    },
                ],
            },
        )

    def test_unlabelled_groups_normalize_case_specific_document_paths(self):
        groups = unlabelled_groups(
            [
                {
                    'name': 'case-one',
                    'differences': [
                        {
                            'path': '/derived_documents/users~1replay-case-one~1episode_links~1case-one/home_dirty',
                            'kind': 'different_value',
                        }
                    ],
                },
                {
                    'name': 'case-two',
                    'differences': [
                        {
                            'path': '/derived_documents/users~1replay-case-two~1episode_links~1case-two/home_dirty',
                            'kind': 'different_value',
                        }
                    ],
                },
            ]
        )
        self.assertEqual(
            groups,
            [
                {
                    'path_pattern': '/derived_documents/users/<uid>/episode_links/<cid>',
                    'field': 'home_dirty',
                    'rows': 2,
                    'cases': 2,
                    'case_ids': ['case-one', 'case-two'],
                    'kinds': ['different_value'],
                }
            ],
        )


if __name__ == '__main__':
    unittest.main()
