"""Filesystem-backed replacement for the external GCS boundary.

Production storage helpers still own blob naming and lifecycle decisions.  This
module replaces only the cloud client leaf before those helpers import it.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from google.cloud.exceptions import NotFound as BlobNotFound

from .events import write_event

_storage_dir: Path | None = None


def configure_storage_dir(path: str | Path) -> Path:
    """Set up the shared local bucket root once per ASGI process."""
    global _storage_dir
    root = Path(path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    _storage_dir = root
    return root


def storage_dir() -> Path:
    if _storage_dir is None:
        configured = os.getenv('OMI_SYNC_STACK_STORAGE_DIR', '').strip()
        if not configured:
            raise RuntimeError('OMI_SYNC_STACK_STORAGE_DIR is required for local storage')
        return configure_storage_dir(configured)
    return _storage_dir


def _safe_blob_path(bucket: str, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('local storage rejects absolute or parent blob paths')
    return storage_dir() / bucket / Path(*relative.parts)


class LocalBlob:
    """Subset of the Google Cloud Storage blob API exercised by Sync v2."""

    def __init__(self, bucket: 'LocalBucket', name: str):
        self.bucket = bucket
        self.name = name
        self.metadata: Any = None
        self.cache_control: str | None = None
        self.content_type: str | None = None

    @property
    def path(self) -> Path:
        return _safe_blob_path(self.bucket.name, self.name)

    @property
    def public_url(self) -> str:
        return 'sync-stack://local-blob'

    def exists(self, *_args: Any, **_kwargs: Any) -> bool:
        return self.path.exists()

    def reload(self, *_args: Any, **_kwargs: Any) -> None:
        if not self.exists():
            raise BlobNotFound(self.name)

    def upload_from_filename(self, filename: str, *_args: Any, **_kwargs: Any) -> None:
        destination = self.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filename, destination)
        write_event(
            'storage', {'event': 'blob_uploaded', 'bucket': self.bucket.name, 'bytes': destination.stat().st_size}
        )

    def download_to_filename(self, filename: str, *_args: Any, **_kwargs: Any) -> None:
        if not self.exists():
            raise BlobNotFound(self.name)
        destination = Path(filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, destination)
        write_event(
            'storage', {'event': 'blob_downloaded', 'bucket': self.bucket.name, 'bytes': self.path.stat().st_size}
        )

    def upload_from_string(
        self, data: bytes | str, content_type: str | None = None, *_args: Any, **_kwargs: Any
    ) -> None:
        destination = self.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = data.encode() if isinstance(data, str) else data
        destination.write_bytes(payload)
        self.content_type = content_type
        write_event('storage', {'event': 'blob_uploaded', 'bucket': self.bucket.name, 'bytes': len(payload)})

    def download_as_bytes(self, *_args: Any, **_kwargs: Any) -> bytes:
        if not self.exists():
            raise BlobNotFound(self.name)
        payload = self.path.read_bytes()
        write_event('storage', {'event': 'blob_downloaded', 'bucket': self.bucket.name, 'bytes': len(payload)})
        return payload

    def delete(self, *_args: Any, **_kwargs: Any) -> None:
        if self.path.exists():
            self.path.unlink()
        write_event('storage', {'event': 'blob_deleted', 'bucket': self.bucket.name})

    def generate_signed_url(self, *_args: Any, **_kwargs: Any) -> str:
        # The deterministic STT leaf consumes this opaque local-only value.
        job_id = PurePosixPath(self.name).parent.name
        return f'sync-stack://staged/{job_id}' if job_id else 'sync-stack://staged'

    def make_public(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def patch(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class LocalBucket:
    def __init__(self, name: str):
        self.name = name
        (storage_dir() / name).mkdir(parents=True, exist_ok=True)

    def blob(self, name: str) -> LocalBlob:
        return LocalBlob(self, name)

    def list_blobs(self, prefix: str = '', *_args: Any, **_kwargs: Any) -> Iterable[LocalBlob]:
        root = storage_dir() / self.name
        if not root.exists():
            return []
        blobs: list[LocalBlob] = []
        for path in root.rglob('*'):
            if path.is_file():
                name = path.relative_to(root).as_posix()
                if name.startswith(prefix):
                    blobs.append(LocalBlob(self, name))
        return blobs


class LocalStorageClient:
    """Lazy storage client instantiated by the production storage helpers."""

    def __init__(self, *_args: Any, **_kwargs: Any):
        storage_dir()

    def bucket(self, name: str) -> LocalBucket:
        return LocalBucket(name)

    def get_bucket(self, name: str) -> LocalBucket:
        return self.bucket(name)


def patch_google_storage() -> None:
    """Install the local client before ``utils.other.storage`` is imported."""
    from google.cloud import storage

    storage.Client = LocalStorageClient
