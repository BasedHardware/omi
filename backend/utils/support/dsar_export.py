"""``dsar export``: an operator-side GDPR Article 15 data copy for one account.

    scripts/support/ops.py ... dsar export UID --approval NOTE_ID [--audio/--no-audio] [--url-days 7] [--apply]

The JSON body is produced by the same code path as the in-app "Export All Data"
(``GET /v1/users/export`` -> ``services.users.data_export.iter_user_data_export``),
so the operator copy contains exactly what the owner would download. With
``--audio`` the account's retained audio objects under ``chunks/{uid}/`` and
``playback/{uid}/`` in the private-cloud-sync bucket are added; encrypted chunk
objects are decrypted one object at a time with ``utils.encryption`` and kept in
their stored codec.

Without ``--apply`` the command is a dry run: it builds the export locally to
count sections and lists audio objects, and writes nothing to GCS. With
``--apply`` it streams a zip to a local temp file, uploads it to
``gs://based-hardware-privacy-exports/{ticket}/{uid[:6]}-{UTC}.zip`` with
``if_generation_match=0`` and returns a V4 signed GET URL signed through IAM
``signBlob`` with the operator's credentials (never a JSON key).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from typing import IO, Any, Iterable, Iterator

import google.auth
from google.auth.transport import requests as google_auth_requests
from google.cloud import storage

from config.record_wal_storage import private_archive_bucket
from database.audio_timeline import get_extension_for_path
from database.support_actions import ActionContext, ActionRecord

EXPORT_BUCKET = "based-hardware-privacy-exports"
MAX_URL_DAYS = 7
DEFAULT_URL_DAYS = 7
AUDIO_PREFIXES = ("chunks", "playback")
CHUNK_EXTENSIONS = (".batch.enc", ".batch.bin", ".opus.enc", ".opus", ".enc", ".bin")
PLAYBACK_EXTENSIONS = (".mp3",)
# Conversation recordings: {uid}/{conversation_id}.wav in BUCKET_MEMORIES_RECORDINGS.
DEFAULT_MEMORIES_RECORDINGS_BUCKET = "memories-recordings"
RECORDING_EXTENSIONS = (".wav",)
# Encrypted stored extension -> extension of the decrypted bytes (same codec as
# the unencrypted variant the pipeline writes).
_DECRYPTED_SUFFIX = {"batch.enc": ".batch.bin", "opus.enc": ".opus", "enc": ".bin"}
_SUMMARY_SECTIONS = ("conversations", "memories", "chat_messages", "action_items", "people")
_SINGLE_RECORD_SECTIONS = frozenset({"profile"})
_COPY_CHUNK = 1024 * 1024
_TICKET_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class DsarExportError(RuntimeError):
    """The export request is invalid or could not be completed safely."""


# --- seams (tests patch these with patch.object) -----------------------------


def _credentials() -> Any:
    """Operator ADC with the cloud-platform scope (needed for IAM signBlob)."""

    credentials, _project = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    return credentials


def _storage_client() -> Any:
    return storage.Client(credentials=_credentials())


def _export_chunks(uid: str) -> Iterator[str]:
    """The in-app export body, eagerly validated and spooled by the service."""

    # Imported here: the data-export chain imports utils.encryption, which needs
    # ENCRYPTION_SECRET at import time. Other operator commands must not need it.
    from services.users.data_export import iter_user_data_export
    from utils.other.portability_read import PortabilityReadContext

    return iter_user_data_export(uid, read_context=PortabilityReadContext())


def _decrypt_audio(data: bytes, uid: str) -> bytes:
    from utils import encryption

    return encryption.decrypt_audio_file(data, uid)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- CLI ---------------------------------------------------------------------


def _url_days(value: str) -> int:
    try:
        days = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--url-days must be an integer") from exc
    if not 1 <= days <= MAX_URL_DAYS:
        raise argparse.ArgumentTypeError(f"--url-days must be between 1 and {MAX_URL_DAYS}")
    return days


def register(groups: Any) -> None:
    group = groups.add_parser("dsar", help="data subject access requests (GDPR Article 15)")
    commands = group.add_subparsers(dest="dsar_command", required=True)
    export_parser = commands.add_parser("export", help="build and upload a data copy for one account")
    export_parser.add_argument("uid")
    export_parser.add_argument(
        "--approval", required=True, help="reference to the recorded approval (Intercom note id)"
    )
    export_parser.add_argument(
        "--audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="include retained audio objects (default: on)",
    )
    export_parser.add_argument(
        "--url-days", type=_url_days, default=DEFAULT_URL_DAYS, help=f"signed URL lifetime, 1-{MAX_URL_DAYS} days"
    )
    export_parser.set_defaults(action="export", handler=export)


# --- section counting ----------------------------------------------------------


class SectionCounter:
    """Count top-level export sections from a JSON text stream in O(depth) memory.

    A top-level array counts its elements; a top-level object whose values are
    arrays (``task_data``, ``jit_data``...) counts each array; any other
    top-level object counts as one record. Scalars (``export_complete``) are
    not sections.
    """

    def __init__(self) -> None:
        self.counts: dict[str, Any] = {}
        self._stack: list[str] = []
        self._expect_key: list[bool] = []
        self._expect_value: list[bool] = []
        self._in_string = False
        self._escape = False
        self._key_buf: list[str] | None = None
        self._keys: list[str | None] = [None, None]

    def feed(self, text: str) -> None:
        for ch in text:
            if self._in_string:
                if self._escape:
                    self._escape = False
                    if self._key_buf is not None:
                        self._key_buf.append(ch)
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
                    if self._key_buf is not None:
                        self._keys[len(self._stack) - 1] = "".join(self._key_buf)
                        self._key_buf = None
                elif self._key_buf is not None:
                    self._key_buf.append(ch)
                continue
            if ch in " \t\r\n":
                continue
            depth = len(self._stack)
            if depth and self._stack[-1] == "{" and self._expect_key[-1]:
                if ch == '"':
                    self._in_string = True
                    self._expect_key[-1] = False
                    self._key_buf = [] if depth <= 2 else None
                # '}' closing an empty object falls through below.
                if ch != "}":
                    continue
            if ch == ":":
                self._expect_value[-1] = True
                continue
            if ch == ",":
                if self._stack[-1] == "{":
                    self._expect_key[-1] = True
                else:
                    self._expect_value[-1] = True
                continue
            if ch in "}]":
                self._stack.pop()
                self._expect_key.pop()
                self._expect_value.pop()
                continue
            # A value starts here.
            if depth and self._expect_value[-1]:
                self._expect_value[-1] = False
                self._on_value(ch)
            if ch == '"':
                self._in_string = True
            elif ch in "{[":
                self._stack.append(ch)
                self._expect_key.append(ch == "{")
                self._expect_value.append(ch == "[")

    def _on_value(self, ch: str) -> None:
        stack, keys = self._stack, self._keys
        if stack == ["{"]:
            key = keys[0]
            if key is None:
                return
            if ch == "[":
                self.counts[key] = 0
            elif ch == "{":
                self.counts[key] = 1
        elif stack == ["{", "["]:
            if keys[0] is not None:
                self.counts[keys[0]] = self.counts.get(keys[0], 0) + 1
        elif stack == ["{", "{"]:
            top, sub = keys[0], keys[1]
            # A single-record section (the profile) may hold arrays of its own; it stays one record.
            if top is not None and sub is not None and ch == "[" and top not in _SINGLE_RECORD_SECTIONS:
                section = self.counts.get(top)
                if not isinstance(section, dict):
                    section = {}
                    self.counts[top] = section
                section[sub] = 0
        elif stack == ["{", "{", "["]:
            top, sub = keys[0], keys[1]
            section = self.counts.get(top) if top is not None else None
            if isinstance(section, dict) and sub in section:
                section[sub] += 1


def _section_totals(counts: dict[str, Any]) -> dict[str, int]:
    """Flatten nested section counts to one integer per top-level section."""

    return {key: sum(value.values()) if isinstance(value, dict) else int(value) for key, value in counts.items()}


# --- audio ---------------------------------------------------------------------


def _audio_blobs(client: Any, uid: str) -> list[Any]:
    bucket = client.bucket(private_archive_bucket())
    selected: list[Any] = []
    for prefix in AUDIO_PREFIXES:
        allowed = CHUNK_EXTENSIONS if prefix == "chunks" else PLAYBACK_EXTENSIONS
        for blob in client.list_blobs(bucket, prefix=f"{prefix}/{uid}/"):
            if blob.name.endswith(allowed):
                selected.append(blob)
    recordings = client.bucket(_memories_recordings_bucket())
    for blob in client.list_blobs(recordings, prefix=f"{uid}/"):
        if blob.name.endswith(RECORDING_EXTENSIONS):
            selected.append(blob)
    selected.sort(key=lambda blob: blob.name)
    return selected


def _memories_recordings_bucket() -> str:
    return (os.getenv("BUCKET_MEMORIES_RECORDINGS") or "").strip() or DEFAULT_MEMORIES_RECORDINGS_BUCKET


def _audio_member_name(blob_name: str, uid: str, decrypted: bool) -> str:
    if blob_name.startswith(f"{uid}/"):
        return f"audio/recordings/{blob_name[len(uid) + 1:]}"
    kind, _, rest = blob_name.partition(f"/{uid}/")
    if decrypted:
        ext = get_extension_for_path(blob_name)
        rest = rest[: -len("." + ext)] + _DECRYPTED_SUFFIX[ext]
    return f"audio/{kind}/{rest}"


class _HashingWriter:
    """File-like wrapper that hashes and counts what passes through it."""

    def __init__(self, target: IO[bytes]) -> None:
        self._target = target
        self.sha256 = hashlib.sha256()
        self.size = 0

    def write(self, data: bytes) -> int:
        self._target.write(data)
        self.sha256.update(data)
        self.size += len(data)
        return len(data)


# --- zip ---------------------------------------------------------------------


def _file_sha256(path: str) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with open(path, "rb") as handle:
        while block := handle.read(_COPY_CHUNK):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _spool_export(uid: str, target: IO[bytes]) -> tuple[SectionCounter, str, int]:
    counter = SectionCounter()
    writer = _HashingWriter(target)
    chunks = _export_chunks(uid)
    try:
        for chunk in chunks:
            counter.feed(chunk)
            writer.write(chunk.encode("utf-8"))
    finally:
        close = getattr(chunks, "close", None)
        if callable(close):
            close()
    return counter, writer.sha256.hexdigest(), writer.size


def _readme(
    *,
    generated_at: datetime,
    sections: dict[str, int],
    include_audio: bool,
    audio_decrypted: int,
    audio_raw: int,
    audio_undecryptable: list[str],
) -> str:
    lines = [
        "Omi personal data export (GDPR Article 15 copy)",
        f"Generated at (UTC): {generated_at.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "Included:",
        "- export.json: the same content as the in-app \"Export All Data\" download:",
        "  profile, conversations (including discarded ones and recordings metadata),",
        "  memories (including archived), people, action items, tasks, chat messages,",
        "  conversation photo manifests, frame requests and related product history.",
    ]
    for name in sorted(sections):
        lines.append(f"    {name}: {sections[name]} record(s)")
    if include_audio:
        lines += [
            "- audio/: stored recording chunks, playback MP3s and per-conversation WAV recordings",
            "  for this account (see Not included for audio this export does not yet cover).",
            "  audio/chunks/: stored recording chunks, decrypted. *.bin and *.batch.bin are raw",
            "  16-bit little-endian mono PCM. *.opus files hold Opus packets in Omi's own framing:",
            "  a 4-byte little-endian packet count, a 4-byte little-endian length of the original",
            "  PCM in bytes, then each packet as a 2-byte little-endian length followed by the",
            "  packet bytes. Decode each packet as Opus, 16 kHz mono, 20 ms frames.",
            "  audio/playback/: MP3 playback files built from those chunks.",
            "  audio/recordings/: per-conversation WAV recordings.",
            f"  Decrypted objects: {audio_decrypted}; objects stored unencrypted: {audio_raw}.",
        ]
        if audio_undecryptable:
            lines.append(
                f"  {len(audio_undecryptable)} object(s) could not be decrypted and are included as stored (encrypted):"
            )
            lines += [f"    {name}" for name in audio_undecryptable]
    else:
        lines.append("- Audio was not requested for this copy and is not included.")
    lines += [
        "- MANIFEST.sha256: SHA-256 of every other file in this archive (sha256sum format).",
        "",
        "Not included:",
        "- Operational records that are not part of the in-app export (logs, billing",
        "  records held by our payment processor, support conversations).",
        "- Data held by third-party integrations you connected; request it from them.",
        "- Audio not yet covered by this export: live-capture packs (raw-live), regional",
        "  playback copies and derived audio (for example cleaned or enhanced versions).",
        "  Ask support if you need these; they are provided on request.",
        "- Conversations you deleted that we are keeping under a legal preservation",
        "  obligation: they are hidden from your account and not in export.json; their",
        "  audio, if any, is in audio/. Ask support for their records.",
        "",
    ]
    return "\n".join(lines)


def _build_zip(uid: str, zip_path: str, *, include_audio: bool, client: Any | None) -> dict[str, Any]:
    generated_at = _now()
    manifest: list[tuple[str, str]] = []
    audio_objects = audio_bytes = audio_decrypted = audio_raw = 0
    undecryptable: list[str] = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        with archive.open("export.json", "w", force_zip64=True) as member:
            counter, export_sha, _ = _spool_export(uid, member)
        manifest.append((export_sha, "export.json"))

        if include_audio:
            assert client is not None
            for blob in _audio_blobs(client, uid):
                encrypted = blob.name.endswith(".enc")
                if encrypted:
                    stored = blob.download_as_bytes()
                    try:
                        payload, decrypted = _decrypt_audio(stored, uid), True
                    except Exception:  # noqa: BLE001 - keep the object, flag it in README
                        payload, decrypted = stored, False
                        undecryptable.append(_audio_member_name(blob.name, uid, False))
                    del stored
                    name = _audio_member_name(blob.name, uid, decrypted)
                    with archive.open(name, "w", force_zip64=True) as member:
                        writer = _HashingWriter(member)
                        writer.write(payload)
                    del payload
                    audio_decrypted += int(decrypted)
                else:
                    name = _audio_member_name(blob.name, uid, False)
                    with archive.open(name, "w", force_zip64=True) as member:
                        writer = _HashingWriter(member)
                        blob.download_to_file(writer)
                    audio_raw += 1
                manifest.append((writer.sha256.hexdigest(), name))
                audio_objects += 1
                audio_bytes += writer.size

        sections = _section_totals(counter.counts)
        readme = _readme(
            generated_at=generated_at,
            sections=sections,
            include_audio=include_audio,
            audio_decrypted=audio_decrypted,
            audio_raw=audio_raw,
            audio_undecryptable=undecryptable,
        ).encode("utf-8")
        archive.writestr("README.txt", readme)
        manifest.append((hashlib.sha256(readme).hexdigest(), "README.txt"))
        archive.writestr("MANIFEST.sha256", "".join(f"{sha}  {name}\n" for sha, name in manifest))

    return {
        "generated_at": generated_at,
        "sections": sections,
        "audio_objects": audio_objects,
        "audio_bytes": audio_bytes,
        "audio_decrypted": audio_decrypted,
        "audio_raw": audio_raw,
        "audio_undecryptable": len(undecryptable),
    }


# --- upload + sign -------------------------------------------------------------


def _signing_kwargs(credentials: Any) -> dict[str, str]:
    if not credentials.valid:
        credentials.refresh(google_auth_requests.Request())
    email = getattr(credentials, "service_account_email", None) or getattr(credentials, "signer_email", None)
    token = getattr(credentials, "token", None)
    if not isinstance(email, str) or "@" not in email or not token:
        raise DsarExportError(
            "operator credentials cannot sign through IAM signBlob: use a service-account identity "
            "(impersonated operator tier), not a user login or JSON key"
        )
    return {"service_account_email": email, "access_token": token}


def _summary_sections(sections: dict[str, int]) -> dict[str, int]:
    """Content-free section counts that fit the audit summary's flat scalar shape."""

    summary = {"sections": len(sections), "section_records": sum(sections.values())}
    for name in _SUMMARY_SECTIONS:
        if name in sections:
            summary[f"section_{name}"] = sections[name]
    return summary


