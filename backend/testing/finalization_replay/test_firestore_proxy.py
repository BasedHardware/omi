from threading import Lock
import unittest
from concurrent.futures import ThreadPoolExecutor

import grpc

from google.cloud.firestore_v1.types import firestore

from testing.finalization_replay.firestore_proxy import FirestoreProxy, _SERVICE


class FirestoreProxyTests(unittest.TestCase):
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
                    self.assertEqual(proxy.counts()['document_reads'], 3)
                    self.assertEqual(proxy.rpc_failures(), {})
                    self.assertTrue(0 < deadlines[0] <= 61)
                    self.assertTrue(0 < deadlines[1] <= 61)
                    self.assertTrue(0 < deadlines[2] <= 5)
            finally:
                server.stop(0).wait()


if __name__ == '__main__':
    unittest.main()
