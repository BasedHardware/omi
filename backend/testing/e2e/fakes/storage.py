"""
Filesystem-backed fake Google Cloud Storage client for hermetic e2e tests.

Implementation lives in ``utils.other.fake_gcs`` so production/runtime images
can import it without pulling ``testing.*`` into deployable closures (#11703).
"""

from utils.other.fake_gcs import (  # noqa: F401
    DEFAULT_BUCKETS,
    FakeBlob,
    FakeBucket,
    FakeStorageClient,
    clear_fake_storage,
    fake_blob_exists,
    fake_delete_blob,
    fake_download_blob,
    fake_upload_blob,
    get_storage_dir,
    list_storage_files,
    patch_google_storage,
    setup_fake_storage,
    teardown_fake_storage,
)