def _validate(args: argparse.Namespace, ctx: ActionContext) -> tuple[str, str, int]:
    uid = (getattr(args, "uid", "") or "").strip()
    if not uid or "/" in uid:
        raise DsarExportError("uid is required")
    approval = (getattr(args, "approval", "") or "").strip()
    if not approval:
        raise DsarExportError("--approval is required: reference the recorded approval (Intercom note id)")
    if len(approval) > 200:
        raise DsarExportError("--approval reference is too long")
    url_days = getattr(args, "url_days", DEFAULT_URL_DAYS)
    if not isinstance(url_days, int) or not 1 <= url_days <= MAX_URL_DAYS:
        raise DsarExportError(f"--url-days must be between 1 and {MAX_URL_DAYS}")
    if not _TICKET_RE.match(ctx.ticket):
        raise DsarExportError("ticket must be a plain id (letters, digits, '.', '_', '-') to form the object path")
    return uid, approval, url_days


def export(args: argparse.Namespace, ctx: ActionContext, record: ActionRecord) -> dict[str, Any]:
    uid, approval, url_days = _validate(args, ctx)
    include_audio = bool(getattr(args, "audio", True))
    client = _storage_client() if (include_audio or ctx.apply) else None

    if not ctx.apply:
        with tempfile.TemporaryFile() as scratch:
            counter, _, export_bytes = _spool_export(uid, scratch)
        sections = _section_totals(counter.counts)
        blobs = _audio_blobs(client, uid) if include_audio else []
        audio_bytes = sum(int(getattr(blob, "size", 0) or 0) for blob in blobs)
        record.summary = {
            "dry_run": True,
            "approval": approval,
            **_summary_sections(sections),
            "audio": include_audio,
            "audio_objects": len(blobs),
            "audio_bytes": audio_bytes,
            "url_days": url_days,
        }
        return {
            "dry_run": True,
            "approval": approval,
            "sections": sections,
            "export_json_bytes": export_bytes,
            "audio": include_audio,
            "audio_objects": len(blobs),
            "audio_stored_bytes": audio_bytes,
            "url_days": url_days,
            "would_upload_to": f"gs://{EXPORT_BUCKET}/{ctx.ticket}/{uid[:6]}-<UTC>.zip",
        }

    # Fail before any read or upload when these credentials cannot sign.
    _signing_kwargs(_credentials())
    workdir = tempfile.mkdtemp(prefix="dsar-export-")
    try:
        zip_path = os.path.join(workdir, "export.zip")
        built = _build_zip(uid, zip_path, include_audio=include_audio, client=client)
        zip_sha, zip_bytes = _file_sha256(zip_path)
        stamp = built["generated_at"].strftime("%Y%m%dT%H%M%SZ")
        object_name = f"{ctx.ticket}/{uid[:6]}-{stamp}.zip"
        assert client is not None  # resolved above whenever ctx.apply
        blob = client.bucket(EXPORT_BUCKET).blob(object_name)
        blob.metadata = {"sha256": zip_sha, "approval": approval}
        # Sign before upload (a V4 URL does not need the object to exist): a
        # signing failure then leaves no export behind without a link.
        expires_at = _now() + timedelta(days=url_days)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(days=url_days),
            method="GET",
            **_signing_kwargs(_credentials()),
        )
        blob.upload_from_filename(zip_path, content_type="application/zip", if_generation_match=0)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    record.after_digest = zip_sha
    record.summary = {
        "approval": approval,
        **_summary_sections(built["sections"]),
        "audio": include_audio,
        "audio_objects": built["audio_objects"],
        "audio_decrypted": built["audio_decrypted"],
        "audio_undecryptable": built["audio_undecryptable"],
        "zip_bytes": zip_bytes,
        "url_days": url_days,
    }
    return {
        "object": f"gs://{EXPORT_BUCKET}/{object_name}",
        "zip_bytes": zip_bytes,
        "zip_sha256": zip_sha,
        "signed_url": signed_url,
        "url_expires_at": expires_at.isoformat(),
        "url_days": url_days,
        "approval": approval,
        "sections": built["sections"],
        "audio": include_audio,
        "audio_objects": built["audio_objects"],
        "audio_bytes": built["audio_bytes"],
        "audio_decrypted": built["audio_decrypted"],
        "audio_undecryptable": built["audio_undecryptable"],
    }


__all__: Iterable[str] = ("register", "export", "SectionCounter", "DsarExportError")
