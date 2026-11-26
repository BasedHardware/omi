from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import Lock
import unittest

import grpc

from google.cloud.firestore_v1.types import firestore

from testing.finalization_replay.firestore_proxy import FirestoreProxy, _SERVICE

ROOT = 'projects/p/databases/(default)/documents'
PRIVACY_PATH = 'batch_pipeline_privacy/' + sha256(b'owner').hexdigest()
PRIVACY_NAME = f'{ROOT}/{PRIVACY_PATH}'


def meter_proxy():
    proxy = object.__new__(FirestoreProxy)
    proxy.privacy_document_path = PRIVACY_PATH
    proxy.home_dirty_receipt_path = 'users/u/episode_links/c'
    proxy._lock = Lock()
    proxy.reset()
    return proxy


def privacy_aggregation():
    return firestore.RunAggregationQueryRequest(
        parent=ROOT,
        structured_aggregation_query={
            'structured_query': {'from_': [{'collection_id': 'batch_pipeline_privacy'}]},
            'aggregations': [{'count': {}, 'alias': 'number_of_documents'}],
        },
    )


class FirestoreProxyTests(unittest.TestCase):
    def test_read_request_shapes_attribute_the_privacy_target(self):
        queries = [
            ('get_document', firestore.GetDocumentRequest(name=PRIVACY_NAME), 1, 0),
            (
                'batch_get_documents',
                firestore.BatchGetDocumentsRequest(documents=[PRIVACY_NAME, ROOT + '/users/u']),
                0,
                0,
            ),
            (
                'list_documents',
                firestore.ListDocumentsRequest(parent=ROOT, collection_id='batch_pipeline_privacy'),
                0,
                1,
            ),
            (
                'run_query',
                firestore.RunQueryRequest(
                    parent=ROOT, structured_query={'from_': [{'collection_id': 'batch_pipeline_privacy'}]}
                ),
                0,
                1,
            ),
            ('run_aggregation_query', privacy_aggregation(), 0, 1),
        ]
        for method, request, document_reads, query_requests in queries:
            with self.subTest(method=method):
                proxy = meter_proxy()
                proxy._record_request(method, request)
                counts = proxy.counts()
                self.assertEqual(counts['batch_pipeline_privacy_document_reads'], 1)
                self.assertEqual(counts['query_requests'], query_requests)
                self.assertEqual(counts['document_reads'], document_reads)
                self.assertEqual(counts['query_documents'], 0)
                self.assertEqual(counts['writes'], 0)
                self.assertEqual(counts['deletes'], 0)
        for request in (
            firestore.ListDocumentsRequest(parent=ROOT, collection_id='users'),
            firestore.ListDocumentsRequest(parent=ROOT + '/users/u', collection_id='batch_pipeline_privacy'),
        ):
            proxy = meter_proxy()
            proxy._record_request('list_documents', request)
            self.assertEqual(proxy.counts()['batch_pipeline_privacy_document_reads'], 0)

    def test_aggregation_read_invalidates_go_privacy_proof(self):
        binary = os.environ.get('REPLAY_TEST_BINARY')
        if binary is None:
            self.skipTest('test.sh supplies the built Go replay comparator')
        proxy = meter_proxy()
        proxy._record_request('commit', firestore.CommitRequest(writes=[{'update': {'name': PRIVACY_NAME}}]))
        fields = {'memo_token': '323e4567e89b42d3a456426614174000', 'memo_schema': 1}
        doc = {
            'owner_id': 'owner',
            'status': 'completed',
            'conversation': {},
            'effects': {},
            'derived_documents': {PRIVACY_PATH: fields},
            'seeded_token_hashes': [],
            'batch_pipeline_privacy': {
                'seed': {'exists': False, 'fields': {}},
                'final': {'exists': True, 'fields': fields},
            },
        }

        def observation():
            return {**doc, 'cost': {'measured': True, 'firestore_operations': proxy.counts()}}

        control = observation()
        proxy._record_request('run_aggregation_query', privacy_aggregation())
        candidate = observation()
        self.assertEqual(proxy.counts()['batch_pipeline_privacy_document_reads'], 1)
        corpus = Path(__file__).resolve().parents[3] / 'backend-go/tools/replay/corpus/admission-parity.json'
        corpus_bytes = corpus.read_bytes()
        names = [case['name'] for case in json.loads(corpus_bytes)['cases']]
        cases = [{'name': name, 'python': control, 'go': control} for name in names]
        cases[1]['go'] = candidate
        with TemporaryDirectory() as scratch:
            observations, report = (Path(scratch) / name for name in ('observations.json', 'report.json'))
            observations.write_text(
                json.dumps({'corpus_sha256': sha256(corpus_bytes).hexdigest(), 'cases': cases}),
                encoding='utf-8',
            )
            result = subprocess.run(
                [binary, '-corpus', corpus, '-commit', '0' * 40, '-observations', observations, '-output', report],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            control_row, aggregation_row, *_ = json.loads(report.read_text(encoding='utf-8'))['cases']
        self.assertEqual(control_row['differences'], [])
        self.assertEqual(
            aggregation_row['differences'],
            [{'path': '/go/firestore_operations/batch_pipeline_privacy_document', 'kind': 'invalid_operations'}],
        )

    def test_transaction_begin_and_rollback_count_only_rpcs(self):
        proxy = meter_proxy()
        proxy._record_request('begin_transaction', firestore.BeginTransactionRequest(database=ROOT.rsplit('/', 1)[0]))
        proxy._record_request('rollback', firestore.RollbackRequest(database=ROOT.rsplit('/', 1)[0], transaction=b'id'))
        self.assertEqual({k: v for k, v in proxy.counts().items() if v}, {'rpc_calls': 2})
        self.assertEqual(proxy.operation_sources(), {})

    def test_batch_write_attributes_transform_and_delete_attempts(self):
        proxy = meter_proxy()
        request = firestore.BatchWriteRequest(
            writes=[
                {
                    'transform': {
                        'document': PRIVACY_NAME,
                        'field_transforms': [{'field_path': 'memo', 'set_to_server_value': 1}],
                    }
                },
                {'delete': PRIVACY_NAME},
            ]
        )
        proxy._record_request('batch_write', request)
        self.assertEqual(proxy.counts()['writes'], 1)
        self.assertEqual(proxy.counts()['deletes'], 1)
        self.assertEqual(proxy.counts()['batch_pipeline_privacy_document_writes'], 1)
        self.assertEqual(proxy.counts()['batch_pipeline_privacy_document_deletes'], 1)
        self.assertEqual(proxy.operation_sources()[PRIVACY_PATH], {'reads': 0, 'writes': 1, 'deletes': 1})

    def test_batch_write_requires_explicit_success_for_home_receipts(self):
        home = f'{ROOT}/users/u/episode_links/c'
        update = {'update': {'name': home, 'fields': {'home_dirty': {'boolean_value': True}}}}
        delete = {'delete': home}
        statuses = (('failed', [{}, {'code': 7}], 0), ('missing', [{}], 0), ('successful', [{}, {}], 1))
        for bucket, home_write in (('set_true', update), ('deleted', delete)):
            request = firestore.BatchWriteRequest(writes=[{'delete': PRIVACY_NAME}, home_write])
            for label, entries, expected in statuses:
                with self.subTest(home_operation=bucket, status=label):
                    proxy = meter_proxy()
                    response = firestore.BatchWriteResponse(status=entries)
                    proxy._record_committed_home_writes(
                        'batch_write', request, firestore.BatchWriteResponse.serialize(response)
                    )
                    self.assertEqual(proxy.home_receipt_trace()[bucket], expected)
                    self.assertEqual(sum(proxy.home_receipt_trace().values()), expected)

    def test_direct_writes_attribute_the_document_name(self):
        proxy = meter_proxy()
        privacy = firestore.UpdateDocumentRequest(document={'name': PRIVACY_NAME})
        proxy._record_request('update_document', privacy)
        proxy._record_request(
            'create_document',
            firestore.CreateDocumentRequest(
                parent=ROOT, collection_id='batch_pipeline_privacy', document_id=PRIVACY_PATH.split('/')[-1]
            ),
        )
        proxy._record_request('delete_document', firestore.DeleteDocumentRequest(name=PRIVACY_NAME))
        self.assertEqual(proxy.counts()['batch_pipeline_privacy_document_writes'], 2)
        self.assertEqual(proxy.counts()['batch_pipeline_privacy_document_deletes'], 1)
        self.assertEqual(proxy.operation_sources()[PRIVACY_PATH], {'reads': 0, 'writes': 2, 'deletes': 1})
        home = firestore.UpdateDocumentRequest(
            document={'name': f'{ROOT}/users/u/episode_links/c', 'fields': {'home_dirty': {'boolean_value': True}}}
        )
        proxy._record_committed_home_writes('update_document', home, b'')
        self.assertEqual(proxy.home_receipt_trace()['set_true'], 1)

    def test_batch_get_attributes_found_and_missing_but_skips_metadata_only(self):
        proxy = meter_proxy()
        for response in (
            firestore.BatchGetDocumentsResponse(found={'name': PRIVACY_NAME}),
            firestore.BatchGetDocumentsResponse(missing=ROOT + '/users/missing'),
            firestore.BatchGetDocumentsResponse(transaction=b'id'),
        ):
            proxy._record_response('batch_get_documents', firestore.BatchGetDocumentsResponse.serialize(response))
        self.assertEqual(proxy.counts()['document_reads'], 2)
        self.assertEqual(
            proxy.operation_sources(),
            {
                PRIVACY_PATH: {'reads': 1, 'writes': 0, 'deletes': 0},
                'users/missing': {'reads': 1, 'writes': 0, 'deletes': 0},
            },
        )

    def test_commit_counts_target_operations_and_home_receipt_lifecycle(self):
        proxy = object.__new__(FirestoreProxy)
        proxy.privacy_document_path = 'batch_pipeline_privacy/owner-hash'
        proxy.home_dirty_receipt_path = 'users/u/episode_links/c'
        proxy._lock = Lock()
        proxy.reset()
        request = firestore.CommitRequest(
            writes=[
                {
                    'update': {
                        'name': 'projects/p/databases/(default)/documents/batch_pipeline_privacy/owner-hash',
                        'fields': {'memo_token': {'string_value': 'synthetic'}},
                    }
                },
                {
                    'update': {
                        'name': 'projects/p/databases/(default)/documents/users/u/episode_links/c',
                        'fields': {'home_dirty': {'boolean_value': True}},
                    }
                },
                {
                    'update': {
                        'name': 'projects/p/databases/(default)/documents/users/u/episode_links/c',
                        'fields': {'home_dirty': {'boolean_value': False}},
                    }
                },
                {'delete': 'projects/p/databases/(default)/documents/batch_pipeline_privacy/owner-hash'},
            ]
        )

        proxy._record_request('commit', request)
        proxy._record_committed_home_writes('commit', request, b'')

        self.assertEqual(proxy.counts()['rpc_calls'], 1)
        self.assertEqual(proxy.counts()['batch_pipeline_privacy_document_writes'], 1)
        self.assertEqual(proxy.counts()['batch_pipeline_privacy_document_deletes'], 1)
        self.assertEqual(
            proxy.operation_sources(),
            {
                'batch_pipeline_privacy/owner-hash': {'reads': 0, 'writes': 1, 'deletes': 1},
                'users/u/episode_links/c': {'reads': 0, 'writes': 2, 'deletes': 0},
            },
        )
        self.assertEqual(proxy.home_receipt_trace(), {'set_true': 1, 'set_false': 1, 'deleted': 0, 'other_write': 0})

    def test_query_on_privacy_collection_counts_as_a_target_read(self):
        proxy = object.__new__(FirestoreProxy)
        proxy.privacy_document_path = 'batch_pipeline_privacy/owner-hash'
        proxy.home_dirty_receipt_path = 'users/u/episode_links/c'
        proxy._lock = Lock()
        proxy.reset()
        request = firestore.RunQueryRequest(
            parent='projects/p/databases/(default)/documents',
            structured_query={'from_': [{'collection_id': 'batch_pipeline_privacy'}]},
        )

        proxy._record_request('run_query', request)

        self.assertEqual(proxy.counts()['query_requests'], 1)
        self.assertEqual(proxy.counts()['batch_pipeline_privacy_document_reads'], 1)

    def test_forwards_unary_and_streaming_calls_without_a_deadline(self):
        name = 'projects/demo-proxy/databases/(default)/documents/users/fixture'
        deadlines = []

        def get(_request, context):
            deadlines.append(context.time_remaining())
            return b''

        def batch_get(_request, context):
            deadlines.append(context.time_remaining())
            yield firestore.BatchGetDocumentsResponse.serialize(firestore.BatchGetDocumentsResponse(missing=name))

        def list_documents(_request, _context):
            return firestore.ListDocumentsResponse.serialize(
                firestore.ListDocumentsResponse(documents=[{'name': name}])
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            server = grpc.server(executor)
            port = server.add_insecure_port('127.0.0.1:0')
            server.add_generic_rpc_handlers(
                (
                    grpc.method_handlers_generic_handler(
                        _SERVICE,
                        {
                            'GetDocument': grpc.unary_unary_rpc_method_handler(get),
                            'BatchGetDocuments': grpc.unary_stream_rpc_method_handler(batch_get),
                            'ListDocuments': grpc.unary_unary_rpc_method_handler(list_documents),
                        },
                    ),
                )
            )
            server.start()
            try:
                with FirestoreProxy(f'127.0.0.1:{port}', '', '') as proxy, grpc.insecure_channel(
                    proxy.address
                ) as client:
                    point = client.unary_unary(
                        f'/{_SERVICE}/GetDocument', request_serializer=firestore.GetDocumentRequest.serialize
                    )
                    batch = client.unary_stream(
                        f'/{_SERVICE}/BatchGetDocuments',
                        request_serializer=firestore.BatchGetDocumentsRequest.serialize,
                    )
                    point(firestore.GetDocumentRequest(name=name))
                    self.assertEqual(len(list(batch(firestore.BatchGetDocumentsRequest(documents=[name])))), 1)
                    point(firestore.GetDocumentRequest(name=name), timeout=4)
                    listed = client.unary_unary(
                        f'/{_SERVICE}/ListDocuments',
                        request_serializer=firestore.ListDocumentsRequest.serialize,
                        response_deserializer=firestore.ListDocumentsResponse.deserialize,
                    )
                    self.assertEqual(
                        len(listed(firestore.ListDocumentsRequest(parent=ROOT, collection_id='users')).documents), 1
                    )
                    self.assertEqual(proxy.counts()['document_reads'], 3)
                    self.assertEqual(proxy.counts()['query_documents'], 1)
                    self.assertEqual(proxy.operation_sources()['users/fixture']['reads'], 4)
                    self.assertEqual(proxy.rpc_failures(), {})
                    self.assertTrue(0 < deadlines[0] <= 61)
                    self.assertTrue(0 < deadlines[1] <= 61)
                    self.assertTrue(0 < deadlines[2] <= 5)
            finally:
                server.stop(0).wait()


if __name__ == '__main__':
    unittest.main()
