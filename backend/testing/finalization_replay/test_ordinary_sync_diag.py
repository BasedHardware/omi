import ast
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from testing.finalization_replay.metrics import _active_state, measure, suspend_meter
from testing.finalization_replay.ordinary_sync_diag import _stored_sync_cases
from testing.finalization_replay.ordinary_sync_diag_report import enrich, family_for_path, unlabelled_groups


class OrdinarySyncDiagnosticTests(unittest.TestCase):
    def test_pinned_replay_bindings_have_no_function_local_imports(self):
        for module in ('ordinary_sync_diag', 'ordinary_sync_runtime', 'ordinary_sync_retry', 'memo_bindings', 'state'):
            source = Path(__file__).with_name(f'{module}.py')
            for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertFalse(
                        any(isinstance(child, (ast.Import, ast.ImportFrom)) for child in ast.walk(node)),
                        f'{module}:{node.lineno} imports inside {node.name}',
                    )

    def test_failed_case_closes_report_gate_and_exits_nonzero(self):
        # Use the unreadable fixture to prove execution failure also bypasses
        # exception validation and still persists the report for inspection.
        report = {
            'failed_cases': 1,
            'cases': [{'name': 'unreadable-ciphertext-dead-letters', 'errors': {'go': 'UnexpectedGoOutcome'}}],
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_text(json.dumps(report), encoding='utf-8')
            script = Path(__file__).with_name('ordinary_sync_diag_report.py')
            result = subprocess.run([sys.executable, '-I', script, path], capture_output=True, check=False)
            self.assertEqual(result.returncode, 2, result.stderr)
            diagnostic = json.loads(path.read_text(encoding='utf-8'))['diagnostic']
        self.assertEqual(diagnostic['cohort_gate'], 'closed')
        self.assertEqual(diagnostic['r7_operation_budget']['status'], 'invalid')

    def test_memo_probe_suspends_only_its_own_meter(self):
        state = SimpleNamespace(cost_measured=False)
        with measure(state), ThreadPoolExecutor(max_workers=1) as executor:
            with suspend_meter():
                self.assertIsNone(_active_state())
                self.assertIs(executor.submit(_active_state).result(timeout=2), state)
            self.assertIs(_active_state(), state)

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

    def test_unverified_speaker_envelope_is_a_value_free_go_gap(self):
        path = '/derived_documents/users~1replay-c~1conversations~1c~1speaker_evidence~1current/payload'
        report = {
            'unexplained_differences': 1,
            'cases': [
                {
                    'name': 'c',
                    'differences': [
                        {'path': path, 'kind': 'different_value', 'failure_reason': 'speaker_envelope_unverified'}
                    ],
                }
            ],
        }
        result = enrich(report)
        row = result['cases'][0]['differences'][0]
        self.assertEqual(row['label'], 'go_gap')
        self.assertEqual(set(row), {'path', 'kind', 'failure_reason', 'family', 'label'})
        self.assertEqual(result['diagnostic']['unexplained_gate']['go_gap_rows'], 1)

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
                        {'path': '/status', 'kind': 'different_value', 'unreadable_terminal_consequence': True},
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

    def test_reviewed_state_version_and_whitespace_rows_are_exact_go_gaps(self):
        report = {
            'unexplained_differences': 5,
            'cases': [
                {
                    'name': 'empty-capture',
                    'differences': [
                        {
                            'path': '/derived_documents/users~1replay-empty-capture~1episodes~14a3517ab-b5a4-58fc-9d1f-7525f189b614/state_version',
                            'kind': 'different_value',
                        }
                    ],
                },
                {
                    'name': 'transcript-empty-text',
                    'differences': [
                        {
                            'path': '/derived_documents/users~1replay-transcript-empty-text~1episodes~1514b6b9f-53d4-5569-8092-f0cdc6a3aa25/state_version',
                            'kind': 'different_value',
                        }
                    ],
                },
                {
                    'name': 'transcript-whitespace',
                    'differences': [{'path': '/conversation/transcript_segments', 'kind': 'different_value'}],
                },
                {
                    'name': 'other-case',
                    'differences': [{'path': '/conversation/transcript_segments', 'kind': 'different_value'}],
                },
                {
                    'name': 'transcript-whitespace',
                    'differences': [{'path': '/conversation/transcript_segments', 'kind': 'missing_in_go'}],
                },
            ],
        }

        enriched = enrich(report)
        labels = [case['differences'][0]['label'] for case in enriched['cases']]
        self.assertEqual(labels, ['go_gap', 'go_gap', 'go_gap', None, None])
        self.assertEqual(enriched['diagnostic']['label_counts']['go_gap'], 3)
        self.assertEqual(enriched['diagnostic']['label_counts']['unlabelled'], 2)

    def test_invalid_go_attach_memo_evidence_is_go_gap_by_default(self):
        cases = []
        for name, reason in (
            ('empty-capture', 'completed_key_mismatch'),
            ('transcript-empty-text', 'completed_key_mismatch'),
            ('unreadable-ciphertext-dead-letters', 'owner_binding_mismatch'),
        ):
            differences = []
            case = {'name': name, 'differences': differences}
            if name == 'unreadable-ciphertext-dead-letters':
                case.update(
                    {
                        'python_status': 'parked',
                        'go_status': 'failure',
                        'go_ciphertext_kept': True,
                        'python_retry': {
                            'outcome': 'parked',
                            'reason': 'age_gate_72h',
                            'ciphertext_kept': True,
                            'attempts': 2,
                            'callback_pending_attempts': 1,
                        },
                    }
                )
                differences.append(
                    {'path': '/status', 'kind': 'different_value', 'unreadable_terminal_consequence': True}
                )
            differences.append(
                {
                    'path': f'/go/derived_documents/users~1replay-{name}~1episode_links~1{name}/attach_memo_evidence',
                    'kind': 'invalid_binding',
                    'failure_reason': reason,
                }
            )
            cases.append(case)
        report = {'unexplained_differences': 4, 'cases': cases}

        enriched = enrich(report)
        labels = [
            next(
                difference['label']
                for difference in case['differences']
                if difference['path'].endswith('/attach_memo_evidence')
            )
            for case in enriched['cases']
        ]
        self.assertEqual(labels, ['go_gap', 'go_gap', 'go_gap'])
        self.assertEqual(enriched['diagnostic']['label_counts']['go_gap'], 3)
        self.assertEqual(enriched['diagnostic']['label_counts'].get('unlabelled', 0), 0)


if __name__ == '__main__':
    unittest.main()
