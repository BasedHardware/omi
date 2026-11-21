import argparse
import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from database import support_actions
from database.support_actions import ActionContext, ActionRecord
from utils.support import dsar_export

UID = "uid1234567890abcdef"
NOW = datetime(2026, 11, 20, 12, 30, 0, tzinfo=timezone.utc)
SECRET_TEXT = "my private note about [brackets] and \"quotes\" {x}"

EXPORT = {
    "profile": {"name": "Pat", "notes": SECRET_TEXT},
    "conversations": [{"id": "c1", "text": SECRET_TEXT}, {"id": "c2", "nested": [1, 2, {"a": []}]}],
    "memories": [{"content": "remember \\ this"}],
    "memory_review_data": {"memory_review_items": [], "memory_review_decisions": [{"d": 1}]},
    "task_data": {"tasks": [{"t": 1}, {"t": 2}], "task_events": [{"e": "x"}]},
    "people": [],
    "chat_messages": [{"text": "hi"}, {"text": "]"}, {"text": "}"}],
}


def _export_text():
    text = json.dumps(EXPORT, indent=2)
    # Chunk boundaries inside strings and escapes must not matter.
    return [text[i : i + 7] for i in range(0, len(text), 7)]


class FakeBlob:
    def __init__(self, bucket, name, data=b""):
        self.bucket = bucket
        self.name = name
        self.data = data
        self.size = len(data)
        self.metadata = None
        self.uploads = []
        self.signed = []

    def download_as_bytes(self):
        return self.data

    def download_to_file(self, writer):
        for i in range(0, len(self.data), 3):
            writer.write(self.data[i : i + 3])

    def upload_from_filename(self, path, content_type=None, if_generation_match=None):
        with open(path, "rb") as handle:
            self.data = handle.read()
        self.size = len(self.data)
        self.uploads.append({"content_type": content_type, "if_generation_match": if_generation_match})

    def generate_signed_url(self, **kwargs):
        self.signed.append(kwargs)
        return f"https://signed.example/{self.name}?sig=abc"


class FakeBucket:
    def __init__(self, client, name):
        self.client = client
        self.name = name

    def blob(self, name):
        blob = FakeBlob(self, name)
        self.client.created.append(blob)
        return blob


class FakeClient:
    def __init__(self, objects):
        self.objects = objects
        self.created = []
        self.listed = []

    def bucket(self, name):
        return FakeBucket(self, name)

    def list_blobs(self, bucket, prefix):
        self.listed.append((bucket.name, prefix))
        return [FakeBlob(bucket, name, data) for name, data in self.objects.items() if name.startswith(prefix)]


class FakeCredentials:
    def __init__(self, email="support-operator@based-hardware.iam.gserviceaccount.com"):
        self.valid = True
        self.service_account_email = email
        self.token = "ya29.token"


AUDIO = {
    f"chunks/{UID}/conv1/1700000000.000.opus.enc": b"ENC:opus-bytes",
    f"chunks/{UID}/conv1/1700000001.000.bin": b"raw-pcm-bytes",
    f"chunks/{UID}/conv1/1700000002.000.batch.enc": b"ENC:pcm-batch",
    f"playback/{UID}/conv1/conversation.mp3": b"ID3mp3",
    f"playback/{UID}/conv1/conversation.unavailable": b"marker",
    "chunks/otheruid/conv9/1.bin": b"not-this-account",
}


def _decrypt(data, uid):
    assert uid == UID
    if not data.startswith(b"ENC:"):
        raise ValueError("bad tag")
    return b"PLAIN:" + data[4:]


def _args(**overrides):
    values = {"uid": UID, "approval": "note-4242", "audio": True, "url_days": 7}
    values.update(overrides)
    return argparse.Namespace(**values)


def _ctx(apply):
    return ActionContext(ticket="215123", actor="agent-a", reason="DSAR", agent="operator", apply=apply)


@pytest.fixture
def seams():
    client = FakeClient(dict(AUDIO))
    with patch.object(dsar_export, "_storage_client", return_value=client), patch.object(
        dsar_export, "_credentials", return_value=FakeCredentials()
    ), patch.object(dsar_export, "_export_chunks", side_effect=lambda uid: iter(_export_text())), patch.object(
        dsar_export, "_decrypt_audio", side_effect=_decrypt
    ), patch.object(
        dsar_export, "_now", return_value=NOW
    ), patch.object(
        dsar_export, "private_archive_bucket", return_value="omi-private-cloud-sync"
    ):
        yield client


def _uploaded(client):
    uploaded = [blob for blob in client.created if blob.uploads]
    assert len(uploaded) == 1
    return uploaded[0]


