"""S3 uploads must stream (bounded memory) instead of holding the whole object in RAM: a stream put
and the open_write() writer both go through multipart-capable upload_fileobj, not put_object(data.read())
(cubic review PR 10887, backend/utils/object_store/adapters/s3.py)."""

import io

import utils.object_store.adapters.s3 as s3


class _FakeS3:
    def __init__(self):
        self.put_object_calls = []
        self.upload_fileobj_calls = []

    def put_object(self, **kwargs):
        self.put_object_calls.append(kwargs)

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        self.upload_fileobj_calls.append({"bucket": bucket, "key": key, "body": fileobj.read(), "extra": ExtraArgs})


def _patch(monkeypatch):
    fake = _FakeS3()
    monkeypatch.setattr(s3, "_s3", lambda: fake)
    return fake


def test_put_stream_uses_multipart_upload_fileobj(monkeypatch):
    fake = _patch(monkeypatch)
    s3.S3ObjectStore().put("bkt", "audio/clip.wav", io.BytesIO(b"streamed-bytes"), content_type="audio/wav")
    assert fake.put_object_calls == []  # not read into memory + put_object
    assert len(fake.upload_fileobj_calls) == 1
    call = fake.upload_fileobj_calls[0]
    assert (call["bucket"], call["key"], call["body"]) == ("bkt", "audio/clip.wav", b"streamed-bytes")
    assert call["extra"]["ContentType"] == "audio/wav"


def test_put_bytes_still_uses_put_object(monkeypatch):
    fake = _patch(monkeypatch)
    s3.S3ObjectStore().put("bkt", "k", b"small-bytes", content_type="text/plain")
    assert fake.upload_fileobj_calls == []
    assert len(fake.put_object_calls) == 1
    assert fake.put_object_calls[0]["Body"] == b"small-bytes"


def test_open_write_streams_via_upload_fileobj(monkeypatch):
    fake = _patch(monkeypatch)
    with s3.S3ObjectStore().open_write("bkt", "k/audio.wav", content_type="audio/wav") as w:
        w.write(b"chunk-1 ")
        w.write(b"chunk-2")
    assert len(fake.upload_fileobj_calls) == 1
    call = fake.upload_fileobj_calls[0]
    assert (call["bucket"], call["key"], call["body"]) == ("bkt", "k/audio.wav", b"chunk-1 chunk-2")
