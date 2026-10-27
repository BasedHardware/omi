"""Mirror David's own recordings into the staging mirror bucket, re-encrypted.

Consent: David, fifth-round rulings 2026-10-19 ("copying some of his own
recordings into dev/staging, with re-encryption under a staging key").

Scope and safety (swarm lane 4, contract (i)):
- **One owner.** The uid comes from ``$DAVID_UID`` and must equal the singleton
  value of every pin env on a prod Cloud Run service (default
  ``backend-sync``: three David-only allowlists; ``DREAM_AGENT_CANARY_UID`` is NOT David).
  If any pin is missing, a secret ref, or not exactly that one uid, nothing runs.
  The uid is never printed or written.
- **Prod is read-only.** Prod access goes through ``ReadOnlyBucket`` (list and
  get only) with the ``prod-operator`` key; ``ENCRYPTION_SECRET`` is read once
  for ``.enc`` objects (the 10-17 prod-operator exception for batch operator tools).
- **Plaintext only in memory.** Each object is downloaded, decrypted, checked,
  sealed under the staging-only mirror key and uploaded to
  ``gs://based-hardware-dev-staging-mirror`` with the ``dev-operator`` key. No
  temp files.
- **Records are aggregates.** The run record (counts, bytes, UTC-day range,
  audio hours, skip reasons) goes to the workspace lane04 folder; the bucket
  manifest holds keyed group labels, hashes and timing only.

    export DAVID_UID=...   # the already verified owner uid; never echo it
    python -m scripts.staging.mirror_owner_recordings inventory
    python -m scripts.staging.mirror_owner_recordings copy --max-conversations 200 --apply
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from testing.loadgen import mirror_codec as mc  # noqa: E402

PROD_PROJECT = 'based-hardware'
DEV_PROJECT = 'based-hardware-dev'
MIRROR_BUCKET = 'based-hardware-dev-staging-mirror'
SOURCE_BUCKETS = {'private-cloud-sync': 'omi-private-cloud-sync', 'syncing-local': 'syncing-local'}
PIN_SERVICE = 'backend-sync'
PIN_ENVS = ('BATCH_PIPELINE_UID_ALLOWLIST', 'DREAM_AGENT_UID_ALLOWLIST', 'TRANSCRIPTION_SHADOW_UID_ALLOWLIST')
SECRETS_DIR = Path.home() / '.local' / 'share' / 'hostctl' / 'secrets'
DEFAULT_PROD_KEY = SECRETS_DIR / 'gcp-agent-prod-operator'
DEFAULT_DEV_KEY = SECRETS_DIR / 'gcp-agent-dev-operator'
PROD_ENCRYPTION_SECRET = f'projects/{PROD_PROJECT}/secrets/ENCRYPTION_SECRET/versions/latest'
STAGING_SECRET = f'projects/{DEV_PROJECT}/secrets/staging-encryption-secret/versions/latest'
DEFAULT_RECORD_DIR = Path('/Users/dazheng/workspace/omi/data/run-2026-10-19-legacy-retire/lane04')
MAX_OBJECT_BYTES = 64 * 1024 * 1024


class MirrorRefused(RuntimeError):
    """A safety precondition failed; nothing was read or written past it."""


# --------------------------------------------------------------------------
# Owner pin
# --------------------------------------------------------------------------


def verify_owner_pin(uid: str, service_env: dict[str, str | None], pin_envs: Iterable[str] = PIN_ENVS) -> None:
    """Every pin env must be a literal singleton equal to uid (secret refs count as missing)."""
    if not uid or '/' in uid or len(uid) > 128:
        raise MirrorRefused('owner uid missing or malformed')
    for name in pin_envs:
        value = service_env.get(name)
        if value is None:
            raise MirrorRefused(f'owner pin {name} is absent or not a literal value')
        entries = [x.strip() for x in value.split(',') if x.strip()]
        if entries != [uid]:
            raise MirrorRefused(f'owner pin {name} is not exactly the configured owner')


def cloud_run_literal_env(
    session: Any, project: str, service: str, region: str = 'us-central1'
) -> dict[str, str | None]:
    url = f'https://run.googleapis.com/v2/projects/{project}/locations/{region}/services/{service}'
    response = session.get(url, timeout=30)
    response.raise_for_status()
    env: dict[str, str | None] = {}
    for container in response.json().get('template', {}).get('containers', []):
        for item in container.get('env', []):
            env[item['name']] = item.get('value') if 'valueSource' not in item else None
    return env


def read_secret(session: Any, resource: str) -> bytes:
    import base64

    response = session.get(f'https://secretmanager.googleapis.com/v1/{resource}:access', timeout=30)
    response.raise_for_status()
    return base64.b64decode(response.json()['payload']['data'])


# --------------------------------------------------------------------------
# Source inventory
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceObject:
    source: str  # 'private-cloud-sync' | 'syncing-local'
    kind: str  # 'chunk' | 'raw-sync' | 'raw-mobile-batch' | 'syncing'
    name: str
    size: int
    group: str  # conversation id / job id / day key; never written out in clear
    capture_start: float
    source_format: str
    encrypted: bool
    original_name: str = ''
    expected_sha256: str = ''


def _float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def classify(source: str, uid: str, name: str, size: int, metadata: dict[str, str] | None) -> SourceObject | str:
    """Map one listed object to a SourceObject, or return the skip reason."""
    metadata = metadata or {}
    if size <= 0 or size > MAX_OBJECT_BYTES:
        return 'size_out_of_bounds'
    parts = name.split('/')
    if source == 'private-cloud-sync' and parts[0] == 'chunks' and len(parts) == 4 and parts[1] == uid:
        leaf = parts[3]
        for ext, fmt, enc in (
            ('.opus.enc', mc.FORMAT_CHUNK_OPUS, True),
            ('.opus', mc.FORMAT_CHUNK_OPUS, False),
            ('.batch.enc', mc.FORMAT_CHUNK_PCM16, True),  # concatenated per-chunk ciphertexts of PCM16
            ('.batch.bin', mc.FORMAT_CHUNK_PCM16, False),
            ('.enc', mc.FORMAT_CHUNK_PCM16, True),
            ('.bin', mc.FORMAT_CHUNK_PCM16, False),
        ):
            if leaf.endswith(ext):
                if fmt == mc.FORMAT_CHUNK_PCM16:
                    rate = metadata.get('v2_sample_rate') or metadata.get('record_sample_rate') or '16000'
                    if rate != '16000':
                        return 'non_16k_pcm'
                ts = _float(leaf[: -len(ext)].split('-', 1)[0])  # batch names are <first>-<last>
                if ts is None:
                    return 'chunk_timestamp_unparsed'
                return SourceObject(source, 'chunk', name, size, parts[2], ts, fmt, enc)
        return 'chunk_extension_unknown'
    if source == 'private-cloud-sync' and parts[0] in ('raw-sync', 'raw-mobile-batch') and len(parts) == 4:
        if parts[1] != uid:
            return 'foreign_owner'
        filename, leaf = parts[2], parts[3]
        fields = mc.parse_upload_filename(filename)
        if fields is None:
            return 'raw_filename_unparsed'
        try:
            linked = json.loads(metadata.get('conversation_ids', '[]'))
        except ValueError:
            linked = []
        day = datetime.fromtimestamp(fields['capture_start'], timezone.utc).strftime('%Y-%m-%d')
        group = linked[0] if len(linked) == 1 else f'{parts[0]}:{day}'
        return SourceObject(
            source,
            parts[0],
            name,
            size,
            group,
            fields['capture_start'],
            mc.FORMAT_RAW_UPLOAD,
            leaf.endswith('.enc'),
            filename,
            metadata.get('sha256', ''),
        )
    if source == 'syncing-local' and parts[0] == 'syncing' and len(parts) == 4 and parts[1] == uid:
        fields = mc.parse_upload_filename(parts[3])
        if fields is None:
            return 'syncing_not_upload_file'
        return SourceObject(
            source, 'syncing', name, size, parts[2], fields['capture_start'], mc.FORMAT_RAW_UPLOAD, False, parts[3]
        )
    return 'unrecognized_layout'


def prefixes_for(source: str, uid: str) -> list[str]:
    if source == 'private-cloud-sync':
        # David's 10-19 grant is conditioned to chunks/<uid>/ only (title david-archive-prefix-only);
        # never list or read another prefix of this bucket.
        return [f'chunks/{uid}/']
    if source == 'syncing-local':
        return [f'syncing/{uid}/']
    raise MirrorRefused(f'unknown source {source!r}')


class ReadOnlyBucket:
    """The only prod storage surface this tool has: list and get."""

    def __init__(self, client: Any, name: str):
        if name not in SOURCE_BUCKETS.values():
            raise MirrorRefused('source bucket outside the allowlist')
        self._bucket = client.bucket(name)
        self._client = client
        self.name = name

    def list(self, prefix: str) -> Iterable[Any]:
        return self._client.list_blobs(self._bucket, prefix=prefix)

    def get(self, name: str) -> bytes:
        return self._bucket.blob(name).download_as_bytes(timeout=120)


@dataclass
class Inventory:
    objects: list[SourceObject] = field(default_factory=list)
    listed: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)

    def groups(self) -> dict[tuple[str, str], list[SourceObject]]:
        out: dict[tuple[str, str], list[SourceObject]] = {}
        for obj in self.objects:
            family = 'chunk' if obj.kind == 'chunk' else 'upload'
            out.setdefault((family, obj.group), []).append(obj)
        for files in out.values():
            files.sort(key=lambda o: o.capture_start)
        return out


def take_inventory(buckets: dict[str, ReadOnlyBucket], uid: str) -> Inventory:
    inv = Inventory()
    for source, bucket in buckets.items():
        for prefix in prefixes_for(source, uid):
            kind = prefix.split('/', 1)[0]
            for blob in bucket.list(prefix):
                inv.listed[kind] = inv.listed.get(kind, 0) + 1
                got = classify(source, uid, blob.name, int(blob.size or 0), blob.metadata)
                if isinstance(got, str):
                    inv.skipped[got] = inv.skipped.get(got, 0) + 1
                else:
                    inv.objects.append(got)
    return inv


def select_groups(
    inv: Inventory,
    *,
    max_groups: int,
    since: float | None = None,
    families: tuple[str, ...] = ('chunk', 'upload'),
    spread: bool = False,
    max_group_bytes: int | None = None,
) -> list[list[SourceObject]]:
    """``max_groups`` recordings: the newest, or (``spread``) evenly spaced across the capture history.

    ``max_group_bytes`` skips recordings larger than the bound (multi-hour batch containers).
    """
    groups = [
        files
        for (family, _), files in inv.groups().items()
        if family in families
        and (since is None or files[-1].capture_start >= since)
        and (max_group_bytes is None or sum(o.size for o in files) <= max_group_bytes)
    ]
    groups.sort(key=lambda files: files[-1].capture_start, reverse=True)
    if not spread or len(groups) <= max_groups:
        return groups[:max_groups]
    step = len(groups) / max_groups
    return [groups[int(i * step)] for i in range(max_groups)]


def inventory_record(inv: Inventory, selected: list[list[SourceObject]] | None = None) -> dict[str, Any]:
    """Aggregates only: no uid, no names, no ids."""

    def day(ts: float) -> str:
        return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d')

    groups = inv.groups()
    by_kind: dict[str, dict[str, int]] = {}
    for obj in inv.objects:
        k = by_kind.setdefault(f'{obj.kind}/{obj.source_format}', {'objects': 0, 'bytes': 0, 'encrypted': 0})
        k['objects'] += 1
        k['bytes'] += obj.size
        k['encrypted'] += int(obj.encrypted)
    starts = [o.capture_start for o in inv.objects]
    record: dict[str, Any] = {
        'listed_by_prefix_kind': dict(sorted(inv.listed.items())),
        'mirrorable_by_kind': dict(sorted(by_kind.items())),
        'skipped_by_reason': dict(sorted(inv.skipped.items())),
        'recordings': {
            'chunk_conversations': sum(1 for f, _ in groups if f == 'chunk'),
            'upload_groups': sum(1 for f, _ in groups if f == 'upload'),
        },
        'capture_day_range_utc': [day(min(starts)), day(max(starts))] if starts else [],
    }
    if selected is not None:
        objs = [o for files in selected for o in files]
        record['selected'] = {
            'recordings': len(selected),
            'objects': len(objs),
            'bytes': sum(o.size for o in objs),
            'capture_day_range_utc': (
                [day(min(o.capture_start for o in objs)), day(max(o.capture_start for o in objs))] if objs else []
            ),
        }
    return record


# --------------------------------------------------------------------------
# Copy
# --------------------------------------------------------------------------


@dataclass
class CopyStats:
    read_objects: int = 0
    read_bytes: int = 0
    decrypted: int = 0
    written: int = 0
    already_present: int = 0
    audio_seconds: float = 0.0
    failed: dict[str, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def fail(self, reason: str) -> None:
        with self.lock:
            self.failed[reason] = self.failed.get(reason, 0) + 1

    def public(self) -> dict[str, Any]:
        # Not dataclasses.asdict: it deep-copies fields and a Lock cannot be copied.
        with self.lock:
            return {
                'read_objects': self.read_objects,
                'read_bytes': self.read_bytes,
                'decrypted': self.decrypted,
                'written': self.written,
                'already_present': self.already_present,
                'audio_hours': round(self.audio_seconds / 3600, 3),
                'failed': dict(sorted(self.failed.items())),
            }


def mirror_object_name(owner_label: str, group: str, seq: int, plaintext_sha256: str) -> str:
    return f'mirror/v1/{owner_label}/{group}/{seq:05d}-{plaintext_sha256[:24]}.smenc'


def copy_object(
    obj: SourceObject,
    seq: int,
    *,
    owner_label: str,
    group: str,
    read: Callable[[SourceObject], bytes],
    prod_user_key: Callable[[], bytes],
    mirror_key: bytes,
    write: Callable[[str, bytes, dict[str, str]], bool],
    stats: CopyStats,
) -> dict[str, Any] | None:
    try:
        raw = read(obj)
    except Exception as exc:
        stats.fail(f'read:{type(exc).__name__}')
        return None
    with stats.lock:
        stats.read_objects += 1
        stats.read_bytes += len(raw)
    try:
        plain = mc.decrypt_prod_audio(raw, prod_user_key()) if obj.encrypted else raw
    except Exception as exc:
        stats.fail(f'decrypt:{type(exc).__name__}')
        return None
    del raw
    if obj.encrypted:
        with stats.lock:
            stats.decrypted += 1
    digest = hashlib.sha256(plain).hexdigest()
    if obj.expected_sha256 and obj.expected_sha256 != digest:
        stats.fail('sha256_mismatch')
        return None
    try:
        audio = mc.to_upload_audio(obj.source_format, plain, filename=obj.original_name)
    except mc.MirrorFormatError:
        stats.fail('unparseable_audio')
        return None
    name = mirror_object_name(owner_label, group, seq, digest)
    sealed = mc.seal_mirror_object(mirror_key, name, plain)
    del plain
    metadata = {
        'mirror_format': 'v1',
        'source_format': obj.source_format,
        'plaintext_sha256': digest,
        'duration_s': f'{audio.duration_s:.3f}',
    }
    try:
        created = write(name, sealed, metadata)
    except Exception as exc:
        stats.fail(f'write:{type(exc).__name__}')
        return None
    with stats.lock:
        stats.written += int(created)
        stats.already_present += int(not created)
        stats.audio_seconds += audio.duration_s
    return {
        'object': name,
        'group': group,
        'source_format': obj.source_format,
        'duration_s': round(audio.duration_s, 3),
        'capture_start': obj.capture_start,
        'original_name': obj.original_name,
        'plaintext_sha256': digest,
        'bytes': len(sealed),
    }


def make_writer(dev_client: Any, bucket_name: str) -> Callable[[str, bytes, dict[str, str]], bool]:
    if bucket_name != MIRROR_BUCKET:
        raise MirrorRefused(f'destination must be {MIRROR_BUCKET}')
    from google.api_core.exceptions import PreconditionFailed

    bucket = dev_client.bucket(bucket_name)

    def write(name: str, sealed: bytes, metadata: dict[str, str]) -> bool:
        blob = bucket.blob(name)
        blob.metadata = metadata
        try:
            blob.upload_from_string(sealed, content_type='application/octet-stream', if_generation_match=0, timeout=120)
            return True
        except PreconditionFailed:
            blob.reload(timeout=30)
            if (blob.metadata or {}).get('plaintext_sha256') != metadata['plaintext_sha256']:
                raise
            return False

    return write


def _credentials(path: Path, expected_project: str) -> Any:
    from google.oauth2 import service_account

    if not path.is_file():
        raise MirrorRefused(f'credential file missing for {expected_project} (hostctl secrets)')
    creds = service_account.Credentials.from_service_account_file(
        str(path), scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    if creds.project_id != expected_project:
        raise MirrorRefused(f'credential is not a {expected_project} identity')
    return creds


def write_record(record_dir: Path, record: dict[str, Any]) -> Path:
    record_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = record_dir / f'mirror-{record["mode"]}-{stamp}.json'
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return path


def run(args: argparse.Namespace) -> int:
    from google.auth.transport.requests import AuthorizedSession
    from google.cloud import storage

    uid = os.environ.get(args.owner_env, '').strip()
    prod_creds = _credentials(Path(args.prod_key_file), PROD_PROJECT)
    prod_session = AuthorizedSession(prod_creds)
    verify_owner_pin(uid, cloud_run_literal_env(prod_session, PROD_PROJECT, args.pin_service), args.pin_env)

    prod_storage = storage.Client(project=PROD_PROJECT, credentials=prod_creds)
    buckets = {s: ReadOnlyBucket(prod_storage, SOURCE_BUCKETS[s]) for s in args.source}
    inv = take_inventory(buckets, uid)
    since = datetime.now(timezone.utc).timestamp() - args.since_days * 86400 if args.since_days else None
    selected = select_groups(
        inv,
        max_groups=args.max_conversations,
        since=since,
        families=tuple(args.family),
        spread=args.spread,
        max_group_bytes=int(args.max_group_mb * 1024 * 1024) if args.max_group_mb else None,
    )
    record: dict[str, Any] = {
        'mode': 'inventory' if args.cmd == 'inventory' or not args.apply else 'copy',
        'at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'owner': 'David (pinned by singleton allowlists; uid withheld)',
        'tier_read': 'prod-operator',
        'prod_operations': 'list objects + metadata (owner prefixes only)'
        + (
            ''
            if args.cmd == 'inventory' or not args.apply
            else '; get selected objects; ENCRYPTION_SECRET only if .enc'
        ),
        'sources': {s: SOURCE_BUCKETS[s] for s in args.source},
        'inventory': inventory_record(inv, selected),
    }
    if record['mode'] == 'copy':
        dev_creds = _credentials(Path(args.dev_key_file), DEV_PROJECT)
        staging_secret = (
            os.environ[args.staging_secret_env].encode()
            if args.staging_secret_env
            else read_secret(AuthorizedSession(dev_creds), args.staging_secret)
        )
        mirror_key = mc.derive_mirror_key(staging_secret)
        group_key = mc.derive_group_key(staging_secret)
        del staging_secret
        user_key_box: dict[str, bytes] = {}
        user_key_lock = threading.Lock()

        def prod_user_key() -> bytes:
            with user_key_lock:
                if 'k' not in user_key_box:  # read ENCRYPTION_SECRET only if an .enc object is selected
                    secret = read_secret(prod_session, PROD_ENCRYPTION_SECRET)
                    user_key_box['k'] = mc.derive_prod_user_key(secret, uid)
                    del secret
                return user_key_box['k']

        def read(obj: SourceObject) -> bytes:
            return buckets[obj.source].get(obj.name)

        write = make_writer(storage.Client(project=DEV_PROJECT, credentials=dev_creds), args.dest_bucket)
        stats = CopyStats()
        jobs = []
        for files in selected:
            label = mc.group_label(group_key, f'{files[0].kind}:{files[0].group}')
            for seq, obj in enumerate(files):
                jobs.append((obj, seq, label))
        entries: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(
                    copy_object,
                    obj,
                    seq,
                    owner_label=args.owner_label,
                    group=label,
                    read=read,
                    prod_user_key=prod_user_key,
                    mirror_key=mirror_key,
                    write=write,
                    stats=stats,
                )
                for obj, seq, label in jobs
            ]
            for future in concurrent.futures.as_completed(futures):
                entry = future.result()
                if entry:
                    entries.append(entry)
        entries.sort(key=lambda e: (e['group'], e['capture_start']))
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        manifest = {
            'schema_version': 1,
            'run_id': run_id,
            'owner_label': args.owner_label,
            'objects': entries,
        }
        manifest_name = f'manifests/{args.owner_label}/{run_id}.json'
        write(
            manifest_name,
            json.dumps(manifest, sort_keys=True).encode(),
            {
                'mirror_format': 'manifest-v1',
                'plaintext_sha256': hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            },
        )
        record['tier_write'] = 'dev-operator'
        record['destination'] = f'gs://{args.dest_bucket}/mirror/v1/{args.owner_label}/'
        record['manifest'] = f'gs://{args.dest_bucket}/{manifest_name}'
        record['copy'] = stats.public()
        record['mirrored_recordings'] = len({e['group'] for e in entries})
    path = write_record(Path(args.record_dir), record)
    print(json.dumps({'event': f'mirror_{record["mode"]}', 'record': str(path), **record['inventory']}, sort_keys=True))
    return 0 if not record.get('copy', {}).get('failed') else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Mirror David-only recordings into staging (swarm lane 4)')
    parser.add_argument('cmd', choices=['inventory', 'copy'])
    parser.add_argument('--owner-env', default='DAVID_UID')
    parser.add_argument('--pin-service', default=PIN_SERVICE)
    parser.add_argument('--pin-env', action='append', default=None, help=f'default: {", ".join(PIN_ENVS)}')
    parser.add_argument('--source', action='append', choices=sorted(SOURCE_BUCKETS), default=None)
    parser.add_argument('--max-conversations', type=int, default=200)
    parser.add_argument('--since-days', type=float)
    parser.add_argument('--family', action='append', choices=['chunk', 'upload'], default=None)
    parser.add_argument('--spread', action='store_true', help='evenly spaced across history instead of newest')
    parser.add_argument('--max-group-mb', type=float, help='skip recordings larger than this')
    parser.add_argument('--owner-label', default='owner-a')
    parser.add_argument('--dest-bucket', default=MIRROR_BUCKET)
    parser.add_argument('--staging-secret', default=STAGING_SECRET)
    parser.add_argument('--staging-secret-env', help='read the staging secret from this env instead')
    parser.add_argument('--prod-key-file', default=str(DEFAULT_PROD_KEY))
    parser.add_argument('--dev-key-file', default=str(DEFAULT_DEV_KEY))
    parser.add_argument('--record-dir', default=str(DEFAULT_RECORD_DIR))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--apply', action='store_true', help='copy: actually read audio and write the mirror')
    args = parser.parse_args(argv)
    args.pin_env = tuple(args.pin_env or PIN_ENVS)
    args.family = args.family or ['chunk', 'upload']
    # prod-operator can get syncing-local (raw client uploads, short retention) but only
    # list omi-private-cloud-sync; copying chunks needs a David-prefix read grant (human tier).
    args.source = args.source or (
        ['private-cloud-sync', 'syncing-local'] if args.cmd == 'inventory' else ['syncing-local']
    )
    if not args.owner_label.replace('-', '').isalnum():
        parser.error('--owner-label must be alphanumeric/dash')
    try:
        return run(args)
    except MirrorRefused as exc:
        print(json.dumps({'event': 'mirror_refused', 'reason': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