def test_section_counter_matches_json_structure():
    counter = dsar_export.SectionCounter()
    for chunk in _export_text():
        counter.feed(chunk)
    assert counter.counts == {
        "profile": 1,
        "conversations": 2,
        "memories": 1,
        "memory_review_data": {"memory_review_items": 0, "memory_review_decisions": 1},
        "task_data": {"tasks": 2, "task_events": 1},
        "people": 0,
        "chat_messages": 3,
    }
    assert dsar_export._section_totals(counter.counts)["task_data"] == 3


def test_section_counter_ignores_scalars_and_empty_objects():
    counter = dsar_export.SectionCounter()
    counter.feed('{"profile": {}, "a": [], "jit_data": {}, "export_complete": true}')
    # An object with no arrays inside is one record (an empty profile still exists).
    assert counter.counts == {"profile": 1, "a": 0, "jit_data": 1}


def test_profile_with_array_fields_is_one_record():
    counter = dsar_export.SectionCounter()
    counter.feed('{"profile": {"platforms_used": ["ios", "macos"], "name": "x"}, "memories": [{}]}')
    assert counter.counts == {"profile": 1, "memories": 1}


def test_dry_run_writes_nothing(seams):
    record = ActionRecord(action_id="a1")
    result = dsar_export.export(_args(), _ctx(apply=False), record)

    assert seams.created == []  # no blob handle was even created for writing
    assert result["dry_run"] is True
    assert result["sections"]["conversations"] == 2
    assert result["sections"]["task_data"] == 3
    assert result["audio_objects"] == 4  # marker file and other account excluded
    assert result["audio_stored_bytes"] == sum(
        len(data) for name, data in AUDIO.items() if UID in name and not name.endswith(".unavailable")
    )
    assert record.after_digest is None
    assert record.summary["dry_run"] is True
    assert record.summary["approval"] == "note-4242"
    assert ("omi-private-cloud-sync", f"chunks/{UID}/") in seams.listed
    assert ("omi-private-cloud-sync", f"playback/{UID}/") in seams.listed


def test_apply_uploads_with_generation_precondition_and_signs(seams):
    record = ActionRecord(action_id="a2")
    result = dsar_export.export(_args(url_days=3), _ctx(apply=True), record)

    blob = _uploaded(seams)
    assert blob.bucket.name == "based-hardware-privacy-exports"
    assert blob.name == f"215123/{UID[:6]}-20261120T123000Z.zip"
    assert blob.uploads == [{"content_type": "application/zip", "if_generation_match": 0}]
    assert blob.signed == [
        {
            "version": "v4",
            "expiration": timedelta(days=3),
            "method": "GET",
            "service_account_email": "support-operator@based-hardware.iam.gserviceaccount.com",
            "access_token": "ya29.token",
        }
    ]
    zip_sha = hashlib.sha256(blob.data).hexdigest()
    assert result["object"] == f"gs://based-hardware-privacy-exports/{blob.name}"
    assert result["zip_sha256"] == zip_sha
    assert result["zip_bytes"] == len(blob.data)
    assert result["signed_url"].startswith("https://signed.example/")
    assert result["url_expires_at"] == (NOW + timedelta(days=3)).isoformat()
    assert result["audio_objects"] == 4
    assert result["sections"]["chat_messages"] == 3
    assert record.after_digest == zip_sha
    assert record.summary["zip_bytes"] == len(blob.data)
    assert record.summary["url_days"] == 3


def test_manifest_matches_every_file_and_audio_is_decrypted(seams):
    dsar_export.export(_args(), _ctx(apply=True), ActionRecord(action_id="a3"))
    archive = zipfile.ZipFile(io.BytesIO(_uploaded(seams).data))

    names = set(archive.namelist())
    assert names == {
        "export.json",
        "README.txt",
        "MANIFEST.sha256",
        "audio/chunks/conv1/1700000000.000.opus",
        "audio/chunks/conv1/1700000001.000.bin",
        "audio/chunks/conv1/1700000002.000.batch.bin",
        "audio/playback/conv1/conversation.mp3",
    }
    manifest = {}
    for line in archive.read("MANIFEST.sha256").decode().splitlines():
        sha, name = line.split("  ", 1)
        manifest[name] = sha
    assert set(manifest) == names - {"MANIFEST.sha256"}
    for name, sha in manifest.items():
        assert hashlib.sha256(archive.read(name)).hexdigest() == sha

    assert json.loads(archive.read("export.json")) == EXPORT
    assert archive.read("audio/chunks/conv1/1700000000.000.opus") == b"PLAIN:opus-bytes"
    assert archive.read("audio/chunks/conv1/1700000001.000.bin") == b"raw-pcm-bytes"
    readme = archive.read("README.txt").decode()
    assert "Generated at (UTC): 2026-11-20T12:30:00Z" in readme
    assert "Decrypted objects: 2" in readme
    assert "Not included:" in readme
    assert "raw-live" in readme and "derived audio" in readme


