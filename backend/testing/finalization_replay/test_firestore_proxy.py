from threading import Lock
import unittest

from google.cloud.firestore_v1.types import firestore

from testing.finalization_replay.firestore_proxy import FirestoreProxy


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


if __name__ == '__main__':
    unittest.main()
