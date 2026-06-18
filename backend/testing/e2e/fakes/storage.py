"""
Fake GCS (Google Cloud Storage) using a local temp directory.

Replaces google.cloud.storage.Client with a filesystem-backed
implementation. Uploads write to temp dir, downloads read from it,
and deletes remove files.
"""

import os
import shutil
import tempfile
from typing import Optional

# Module-level state
_storage_dir: Optional[str] = None


def get_storage_dir() -> str:
    """Return the temp directory used as fake GCS bucket."""
    if _storage_dir is None:
        raise RuntimeError("Fake storage not initialized — call setup_fake_storage() first")
    return _storage_dir


def setup_fake_storage() -> str:
    """Create a fresh temp directory for fake GCS storage."""
    global _storage_dir
    _storage_dir = tempfile.mkdtemp(prefix="omi_e2e_gcs_")

    # Create bucket subdirectories that the backend expects
    for bucket_name in ["speech-profiles", "postprocessing", "backups", "plugins-logos"]:
        os.makedirs(os.path.join(_storage_dir, bucket_name), exist_ok=True)

    return _storage_dir


def teardown_fake_storage():
    """Remove the temp storage directory."""
    global _storage_dir
    if _storage_dir and os.path.exists(_storage_dir):
        shutil.rmtree(_storage_dir, ignore_errors=True)
    _storage_dir = None


def fake_upload_blob(bucket_name: str, source_file: str, destination_blob_name: str):
    """Fake blob upload — copies file to storage dir."""
    dest = os.path.join(get_storage_dir(), bucket_name, destination_blob_name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(source_file, dest)


def fake_download_blob(bucket_name: str, source_blob_name: str, destination_file: str):
    """Fake blob download — copies file from storage dir."""
    src = os.path.join(get_storage_dir(), bucket_name, source_blob_name)
    if os.path.exists(src):
        shutil.copy2(src, destination_file)
        return True
    return False


def fake_delete_blob(bucket_name: str, blob_name: str):
    """Fake blob deletion — removes file from storage dir."""
    path = os.path.join(get_storage_dir(), bucket_name, blob_name)
    if os.path.exists(path):
        os.remove(path)
    return True


def fake_blob_exists(bucket_name: str, blob_name: str) -> bool:
    """Check if a fake blob exists."""
    path = os.path.join(get_storage_dir(), bucket_name, blob_name)
    return os.path.exists(path)


def list_storage_files(bucket_name: str, prefix: str = "") -> list:
    """List files in a fake bucket with optional prefix filter."""
    base = os.path.join(get_storage_dir(), bucket_name)
    if not os.path.exists(base):
        return []
    results = []
    for root, dirs, files in os.walk(base):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, base)
            if rel_path.startswith(prefix):
                results.append(rel_path)
    return results
