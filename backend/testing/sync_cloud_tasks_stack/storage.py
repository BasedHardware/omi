"""Filesystem-backed replacement for the external GCS boundary.

Production storage helpers still own blob naming and lifecycle decisions.  This
module replaces only the cloud client leaf before those helpers import it.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from google.api_core.exceptions import PreconditionFailed
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
    """Subset of the Google Cloud Storage blob API exercised by Sync v2 and batch.

    Object generations are the file's nanosecond mtime: positive, immutable for
    create-only objects, and shared by every process reading the same root.
    Generation preconditions follow GCS semantics (0 means "must not exist").
    """

    def __init__(self, bucket: 'LocalBucket', name: str, generation: int | None = None):
        self.bucket = bucket
        self.name = name
        self.metadata: Any = None
        self.cache_control: str | None = None
        self.content_type: str | None = None
        self.chunk_size: int | None = None
        self._pinned_generation = generation

    @property
    def generation(self) -> int | None:
        try:
            return self.path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    @property
    def size(self) -> int | None:
        return self.path.stat().st_size if self.path.is_file() else None

    def _check_generation(self, if_generation_match: int | None) -> None:
        current = self.generation
        if self._pinned_generation is not None and current != self._pinned_generation:
            raise BlobNotFound(self.name)
        if if_generation_match is None:
            return
        if if_generation_match == 0:
            if current is not None:
                raise PreconditionFailed(f'{self.name} already exists')
            return
        if current is None:
            raise BlobNotFound(self.name)
        if current != if_generation_match:
            raise PreconditionFailed(f'{self.name} generation mismatch')

    @property
    def path(self) -> Path:
        return _safe_blob_path(self.bucket.name, self.name)

    @property
    def public_url(self) -> str:
        return 'sync-stack://local-blob'

    def exists(self, *_args: Any, **_kwargs: Any) -> bool:
        return self.path.exists()

    def reload(self, *_args: Any, if_generation_match: int | None = None, **_kwargs: Any) -> None:
        if not self.exists():
            raise BlobNotFound(self.name)
        self._check_generation(if_generation_match)

    def upload_from_file(
        self,
        stream: Any,
        *_args: Any,
        content_type: str | None = None,
        if_generation_match: int | None = None,
        **_kwargs: Any,
    ) -> None:
        payload = stream.read()
        if isinstance(payload, str):
            payload = payload.encode()
        destination = self.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._check_generation(if_generation_match)
        staged = destination.with_name(destination.name + f'.upload-{os.getpid()}')
        staged.write_bytes(payload)
        try:
            if if_generation_match == 0:
                # Create-only: link fails atomically if another writer won.
                try:
                    os.link(staged, destination)
                except FileExistsError as error:
                    raise PreconditionFailed(f'{self.name} already exists') from error
            else:
                os.replace(staged, destination)
        finally:
            staged.unlink(missing_ok=True)
        self.content_type = content_type
        write_event('storage', {'event': 'blob_uploaded', 'bucket': self.bucket.name, 'bytes': len(payload)})

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

    def download_as_bytes(self, *_args: Any, if_generation_match: int | None = None, **_kwargs: Any) -> bytes:
        if not self.exists():
            raise BlobNotFound(self.name)
        self._check_generation(if_generation_match)
        payload = self.path.read_bytes()
        write_event('storage', {'event': 'blob_downloaded', 'bucket': self.bucket.name, 'bytes': len(payload)})
        return payload

    def delete(self, *_args: Any, if_generation_match: int | None = None, **_kwargs: Any) -> None:
        if if_generation_match is not None and self.path.exists():
            self._check_generation(if_generation_match)
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

    def blob(self, name: str, generation: int | None = None, **_kwargs: Any) -> LocalBlob:
        return LocalBlob(self, name, generation)

    def list_blobs(self, prefix: str = '', *_args: Any, **_kwargs: Any) -> Iterable[LocalBlob]:
        root = storage_dir() / self.name
        if not root.exists():
            return []
        blobs: list[LocalBlob] = []
        for path in root.rglob('*'):
            if path.is_file() and '.upload-' not in path.name:
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
