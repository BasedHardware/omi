from utils.retrieval import frame_request_storage


class _Blob:
    def __init__(self, name):
        self.name = name
        self.uploads = []
        self.deleted = 0

    def upload_from_string(self, data, content_type=None):
        self.uploads.append((data, content_type))

    def delete(self):
        self.deleted += 1

    def download_as_bytes(self):
        return self.name.encode()


class _Bucket:
    def __init__(self, name):
        self.name = name
        self.blobs = {}
        self.copies = []

    def blob(self, name):
        return self.blobs.setdefault(name, _Blob(name))

    def copy_blob(self, source, destination, new_name):
        self.copies.append((source.name, destination.name, new_name))


class _Storage:
    def __init__(self):
        self.buckets = {}

    def bucket(self, name):
        return self.buckets.setdefault(name, _Bucket(name))


def test_upload_delete_and_promotion_use_separate_buckets(monkeypatch):
    storage = _Storage()
    monkeypatch.setenv("BUCKET_FRAME_REQUESTS", "permanent")
    monkeypatch.setenv("BUCKET_FRAME_REQUESTS_TEMPORARY", "temporary")
    monkeypatch.setattr(frame_request_storage, "_get_storage_client", lambda: storage)

    frame_request_storage.upload_frame_request_pixels("uid", "temporary-1", b"jpg", "image/jpeg")
    frame_request_storage.copy_frame_request_pixels_to_permanent("uid", "temporary-1", "permanent-1")
    frame_request_storage.delete_frame_request_pixels("uid", "temporary-1")

    assert len(storage.buckets["temporary"].blobs) == 1
    source_name, destination_bucket, destination_name = storage.buckets["temporary"].copies[0]
    assert source_name.startswith("frame-requests/uid/")
    assert destination_bucket == "permanent"
    assert destination_name.startswith("frame-requests/uid/")
    assert destination_name != source_name
    assert next(iter(storage.buckets["temporary"].blobs.values())).deleted == 1
