"""
Filesystem-backed fake Google Cloud Storage client for hermetic e2e tests.

The backend imports ``google.cloud.storage.Client`` at module import time in
``utils.other.storage``. ``patch_google_storage`` replaces that client before the
real app is imported, while this module keeps bucket/blob bytes under a temp dir.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable, Optional

# Module-level state
_storage_dir: Optional[str] = None


DEFAULT_BUCKETS = [
    "speech-profiles",
    "postprocessing",
    "backups",
    "plugins-logos",
    "omi-private-cloud-sync",
    "sync-temporal",
    "memories-recordings",
    "app-thumbnails",
    "chat-files",
    "desktop-updates",
]


def get_storage_dir() -> str:
    """Return the temp directory used as fake GCS bucket root."""
    if _storage_dir is None:
        raise RuntimeError("Fake storage not initialized — call setup_fake_storage() first")
    return _storage_dir


def setup_fake_storage() -> str:
    """Create a fresh temp directory for fake GCS storage."""
    global _storage_dir
    _storage_dir = tempfile.mkdtemp(prefix="omi_e2e_gcs_")
    for bucket_name in DEFAULT_BUCKETS:
        os.makedirs(os.path.join(_storage_dir, bucket_name), exist_ok=True)
    return _storage_dir


def teardown_fake_storage():
    """Remove the temp storage directory."""
    global _storage_dir
    if _storage_dir and os.path.exists(_storage_dir):
        shutil.rmtree(_storage_dir, ignore_errors=True)
    _storage_dir = None


def clear_fake_storage():
    """Clear all fake bucket contents while preserving bucket directories."""
    root = Path(get_storage_dir())
    for bucket in DEFAULT_BUCKETS:
        bucket_path = root / bucket
        if bucket_path.exists():
            shutil.rmtree(bucket_path, ignore_errors=True)
        bucket_path.mkdir(parents=True, exist_ok=True)


class FakeBlob:
    def __init__(self, bucket: "FakeBucket", name: str):
        self.bucket = bucket
        self.name = name
        self.metadata = None
        self.cache_control = None
        self.content_type = None

    @property
    def path(self) -> Path:
        return self.bucket.path / self.name

    @property
    def public_url(self) -> str:
        return f"https://fake-gcs.local/{self.bucket.name}/{self.name}"

    def exists(self, *args, **kwargs) -> bool:
        return self.path.exists()

    def reload(self, *args, **kwargs):
        if not self.exists():
            raise FileNotFoundError(self.name)
        return None

    def upload_from_filename(self, filename, *args, **kwargs):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filename, self.path)

    def download_to_filename(self, filename, *args, **kwargs):
        if not self.exists():
            raise FileNotFoundError(self.name)
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, filename)

    def upload_from_string(self, data, content_type=None, *args, **kwargs):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.content_type = content_type
        if isinstance(data, str):
            data = data.encode()
        self.path.write_bytes(data)

    def download_as_bytes(self, *args, **kwargs) -> bytes:
        if not self.exists():
            raise FileNotFoundError(self.name)
        return self.path.read_bytes()

    def delete(self, *args, **kwargs):
        if self.path.exists():
            self.path.unlink()

    def generate_signed_url(self, *args, **kwargs) -> str:
        return f"https://fake-gcs.local/{self.bucket.name}/{self.name}?signed=1"

    def make_public(self, *args, **kwargs):
        return None

    def patch(self, *args, **kwargs):
        return None


class FakeBucket:
    def __init__(self, name: str):
        self.name = name
        self.path.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return Path(get_storage_dir()) / self.name

    def blob(self, name: str) -> FakeBlob:
        return FakeBlob(self, name)

    def list_blobs(self, prefix: str = "", *args, **kwargs) -> Iterable[FakeBlob]:
        if not self.path.exists():
            return []
        blobs = []
        for file_path in self.path.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(self.path).as_posix()
            if rel.startswith(prefix):
                blobs.append(FakeBlob(self, rel))
        return blobs


class FakeStorageClient:
    def __init__(self, *args, **kwargs):
        get_storage_dir()

    def bucket(self, name: str) -> FakeBucket:
        return FakeBucket(name)

    def get_bucket(self, name: str) -> FakeBucket:
        return self.bucket(name)


def patch_google_storage():
    """Patch google.cloud.storage.Client to return the filesystem fake."""
    from google.cloud import storage

    storage.Client = FakeStorageClient


def fake_upload_blob(bucket_name: str, source_file: str, destination_blob_name: str):
    FakeStorageClient().bucket(bucket_name).blob(destination_blob_name).upload_from_filename(source_file)


def fake_download_blob(bucket_name: str, source_blob_name: str, destination_file: str):
    blob = FakeStorageClient().bucket(bucket_name).blob(source_blob_name)
    if blob.exists():
        blob.download_to_filename(destination_file)
        return True
    return False


def fake_delete_blob(bucket_name: str, blob_name: str):
    FakeStorageClient().bucket(bucket_name).blob(blob_name).delete()
    return True


def fake_blob_exists(bucket_name: str, blob_name: str) -> bool:
    return FakeStorageClient().bucket(bucket_name).blob(blob_name).exists()


def list_storage_files(bucket_name: str, prefix: str = "") -> list:
    return [blob.name for blob in FakeStorageClient().bucket(bucket_name).list_blobs(prefix=prefix)]
