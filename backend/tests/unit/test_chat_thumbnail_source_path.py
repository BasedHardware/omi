"""Regression for thumbnails generated in the system temp directory."""

from pathlib import Path
from unittest.mock import MagicMock

from utils.other import storage


def test_upload_multi_chat_files_uploads_the_supplied_path(monkeypatch, tmp_path):
    source = tmp_path / "random_upload_thumbnail.png"
    source.write_bytes(b"png")
    blob = MagicMock()
    bucket = MagicMock()
    bucket.blob.return_value = blob
    monkeypatch.setattr(storage, "_get_storage_client", lambda: MagicMock(bucket=lambda _: bucket))
    monkeypatch.setattr(storage, "chat_files_bucket", "chat-files")
    monkeypatch.setattr(storage, "_blob_public_url", lambda *_args: "https://example/thumb.png")
    monkeypatch.setattr(storage, "owner_storage_write_gate", MagicMock())

    storage.upload_multi_chat_files([str(source)], "user-1")

    blob.upload_from_filename.assert_called_once_with(str(source))
    bucket.blob.assert_called_once_with("user-1/random_upload_thumbnail.png")
