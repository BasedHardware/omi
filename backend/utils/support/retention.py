"""``retention check``: what Omi still holds for one account's conversations.

Read-only. For the selected conversations it reports the Firestore document
shape (never decrypted content), every GCS object under the conversation's
audio prefixes (live, noncurrent and soft-deleted), the account's legal hold
and deletion state, and best-effort Firestore backup coverage. It never scans a
whole account: a ``--conversation`` or ``--month`` filter is required, and the
month query is capped at ``CONVERSATION_CAP``.
"""

from __future__ import annotations

import argparse
import json
import os
import zlib
from datetime import datetime, timezone
from typing import Any

from google.cloud.firestore_v1 import FieldFilter

from config.record_wal_storage import private_archive_bucket
from database.account_deletion_marker import account_deletion_firestore_client

try:  # optional: backup coverage is best-effort
    from google.cloud import firestore_admin_v1
except ImportError:  # pragma: no cover - depends on the installed SDK
    firestore_admin_v1 = None

try:
    from google.cloud import storage as gcs_storage
except ImportError:  # pragma: no cover - depends on the installed SDK
    gcs_storage = None

CONVERSATION_CAP = 200
DEFAULT_MEMORIES_RECORDINGS_BUCKET = 'memories-recordings'


class RetentionCheckError(ValueError):
    """The command was asked for something it refuses to do."""


# --- seams ----------------------------------------------------------------


def _firestore_client() -> Any:
    return account_deletion_firestore_client()


def _storage_client() -> Any:
    if gcs_storage is None:
        raise RetentionCheckError('google-cloud-storage is not installed')
    return gcs_storage.Client()


def _firestore_admin_client() -> Any:
    if firestore_admin_v1 is None:
        raise RetentionCheckError('google-cloud-firestore admin API is not installed')
    return firestore_admin_v1.FirestoreAdminClient()


def _private_cloud_sync_bucket() -> str:
    return private_archive_bucket()


def _memories_recordings_bucket() -> str:
    return (os.getenv('BUCKET_MEMORIES_RECORDINGS') or '').strip() or DEFAULT_MEMORIES_RECORDINGS_BUCKET


# --- CLI ------------------------------------------------------------------


def register(groups: Any) -> None:
    group = groups.add_parser('retention', help='what Omi still holds for an account (read-only)')
    actions = group.add_subparsers(dest='retention_action', required=True)
    check_parser = actions.add_parser('check', help='conversations, audio objects, holds and backups for one uid')
    check_parser.add_argument('uid')
    check_parser.add_argument('--conversation', default=None, help='one conversation id')
    check_parser.add_argument('--month', default=None, type=_parse_month, help='UTC month, YYYY-MM')
    check_parser.set_defaults(action='check', handler=check)


def _parse_month(value: str) -> tuple[datetime, datetime]:
    try:
        start = datetime.strptime(value, '%Y-%m').replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f'month must be YYYY-MM, got {value!r}') from exc
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


# --- counters -------------------------------------------------------------


class _Counters:
    def __init__(self) -> None:
        self.firestore_reads = 0
        self.listing_calls = 0

    def as_dict(self) -> dict[str, int]:
        return {'firestore_reads': self.firestore_reads, 'listing_calls': self.listing_calls}


def _get(doc_ref: Any, counters: _Counters) -> Any:
    counters.firestore_reads += 1
    return doc_ref.get()


def _snapshot_dict(snapshot: Any) -> dict[str, Any] | None:
    if snapshot is None or not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict() or {}


# --- conversations --------------------------------------------------------


