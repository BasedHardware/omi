"""Regression tests for replay safety and measurement contracts."""

from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from testing.finalization_replay.candidate import _Handler, replay_database
from testing.finalization_replay.driver import _observe
from testing.finalization_replay.metrics import _delete_write, _invoke_rpc, _wrap_stream
from testing.finalization_replay.state import CaseState

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY_PATH = REPO_ROOT / 'backend-go' / 'tools' / 'replay' / 'verify.py'
VERIFY_SPEC = importlib.util.spec_from_file_location('replay_verify_contracts', VERIFY_PATH)
verify = importlib.util.module_from_spec(VERIFY_SPEC)
VERIFY_SPEC.loader.exec_module(verify)


class ReplayContractTests(unittest.TestCase):
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

    def test_candidate_cost_meter_uses_the_same_messages_as_python(self):
        recorded = {}
        state = SimpleNamespace(
            uid='replay-cost',
            cid='case-cost',
            notes={'title': 'n', 'overview': 'o'},
            case={},
            memories=[],
        )
        state.record_provider_call = lambda feature, prompt, _completion: recorded.update(
            feature=feature, prompt=prompt
        )
        handler = object.__new__(_Handler)
        handler.path = '/llm/notes'
        handler.command = 'POST'
        handler.server = SimpleNamespace(state=state)
        messages = [{'role': 'user', 'content': 'Count this shared message basis.'}]
        handler._body = lambda: {
            'uid': state.uid,
            'subject_id': state.cid,
            'input': 'This legacy field must not be counted.',
            'messages': messages,
        }

        status, _result = handler._route()
        self.assertEqual(status, 200)
        self.assertEqual(recorded['prompt'], messages)

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