def test_signing_failure_uploads_nothing(seams, monkeypatch):
    def refuse(self, **kwargs):
        raise RuntimeError("signBlob denied")

    monkeypatch.setattr(FakeBlob, "generate_signed_url", refuse)
    with pytest.raises(RuntimeError):
        dsar_export.export(_args(), _ctx(apply=True), ActionRecord(action_id="a6"))
    assert not [blob for blob in seams.created if blob.uploads]


def test_conversation_wav_recordings_are_exported(seams):
    seams.objects[f"{UID}/conv1.wav"] = b"RIFF-wav"
    dsar_export.export(_args(), _ctx(apply=True), ActionRecord(action_id="a5"))
    archive = zipfile.ZipFile(io.BytesIO(_uploaded(seams).data))
    assert archive.read("audio/recordings/conv1.wav") == b"RIFF-wav"
    assert ("memories-recordings", f"{UID}/") in seams.listed


def test_undecryptable_object_is_kept_and_flagged(seams):
    seams.objects[f"chunks/{UID}/conv1/1700000003.000.enc"] = b"garbage"
    result = dsar_export.export(_args(), _ctx(apply=True), ActionRecord(action_id="a4"))
    archive = zipfile.ZipFile(io.BytesIO(_uploaded(seams).data))

    assert archive.read("audio/chunks/conv1/1700000003.000.enc") == b"garbage"
    assert "audio/chunks/conv1/1700000003.000.enc" in archive.read("README.txt").decode()
    assert result["audio_undecryptable"] == 1


def test_no_audio_excludes_audio(seams):
    result = dsar_export.export(_args(audio=False), _ctx(apply=True), ActionRecord(action_id="a5"))
    archive = zipfile.ZipFile(io.BytesIO(_uploaded(seams).data))
    assert not [name for name in archive.namelist() if name.startswith("audio/")]
    assert seams.listed == []
    assert result["audio_objects"] == 0


@pytest.mark.parametrize("approval", ["", "   ", None])
def test_missing_approval_fails_before_any_read(seams, approval):
    with patch.object(dsar_export, "_export_chunks") as export_chunks:
        with pytest.raises(dsar_export.DsarExportError, match="approval"):
            dsar_export.export(_args(approval=approval), _ctx(apply=True), ActionRecord(action_id="a6"))
    export_chunks.assert_not_called()
    assert seams.created == []


@pytest.mark.parametrize("days", [8, 0, 30])
def test_url_days_out_of_range_refused(seams, days):
    with pytest.raises(dsar_export.DsarExportError, match="url-days"):
        dsar_export.export(_args(url_days=days), _ctx(apply=True), ActionRecord(action_id="a7"))
    assert seams.created == []


def _parser():
    parser = argparse.ArgumentParser()
    dsar_export.register(parser.add_subparsers(dest="group", required=True))
    return parser


def test_cli_parsing_and_refusals():
    args = _parser().parse_args(["dsar", "export", UID, "--approval", "n1", "--no-audio"])
    assert (args.action, args.handler, args.audio, args.url_days) == ("export", dsar_export.export, False, 7)
    with pytest.raises(SystemExit):
        _parser().parse_args(["dsar", "export", UID])
    with pytest.raises(SystemExit):
        _parser().parse_args(["dsar", "export", UID, "--approval", "n1", "--url-days", "8"])


def test_credentials_that_cannot_sign_fail_before_export(seams):
    with patch.object(dsar_export, "_credentials", return_value=FakeCredentials(email=None)), patch.object(
        dsar_export, "_export_chunks"
    ) as export_chunks:
        with pytest.raises(dsar_export.DsarExportError, match="signBlob"):
            dsar_export.export(_args(), _ctx(apply=True), ActionRecord(action_id="a8"))
    export_chunks.assert_not_called()
    assert seams.created == []


def test_summary_is_content_free(seams):
    record = ActionRecord(action_id="a9")
    result = dsar_export.export(_args(), _ctx(apply=True), record)

    serialized = json.dumps(record.summary)
    for forbidden in (result["signed_url"], "signed.example", UID, UID[:6], "Pat", "brackets", "PLAIN", "ya29"):
        assert forbidden not in serialized
    # Every value survives the audit layer as-is (flat scalars, no digests).
    assert support_actions._content_free_summary(record.summary) == record.summary
    assert record.summary["approval"] == "note-4242"
    assert record.summary["audio_objects"] == 4
    assert record.summary["section_conversations"] == 2
    assert {"sections", "section_records", "zip_bytes", "url_days"} <= set(record.summary)


def test_module_imports_need_no_encryption_secret():
    # utils.encryption raises at import without ENCRYPTION_SECRET; hold, retention and
    # account commands load this module through the CLI and must not need the secret.
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(dsar_export.__file__).read_text())
    top = {node.module for node in tree.body if isinstance(node, ast.ImportFrom)}
    top |= {alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names}
    assert not top & {"utils", "utils.encryption", "services.users.data_export", "database.chat"}