def _select_conversations(
    client: Any, uid: str, conversation_id: str | None, month: tuple[datetime, datetime] | None, counters: _Counters
) -> tuple[list[tuple[str, dict[str, Any] | None]], bool]:
    conversations = client.collection('users').document(uid).collection('conversations')
    if conversation_id:
        snapshot = _get(conversations.document(conversation_id), counters)
        return [(conversation_id, _snapshot_dict(snapshot))], False
    if month is None:
        raise RetentionCheckError('retention check needs --conversation or --month; it never scans a whole account')
    start, end = month
    query = (
        conversations.where(filter=FieldFilter('created_at', '>=', start))
        .where(filter=FieldFilter('created_at', '<', end))
        .order_by('created_at')
        .limit(CONVERSATION_CAP + 1)
    )
    snapshots = list(query.stream())
    # An empty query is still billed as one read.
    counters.firestore_reads += max(len(snapshots), 1)
    capped = len(snapshots) > CONVERSATION_CAP
    return [(snap.id, snap.to_dict() or {}) for snap in snapshots[:CONVERSATION_CAP]], capped


def _segment_shape(data: dict[str, Any]) -> tuple[bool, int | str | None]:
    """(transcript present, segment count | 'encrypted' | None) without decrypting."""

    segments = data.get('transcript_segments')
    present = bool(segments)
    if not present:
        return False, 0 if segments is not None else None
    if data.get('data_protection_level') == 'enhanced':
        return True, 'encrypted'
    if isinstance(segments, list):
        return True, len(segments)
    if isinstance(segments, str):
        # Strings are encrypted payloads; counting would need decryption.
        return True, 'encrypted'
    if isinstance(segments, (bytes, bytearray)) and data.get('transcript_segments_compressed'):
        try:
            decoded = json.loads(zlib.decompress(bytes(segments)).decode('utf-8'))
        except (zlib.error, UnicodeDecodeError, json.JSONDecodeError):
            return True, None
        return True, len(decoded) if isinstance(decoded, list) else None
    return True, None


def _conversation_report(conversation_id: str, data: dict[str, Any] | None) -> dict[str, Any]:
    if data is None:
        return {'id': conversation_id, 'exists': False}
    present, segment_count = _segment_shape(data)
    structured = data.get('structured')
    if not isinstance(structured, dict):
        structured = {}
    return {
        'id': conversation_id,
        'exists': True,
        'created_at': data.get('created_at'),
        'started_at': data.get('started_at'),
        'finished_at': data.get('finished_at'),
        'conversation_status': data.get('status'),
        'discarded': data.get('discarded'),
        'title': structured.get('title'),
        'data_protection_level': data.get('data_protection_level'),
        'transcript_present': present,
        'segment_count': segment_count,
    }


# --- storage --------------------------------------------------------------


def _storage_prefixes(uid: str, conversation_id: str) -> list[tuple[str, str]]:
    sync = _private_cloud_sync_bucket()
    return [
        (sync, f'chunks/{uid}/{conversation_id}/'),
        (sync, f'raw-live/{uid}/{conversation_id}/'),
        (sync, f'playback/{uid}/{conversation_id}/'),
        (_memories_recordings_bucket(), f'{uid}/{conversation_id}.wav'),
    ]


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _list_prefix(storage: Any, bucket: str, prefix: str, counters: _Counters) -> dict[str, Any]:
    report: dict[str, Any] = {
        'bucket': bucket,
        'prefix': prefix,
        'objects': 0,
        'bytes': 0,
        'earliest_created': None,
        'latest_created': None,
        'live': 0,
        'noncurrent': 0,
        'soft_deleted': 0,
        'soft_delete': 'listed',
    }
    created: list[Any] = []

    def add(blob: Any, kind: str) -> None:
        report['objects'] += 1
        report['bytes'] += int(getattr(blob, 'size', 0) or 0)
        report[kind] += 1
        if getattr(blob, 'time_created', None) is not None:
            created.append(blob.time_created)

    # versions=True and soft_deleted=True cannot be combined in one request.
    counters.listing_calls += 1
    for blob in storage.list_blobs(bucket, prefix=prefix, versions=True):
        add(blob, 'noncurrent' if getattr(blob, 'time_deleted', None) is not None else 'live')

    counters.listing_calls += 1
    try:
        for blob in storage.list_blobs(bucket, prefix=prefix, soft_deleted=True):
            add(blob, 'soft_deleted')
    except Exception as exc:  # noqa: BLE001 - buckets without soft delete reject the listing
        report['soft_delete'] = f'unavailable: {type(exc).__name__}'

    if created:
        report['earliest_created'] = _iso(min(created))
        report['latest_created'] = _iso(max(created))
    return report


