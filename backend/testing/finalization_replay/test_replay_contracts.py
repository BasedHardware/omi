"""Regression tests for replay safety and measurement contracts."""

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from testing.finalization_replay.candidate import _Handler, replay_database
from testing.finalization_replay.driver import _observe
from testing.finalization_replay.metrics import _delete_write, _invoke_rpc, _wrap_stream, prompt_token_estimate
from testing.finalization_replay.ordinary_sync_diag_report import is_episode_attach_memo_path
from testing.finalization_replay.state import (
    CaseState,
    episode_attach_go_memo_failure_reason,
    episode_attach_memo_cache_failure_reason,
    episode_attach_memo_failure_reason,
    episode_attach_memo_valid,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY_PATH = REPO_ROOT / 'backend-go' / 'tools' / 'replay' / 'verify.py'
VERIFY_SPEC = importlib.util.spec_from_file_location('replay_verify_contracts', VERIFY_PATH)
verify = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(verify)


class ReplayContractTests(unittest.TestCase):
    def test_attach_memo_report_recognizes_value_and_synthetic_evidence_paths(self):
        self.assertTrue(is_episode_attach_memo_path('/derived_documents/users~1u~1episode_links~1c/attach_completed'))
        self.assertTrue(
            is_episode_attach_memo_path('/go/derived_documents/users~1u~1episode_links~1c/attach_memo_evidence')
        )
        self.assertFalse(is_episode_attach_memo_path('/derived_documents/users~1u~1episode_links~1c/attach_updated_at'))

    def test_episode_attach_memo_evidence_checks_key_owner_and_completion(self):
        conversation = {'transcript_segments': 'fixture-envelope', 'transcript_segments_compressed': True}
        link_path = 'users/owner/episode_links/conversation'
        link = {
            'episode_id': 'episode',
            'attach_owner_id': 'episode',
            'attach_revision': 'v2:fixture-key',
            'attach_completed': 'v2:fixture-key',
            'attach_finalized': None,
        }
        decoded_rows = []

        def decode(uid, raw, compressed):
            decoded_rows.append((uid, raw, compressed))
            return [{'text': 'fixture'}]

        def compute_key(row):
            self.assertEqual(row['transcript_segments'], [{'text': 'fixture'}])
            return 'v2:fixture-key'

        self.assertTrue(
            episode_attach_memo_valid(
                'owner',
                'conversation',
                conversation,
                {link_path: link},
                transcript_decoder=decode,
                content_key_fn=compute_key,
            )
        )
        self.assertEqual(decoded_rows, [('owner', 'fixture-envelope', True)])

        link['attach_owner_id'] = 'other-episode'
        self.assertFalse(
            episode_attach_memo_valid(
                'owner',
                'conversation',
                conversation,
                {link_path: link},
                transcript_decoder=decode,
                content_key_fn=compute_key,
            )
        )
        self.assertEqual(
            episode_attach_memo_failure_reason(
                'owner',
                'conversation',
                conversation,
                {link_path: link},
                transcript_decoder=decode,
                content_key_fn=compute_key,
            ),
            'owner_binding_mismatch',
        )
        link['attach_owner_id'] = 'episode'
        link['attach_revision'] = 'v2:fixture-key'
        link['attach_finalized'] = 'stale-finalization'
        self.assertFalse(
            episode_attach_memo_valid(
                'owner',
                'conversation',
                conversation,
                {link_path: link},
                transcript_decoder=decode,
                content_key_fn=compute_key,
            )
        )
        link['attach_finalized'] = None
        link['attach_revision'] = 'stale-key'
        self.assertFalse(
            episode_attach_memo_valid(
                'owner',
                'conversation',
                conversation,
                {link_path: link},
                transcript_decoder=decode,
                content_key_fn=compute_key,
            )
        )

    def test_episode_attach_memo_accepts_go_decoded_transcript_segments(self):
        segments = [{'text': 'fixture', 'start': 0, 'end': 1}]
        link_path = 'users/owner/episode_links/conversation'
        link = {
            'episode_id': 'episode',
            'attach_owner_id': 'episode',
            'attach_revision': 'v2:fixture-key',
            'attach_completed': 'v2:fixture-key',
            'attach_finalized': 'v2:fixture-key',
        }

        def decode(*_args):
            self.fail('already-decoded segments must not be decoded again')

        def compute_key(row):
            self.assertEqual(row['transcript_segments'], segments)
            return 'v2:fixture-key'

        self.assertTrue(
            episode_attach_memo_valid(
                'owner',
                'conversation',
                {'transcript_segments': segments},
                {link_path: link},
                transcript_decoder=decode,
                content_key_fn=compute_key,
            )
        )
        link['attach_finalized'] = 'stale-key'
        self.assertFalse(
            episode_attach_memo_valid(
                'owner',
                'conversation',
                {'transcript_segments': segments},
                {link_path: link},
                transcript_decoder=decode,
                content_key_fn=compute_key,
            )
        )

    def test_go_attach_memo_must_match_final_conversation_and_owner(self):
        path = 'users/owner/episode_links/conversation'
        conversation = {
            'episode_id': 'episode',
            'transcript_segments': [{'text': 'final transcript'}],
        }
        link = {
            'episode_id': 'episode',
            'attach_owner_id': 'episode',
            'attach_revision': 'v2:final-key',
            'attach_completed': 'v2:final-key',
            'attach_finalized': 'v2:final-key',
        }

        def content_key(_row):
            return 'v2:final-key'

        self.assertEqual(
            episode_attach_go_memo_failure_reason(
                'owner',
                'conversation',
                conversation,
                {path: link},
                transcript_decoder=lambda *_args: None,
                content_key_fn=content_key,
            ),
            '',
        )
        link['attach_completed'] = 'v2:wrong-go-key'
        self.assertEqual(
            episode_attach_go_memo_failure_reason(
                'owner',
                'conversation',
                conversation,
                {path: link},
                transcript_decoder=lambda *_args: None,
                content_key_fn=content_key,
            ),
            'completed_key_mismatch',
        )
        link['attach_completed'] = 'v2:final-key'
        link['attach_owner_id'] = 'wrong-episode'
        self.assertEqual(
            episode_attach_go_memo_failure_reason(
                'owner',
                'conversation',
                conversation,
                {path: link},
                transcript_decoder=lambda *_args: None,
                content_key_fn=content_key,
            ),
            'owner_binding_mismatch',
        )
        link['attach_owner_id'] = 'episode'
        conversation['episode_id'] = 'other-episode'
        self.assertEqual(
            episode_attach_go_memo_failure_reason(
                'owner',
                'conversation',
                conversation,
                {path: link},
                transcript_decoder=lambda *_args: None,
                content_key_fn=content_key,
            ),
            'conversation_owner_mismatch',
        )

    def test_python_attach_memo_cache_fallthrough_requires_own_prior_key(self):
        path = 'users/owner/episode_links/conversation'
        conversation = {'episode_id': 'episode'}
        link = {
            'episode_id': 'episode',
            'attach_owner_id': 'episode',
            'attach_revision': 'v2:older-python-key',
            'attach_completed': 'v2:older-python-key',
        }

        self.assertEqual(
            episode_attach_memo_cache_failure_reason(
                'owner', 'conversation', ['v2:older-python-key'], {path: link}, conversation
            ),
            '',
        )
        link['attach_finalized'] = 'v2:unproduced-key'
        self.assertEqual(
            episode_attach_memo_cache_failure_reason(
                'owner', 'conversation', ['v2:older-python-key'], {path: link}, conversation
            ),
            'python_key_not_produced',
        )
        self.assertEqual(episode_attach_memo_cache_failure_reason('owner', 'conversation', [], {path: {}}, {}), '')

    def test_database_creation_ignores_hostile_libpq_environment(self):
        observed = {}

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, *_args):
                pass

        def connect(dsn, **kwargs):
            observed['dsn'] = dsn
            observed['kwargs'] = kwargs
            observed['pg_environment'] = {key: value for key, value in os.environ.items() if key.startswith('PG')}
            return Connection()

        hostile = {
            'PGHOSTADDR': '198.51.100.77',
            'PGHOST': 'attacker.invalid',
            'PGSERVICE': 'hostile-service',
        }
        with patch.dict(os.environ, hostile), patch('psycopg.connect', side_effect=connect):
            with replay_database('postgres://replay:secret@127.0.0.1:5432/replay?sslmode=disable'):
                pass
            self.assertEqual({key: os.environ.get(key) for key in hostile}, hostile)

        self.assertEqual(observed['pg_environment'], {})
        self.assertEqual(observed['kwargs']['host'], '127.0.0.1')
        self.assertEqual(observed['kwargs']['hostaddr'], '127.0.0.1')
        self.assertEqual(observed['kwargs']['port'], 5432)

    def test_snapshot_keeps_boolean_to_integer_change(self):
        state = CaseState.__new__(CaseState)
        state.started_at = datetime.now(timezone.utc)
        state.queue_fanout_key = None
        state.initial_updated_at = 'before'
        state.admitted = None
        state.provider_calls = []
        state.go_evidence = {}
        state.effects = {}
        state.webhooks = []
        state.documents = lambda: {'derived/doc': {'enabled': 1}}
        state.cost = lambda: {'measured': True}

        class Snapshot:
            def to_dict(self):
                return {'updated_at': 'after'}

        class Conversation:
            def get(self):
                return Snapshot()

        state.conversation = Conversation()
        observation = state.observe('completed', {'derived/doc': {'enabled': True}})
        self.assertEqual(observation['derived_documents'], {'derived/doc': {'enabled': 1}})

    def test_embedding_meter_counts_pretokenized_batches(self):
        state = CaseState.__new__(CaseState)
        from threading import Lock

        state._metrics_lock = Lock()
        state.provider_calls = []
        state.embedding_tokens = 0
        state.record_embedding_request([[101, 202, 303], [404]])
        self.assertEqual(state.embedding_tokens, 4)
        self.assertEqual(state.provider_calls, ['openai-embeddings'])

    def test_cost_verifier_rejects_zero_rows_when_activity_is_observed(self):
        zero_cost = {
            'measured': True,
            'token_basis': 'cl100k content-token estimate; excludes model/API framing',
            'llm_tokens': {'prompt': 0, 'completion': 0, 'total': 0},
            'embedding_tokens': 0,
            'firestore_operations': {
                'rpc_calls': 0,
                'document_reads': 0,
                'query_documents': 0,
                'query_requests': 0,
                'writes': 0,
                'deletes': 0,
            },
        }
        for observation in (
            {'provider_calls': ['conv-structure']},
            {'provider_calls': [], 'derived_documents': {'users/replay/doc': {'value': 1}}},
        ):
            with self.subTest(observation=observation):
                case = {'name': 'active-case', 'cost': {'python': zero_cost, 'go': zero_cost}, 'python': observation}
                report = {
                    'cases': [case],
                    'cost_table': [{'case': 'active-case', 'python': zero_cost, 'go': zero_cost}],
                }
                with self.assertRaises(SystemExit):
                    verify.verify_cost(report)

    def test_jobd_wire_input_uses_nonzero_shared_prompt_token_basis(self):
        from threading import Lock

        state = CaseState.__new__(CaseState)
        state.uid = 'replay-cost'
        state.cid = 'case-cost'
        state.notes = {'title': 'n', 'overview': 'o'}
        state.case = {}
        state.memories = []
        state._metrics_lock = Lock()
        state.provider_calls = []
        state.llm_tokens = {'prompt': 0, 'completion': 0}
        handler = object.__new__(_Handler)
        handler.path = '/llm/notes'
        handler.command = 'POST'
        handler.server = SimpleNamespace(state=state)
        prompt = 'Summarize this synthetic conversation.'
        transcript = ['The real jobd wire carries prompt input here.']
        input_payload = {
            'feature': 'conv-structure',
            'prompt': prompt,
            'transcript': transcript,
            'app_platform': '',
            'trigger': 'sync',
        }
        input_text = json.dumps(input_payload)
        expected_messages = [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': '\n'.join(transcript)},
        ]
        handler._body = lambda: {
            'uid': state.uid,
            'subject_id': state.cid,
            'job_id': 'job-cost',
            'request_id': 'request-cost',
            'input': input_text,
            'input_hash': 'synthetic-hash',
            'implementation_version': 'jobd-go-v1',
        }

        status, _result = handler._route()
        self.assertEqual(status, 200)
        self.assertGreater(state.llm_tokens['prompt'], 0)
        self.assertEqual(state.llm_tokens['prompt'], prompt_token_estimate(expected_messages))

    def test_task_exported_json_drops_go_evidence_after_departure_checks(self):
        private_case = {
            'name': 'synthetic',
            'python': {'conversation': {'private': 'value'}},
            'go': {'conversation': {'private': 'value'}},
            'go_evidence': {'job': {'metadata': 'private queue metadata'}},
            'errors': {},
            'differences': [],
        }
        report = {'cases': [private_case], 'failed_cases': 0, 'unexplained_differences': 0}

        with tempfile.TemporaryDirectory() as temp_dir:
            parity_path = Path(temp_dir) / 'parity-input.json'
            gaps_path = Path(temp_dir) / 'gaps-input.json'
            parity_path.write_text(json.dumps(report))
            gaps_path.write_text(json.dumps(report))
            output_dir = Path(temp_dir) / 'exported'

            def assert_departure_checks_see_evidence(gaps):
                self.assertEqual(gaps['cases'][0]['go_evidence']['job']['metadata'], 'private queue metadata')

            with (
                patch.object(verify, 'verify_corpus_map'),
                patch.object(verify, 'verify_unexplained_count'),
                patch.object(verify, 'verify_departures', side_effect=assert_departure_checks_see_evidence),
            ):
                verify.verify_task_reports(str(output_dir), str(parity_path), str(gaps_path))

            for name in ('parity.json', 'gaps.json'):
                exported = json.loads((output_dir / name).read_text())
                self.assertNotIn('go_evidence', exported['cases'][0])
                self.assertNotIn('python', exported['cases'][0])
                self.assertNotIn('go', exported['cases'][0])

    def test_error_observation_packs_effects(self):
        from threading import Lock

        state = CaseState.__new__(CaseState)
        state._metrics_lock = Lock()
        state.cost_measured = False
        state.documents = lambda: {}
        state.start = lambda: setattr(state, 'started_at', datetime.now(timezone.utc))
        state.started_at = None
        state.queue_fanout_key = None
        state.admitted = None
        state.provider_calls = []
        state.effects = {'raw_payload': b'abc'}
        state.conversation = SimpleNamespace()
        state.webhooks = []
        state.go_evidence = {}
        state.cost = lambda: {'measured': state.cost_measured}
        output = {'errors': {}}

        def fail(_state):
            raise RuntimeError('synthetic adapter error')

        _observe(state, fail, output, 'go')
        self.assertEqual(output['go']['effects'], {'raw_payload': {'$bytes': 'YWJj'}})

    def test_read_attempt_is_counted_when_rpc_fails(self):
        operations = {}

        class Meter:
            def add_firestore_operations(self, **counts):
                for name, count in counts.items():
                    operations[name] = operations.get(name, 0) + count

        def fail():
            raise RuntimeError('synthetic Firestore failure')

        with self.assertRaises(RuntimeError):
            _invoke_rpc(Meter(), 'get_document', {'get_document'}, fail)
        self.assertEqual(operations['document_reads'], 1)
        self.assertEqual(operations['rpc_calls'], 1)

    def test_partial_stream_counts_consumed_results_and_delete_empty_map(self):
        operations = {}

        class Meter:
            def add_firestore_operations(self, **counts):
                for name, count in counts.items():
                    operations[name] = operations.get(name, 0) + count

        stream = _wrap_stream(
            [SimpleNamespace(document={'name': 'first'}), SimpleNamespace(document={'name': 'second'})],
            'run_query',
            Meter(),
        )
        next(stream)
        stream.close()
        self.assertEqual(operations['query_documents'], 1)
        self.assertTrue(_delete_write({'delete': {}}))
        self.assertFalse(_delete_write({'update': {'name': 'retained'}}))


if __name__ == '__main__':
    unittest.main()
