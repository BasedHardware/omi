from typing import List, Optional
from google.cloud.firestore import Batch
from google.api_core.exceptions import BatchError

BATCH_LIMIT = 500

class ChatFileManager:
    def __init__(self, db):
        self.db = db

    def _chunk_batches(self, file_ids: List[str], operation: str) -> List[Batch]:
        """Split file operations into batches of max BATCH_LIMIT."""
        batches = []
        for i in range(0, len(file_ids), BATCH_LIMIT):
            batch = self.db.batch()
            chunk = file_ids[i:i + BATCH_LIMIT]
            for file_id in chunk:
                ref = self.db.collection('chat_files').document(file_id)
                if operation == 'add':
                    batch.set(ref, {'status': 'uploading'})
                elif operation == 'delete':
                    batch.delete(ref)
            batches.append(batch)
        return batches

    def add_multi_files(self, file_ids: List[str]) -> None:
        """Add multiple chat files with batch chunking."""
        if not file_ids:
            return

        batches = self._chunk_batches(file_ids, 'add')
        for batch in batches:
            try:
                batch.commit()
            except BatchError as e:
                raise ValueError(f"Batch commit failed: {str(e)}") from e

    def delete_multi_files(self, file_ids: List[str]) -> None:
        """Delete multiple chat files with batch chunking."""
        if not file_ids:
            return

        batches = self._chunk_batches(file_ids, 'delete')
        for batch in batches:
            try:
                batch.commit()
            except BatchError as e:
                raise ValueError(f"Batch commit failed: {str(e)}") from e