# --- account state --------------------------------------------------------


def _account_state(client: Any, uid: str, counters: _Counters) -> dict[str, Any]:
    hold = _snapshot_dict(_get(client.collection('legal_holds').document(uid), counters))
    gate = _snapshot_dict(_get(client.collection('legal_hold_deletion_gates').document(uid), counters))
    deletion = _get(client.collection('account_deletions').document(uid), counters)
    return {
        'legal_hold': None if hold is None else {'active': None, 'issuer': None, **hold},
        'deletion_gate': (
            None if gate is None else {key: gate.get(key) for key in ('kind', 'state', 'started_at', 'finished_at')}
        ),
        'account_deletion_marker': bool(getattr(deletion, 'exists', False)),
    }


# --- backups --------------------------------------------------------------


def _duration_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, 'total_seconds'):
        return value.total_seconds()
    if hasattr(value, 'seconds'):
        return float(value.seconds)
    return None


def _backup_coverage(firestore_client: Any) -> dict[str, Any]:
    database_name = getattr(firestore_client, '_database_string', None)
    if not isinstance(database_name, str) or not database_name:
        return {'coverage': 'unknown', 'error_type': 'UnknownDatabase'}
    try:
        admin = _firestore_admin_client()
        database = admin.get_database(name=database_name)
        schedules = list(admin.list_backup_schedules(parent=database_name))
    except Exception as exc:  # noqa: BLE001 - coverage is best-effort, never fail the command
        return {'coverage': 'unknown', 'database': database_name, 'error_type': type(exc).__name__}
    pitr = getattr(database, 'point_in_time_recovery_enablement', None)
    return {
        'coverage': 'known',
        'database': database_name,
        'pitr_enablement': getattr(pitr, 'name', None) or (str(pitr) if pitr is not None else None),
        'version_retention_seconds': _duration_seconds(getattr(database, 'version_retention_period', None)),
        'earliest_version_time': _iso(getattr(database, 'earliest_version_time', None)),
        'backup_schedules': [
            {
                'name': getattr(schedule, 'name', None),
                'retention_seconds': _duration_seconds(getattr(schedule, 'retention', None)),
                'recurrence': 'weekly' if getattr(schedule, 'weekly_recurrence', None) else 'daily',
            }
            for schedule in schedules
        ],
    }


# --- handler --------------------------------------------------------------


def check(args: argparse.Namespace, ctx: Any, record: Any) -> dict[str, Any]:
    """Read-only; ``ctx.apply`` is ignored."""

    uid = args.uid
    conversation_id = getattr(args, 'conversation', None)
    month = getattr(args, 'month', None)
    if isinstance(month, str):
        month = _parse_month(month)
    if not conversation_id and month is None:
        raise RetentionCheckError('retention check needs --conversation or --month; it never scans a whole account')

    counters = _Counters()
    client = _firestore_client()
    selected, capped = _select_conversations(client, uid, conversation_id, month, counters)

    storage = _storage_client()
    conversations: list[dict[str, Any]] = []
    objects_total = 0
    with_audio = 0
    for cid, data in selected:
        report = _conversation_report(cid, data)
        report['storage'] = [
            _list_prefix(storage, bucket, prefix, counters) for bucket, prefix in _storage_prefixes(uid, cid)
        ]
        objects = sum(entry['objects'] for entry in report['storage'])
        objects_total += objects
        with_audio += 1 if objects else 0
        conversations.append(report)

    account = _account_state(client, uid, counters)
    backups = _backup_coverage(client)

    record.summary = {
        'conversations_checked': len(conversations),
        'conversations_with_audio': with_audio,
        'objects_total': objects_total,
        'listing_calls': counters.listing_calls,
        'firestore_reads': counters.firestore_reads,
        'capped': capped,
    }
    return {
        'account': account,
        'conversations': conversations,
        'capped': capped,
        'conversation_cap': CONVERSATION_CAP,
        'backups': backups,
        'counters': counters.as_dict(),
        **counters.as_dict(),
    }
