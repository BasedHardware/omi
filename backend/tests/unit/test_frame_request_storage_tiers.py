"""Frame-request pixels use two separate tiers, over the neutral object-store port (ADR-0032).

Upstream's version of this test injected a fake GCS *client* and asserted on ``bucket.copy_blob``.
The port removed that shape — ``frame_request_storage`` now names buckets and calls
``put``/``copy``/``delete`` — so the assertions are re-expressed against the in-memory
``FakeObjectStore``. What is being proven is unchanged, and it is the thing that matters here: an
upload lands in the TEMPORARY bucket, promotion copies it into the PERMANENT one under a different
object name, and the delete removes the temporary object. The tiers must stay separate because the
temporary bucket is lifecycle-backed and the permanent one must have no expiration rule.
"""

import utils.other.storage as storage
from tests.object_store_fakes import FakeObjectStore
from utils.retrieval import frame_request_storage


def test_upload_delete_and_promotion_use_separate_buckets(monkeypatch):
    store = FakeObjectStore()
    monkeypatch.setenv("BUCKET_FRAME_REQUESTS", "permanent")
    monkeypatch.setenv("BUCKET_FRAME_REQUESTS_TEMPORARY", "temporary")
    # One patch point: the module reads the store through `utils.other.storage`, and so does the
    # owner write gate, so this single injection moves both.
    monkeypatch.setattr(storage, "_object_store", lambda: store)

    frame_request_storage.upload_frame_request_pixels("uid", "temporary-1", b"jpg", "image/jpeg")
    temporary_key = frame_request_storage._object_name("uid", "temporary-1")
    permanent_key = frame_request_storage._object_name("uid", "permanent-1")

    assert [info.key for info in store.list("temporary", "frame-requests/uid/")] == [temporary_key]
    assert store.get_bytes("temporary", temporary_key) == b"jpg"
    assert not store.list("permanent", "frame-requests/uid/")

    frame_request_storage.copy_frame_request_pixels_to_permanent("uid", "temporary-1", "permanent-1")

    # Promoted into the OTHER bucket, under a different object name, with the pixels intact.
    assert [info.key for info in store.list("permanent", "frame-requests/uid/")] == [permanent_key]
    assert permanent_key != temporary_key
    assert store.get_bytes("permanent", permanent_key) == b"jpg"

    frame_request_storage.delete_frame_request_pixels("uid", "temporary-1")

    assert not store.list("temporary", "frame-requests/uid/")
    assert store.exists("permanent", permanent_key)
