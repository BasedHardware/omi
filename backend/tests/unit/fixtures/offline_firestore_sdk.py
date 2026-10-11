from typing import Any

from google.cloud.firestore_v1.batch import WriteBatch
from google.cloud.firestore_v1.collection import CollectionReference
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.query import CollectionGroup
from google.cloud.firestore_v1.transaction import Transaction


class OfflineFirestoreClient:
    def __init__(self, *, project: str, database: str = '(default)', api: Any = None):
        self.project = project
        self._database = database
        self._database_string = f'projects/{project}/databases/{database}'
        self._rpc_metadata = ()
        self._firestore_api_internal = api

    @property
    def _firestore_api(self):
        if self._firestore_api_internal is None:
            raise AssertionError('Offline Firestore fixture has no RPC implementation')
        return self._firestore_api_internal

    def collection(self, *path):
        return CollectionReference(*'/'.join(path).split('/'), client=self)

    def document(self, *path):
        relative = '/'.join(path).removeprefix(self._database_string + '/documents/')
        return DocumentReference(*relative.split('/'), client=self)

    def collection_group(self, collection_id):
        if '/' in collection_id:
            raise ValueError('Collection ID must not contain a slash')
        return CollectionGroup(self.collection(collection_id))

    def transaction(self, **kwargs):
        return Transaction(self, **kwargs)

    def batch(self):
        return WriteBatch(self)

    def get_all(self, references, **kwargs):
        for reference in references:
            yield reference.get(**kwargs)
