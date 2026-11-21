"""Production eraser for owner-cancelled batch uploads (see ``owner_cancel``).

Reuses the privacy purge's unit helpers. Every erasing transaction re-proves
that the unit is still the owner's and still fenced by owner cancellation, so a
row the fence did not write is never touched. Objects go before metadata, so a
partial failure leaves the rows reachable for the next call.
"""

from typing import Any, Callable

from database._client import get_data_plane_firestore_client
from database.batch_pipeline_purge import delete_job, erase_artifact, row_references
from database.batch_pipeline_staging import artifact_id
from utils.batch_pipeline.owner_cancel import JOB_PREFIX, is_owner_cancelled
from utils.batch_pipeline.retention import delete_batch_object
from utils.other.storage import delete_unlinked_upload_archives


class UnitNotFenced(RuntimeError):
    """The unit changed owner or fence after the cancel; nothing is erased."""


class FirestoreEraser:
    def __init__(
        self,
        namespace: str,
        *,
        client: Any = None,
        delete_uri: Callable[[str, str], None] = delete_batch_object,
        delete_archives: Callable[[str, str, tuple[str, ...]], int] = delete_unlinked_upload_archives,
    ):
        self.namespace = namespace
        self._client = client
        self.delete_uri = delete_uri
        self.delete_archives = delete_archives

    @property
    def client(self) -> Any:
        return self._client if self._client is not None else get_data_plane_firestore_client()

    def _collection(self, table: str) -> Any:
        return self.client.collection(f'{self.namespace}_{table}')

    def erase_unit(self, uid: str, segment_id: str) -> None:
        reference = self._collection('jobs').document(segment_id)
        snapshot = reference.get()
        if not snapshot.exists:
            return
        job = snapshot.to_dict() or {}
        if job.get('owner_id') != uid or not is_owner_cancelled(job):
            raise UnitNotFenced('unit is not fenced for this owner')

        def fence(transaction: Any) -> None:
            current = reference.get(transaction=transaction)
            row = current.to_dict() or {}
            if current.exists and (row.get('owner_id') != uid or not is_owner_cancelled(row)):
                raise UnitNotFenced('unit fence changed before erasure')

        result = self._collection('results').document(segment_id).get().to_dict() or {}
        for uri in sorted(row_references(job) | row_references(result)):
            self.delete_uri(uid, uri)
            artifact = self._collection('artifacts').document(artifact_id(segment_id, uri)).get()
            if artifact.exists:
                data = artifact.to_dict() or {}
                if data.get('owner_id') not in (None, uid):
                    raise UnitNotFenced('artifact owner mismatch')
                erase_artifact(uid, self.namespace, artifact, data, self.delete_uri, fence=fence, client=self.client)
        delete_job(self.client, self.namespace, snapshot, retain_ordering=False, fence=fence)

    def erase_hold(self, uid: str, hold_id: str) -> None:
        from utils.sync.owner_cancel_legacy import FirestoreLegacyEraser

        FirestoreLegacyEraser().erase_hold(uid, hold_id)

    def erase_archives(self, uid: str, job_id: str, paths: tuple[str, ...] = ()) -> None:
        # Older receipts only have the router's job id. New receipts also record
        # the exact objects returned by create-only archive writes, including reused ones.
        self.delete_archives(uid, job_id.removeprefix(JOB_PREFIX), paths)
