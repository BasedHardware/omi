#!/usr/bin/env python3
"""Move production-customer screen frames from the dev bucket to the production bucket.

Background: the dev backends serve production Firestore, and until the
data-plane bucket fix they wrote frame bytes to `based-hardware-dev-screen-frames`
and stamped the production frame docs with that bucket (or, before #19911, with
no bucket at all). Production hosts only read frames whose bucket is their own,
so those frames were invisible to production notes and screenshot views, and
their bytes sat in a bucket that dev identities can read.

Phases (each is dry-run unless --apply is given):

  scan          Read-only. Pages every `screen_frames` doc (collection group,
                ordered by document path, projected to `storage_bucket`) and
                prints aggregate counts only: frames by bucket class, distinct
                users and conversations to move, and mixed conversations.
  copy          Per conversation: server-side copy of each source frame's two
                objects into the destination bucket (create-only precondition),
                then repoint the frame doc's `storage_bucket` (compare-and-set on
                the doc's update time), then carry the conversation's source
                markers into the destination bucket's marker and bump its
                revision so clients refetch. Every change is journaled before
                the next one starts.
  rollback      Undo `copy` from the journal: restore each doc's prior
                `storage_bucket` (or remove it for unstamped legacy docs),
                restore the destination marker, and delete only the destination
                objects this script created (generation-matched). Valid until
                purge-source has run.
  purge-source  Irreversible (beyond the bucket's soft-delete window). Deletes
                the source objects of journaled frames whose doc points at the
                destination and whose destination objects exist, and drains
                `screen_frame_cleanup` records filed for the source bucket
                (no host owns that bucket after the fix). Requires
                --confirm-irreversible as well as --apply. Wait at least one
                hour after the last copy so no cached dev-signed URL is still
                handed out.

Conversations that already hold destination-bucket frames ("mixed") are skipped
and counted: merging two banner/cap sets is enforcement's job, not a copy's.

The cursor (state file) records the last conversation finished, so a stopped run
resumes; --rescan starts the scan over (rerun after the env flip to catch
stragglers). The journal is append-only JSONL with ids and bucket names only,
never frame content. Keep both files on the operator host, mode 0600.

Identity: one credential that can read the source bucket, write and delete in
the destination bucket, and read/write production Firestore. Scan needs only
Firestore read.

Examples (not executed by the PR that adds this script):
  python scripts/migrate_screen_frames_to_data_plane_bucket.py scan
  python scripts/migrate_screen_frames_to_data_plane_bucket.py copy --state /secure/sf.state.json \\
      --journal /secure/sf.journal.jsonl                      # dry run
  python scripts/migrate_screen_frames_to_data_plane_bucket.py copy --state ... --journal ... --apply
  python scripts/migrate_screen_frames_to_data_plane_bucket.py rollback --journal ... --apply
  python scripts/migrate_screen_frames_to_data_plane_bucket.py purge-source --journal ... --apply \\
      --confirm-irreversible
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from collections import Counter as Tally
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

# Mirrors database/screen_frames.py (pinned by tests/unit/test_migrate_screen_frames_bucket.py).
# Not imported: that module needs ENCRYPTION_SECRET and app clients, which an operator run must not.
LEGACY_SCREEN_FRAMES_BUCKET = 'based-hardware-dev-screen-frames'
ENV_STATE_FIELD = 'screen_frames_env_state'
LEGACY_STATE_FIELDS = {
    'revision': 'screen_frames_revision',
    'adjudicated_at': 'screen_frames_adjudicated_at',
    'selection_fingerprint': 'screen_frames_selection_fingerprint',
}

SOURCE_BUCKET = LEGACY_SCREEN_FRAMES_BUCKET
DEST_BUCKET = 'based-hardware-prod-screen-frames'
FIRESTORE_PROJECT = 'based-hardware'
FRAMES = 'screen_frames'
CLEANUP_COLLECTION = 'screen_frame_cleanup'
CAS_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def state_key(bucket: str) -> str:
    return re.sub(r'[^A-Za-z0-9_]', '_', bucket)


def bucket_state_field_paths(bucket: str) -> List[str]:
    if bucket == LEGACY_SCREEN_FRAMES_BUCKET:
        return list(LEGACY_STATE_FIELDS.values())
    return [f'{ENV_STATE_FIELD}.{state_key(bucket)}']


def bucket_state_from_conversation(conversation: Dict[str, Any], bucket: str) -> Dict[str, Any]:
    """``bucket``'s markers ({revision, adjudicated_at, selection_fingerprint}) from a conversation dict."""
    if bucket == LEGACY_SCREEN_FRAMES_BUCKET:
        return {
            field: conversation[name]
            for field, name in LEGACY_STATE_FIELDS.items()
            if conversation.get(name) is not None
        }
    state = conversation.get(ENV_STATE_FIELD)
    scoped = state.get(state_key(bucket)) if isinstance(state, dict) else None
    return {key: value for key, value in scoped.items() if value is not None} if isinstance(scoped, dict) else {}


def frame_bucket(data: Dict[str, Any]) -> Optional[str]:
    bucket = data.get('storage_bucket')
    return bucket if isinstance(bucket, str) and bucket else None


def is_source(data: Dict[str, Any], source: str) -> bool:
    bucket = frame_bucket(data)
    if bucket is None:
        return source == LEGACY_SCREEN_FRAMES_BUCKET
    return bucket == source


def object_paths(uid: str, conversation_id: str, frame_id: str) -> List[str]:
    return [f'{uid}/{conversation_id}/{frame_id}.jpg', f'{uid}/{conversation_id}/{frame_id}_thumb.jpg']


def split_frame_path(path: str) -> tuple[str, str, str]:
    """users/{uid}/conversations/{cid}/screen_frames/{fid} -> (uid, cid, fid)."""
    parts = path.split('/')
    if len(parts) != 6 or parts[0] != 'users' or parts[2] != 'conversations' or parts[4] != FRAMES:
        raise ValueError(f'unexpected screen_frames path shape ({len(parts)} segments)')
    return parts[1], parts[3], parts[5]


def conversation_path(uid: str, conversation_id: str) -> str:
    return f'users/{uid}/conversations/{conversation_id}'


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {'__dt__': value.isoformat()}
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {'__dt__'}:
            return datetime.fromisoformat(value['__dt__'])
        return {key: _decode(item) for key, item in value.items()}
    return value


class Journal:
    """Append-only JSONL; each line is fsynced before the next mutation starts."""

    def __init__(self, path: Optional[Path]):
        self.path = path

    def append(self, record: Dict[str, Any]) -> None:
        if self.path is None:
            return
        line = json.dumps(_encode({**record, 'at': datetime.now(timezone.utc)}), sort_keys=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, (line + '\n').encode())
            os.fsync(fd)
        finally:
            os.close(fd)

    def records(self) -> List[Dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return []
        return [_decode(json.loads(line)) for line in self.path.read_text().splitlines() if line.strip()]


def load_state(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {'cursor': None, 'complete': False}
    return json.loads(path.read_text())


def save_state(path: Optional[Path], state: Dict[str, Any]) -> None:
    if path is None:
        return
    temp = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(state, sort_keys=True).encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    temp.replace(path)


# ---------------------------------------------------------------------------
# Firestore paging
# ---------------------------------------------------------------------------


def iter_frame_docs(client: Any, *, cursor: Optional[str], page_size: int) -> Iterator[Any]:
    """Every screen_frames doc in document-path order, projected to `storage_bucket`."""
    last = cursor
    while True:
        query = client.collection_group(FRAMES).order_by('__name__').select(['storage_bucket'])
        if last:
            query = query.start_after({'__name__': client.document(last)})
        page = list(query.limit(page_size).stream())
        for snapshot in page:
            yield snapshot
        if len(page) < page_size:
            return
        last = page[-1].reference.path


def iter_conversations(client: Any, *, cursor: Optional[str], page_size: int) -> Iterator[tuple[str, List[Any]]]:
    """(conversation path, its frame snapshots) after ``cursor`` (a conversation path).

    A conversation's frames are contiguous in document-path order, so one paged
    collection-group stream yields whole groups without a query per conversation.
    """
    start = f'{cursor}/{FRAMES}/\uf8ff' if cursor else None
    current: Optional[str] = None
    group: List[Any] = []
    for snapshot in iter_frame_docs(client, cursor=start, page_size=page_size):
        uid, cid, _fid = split_frame_path(snapshot.reference.path)
        path = conversation_path(uid, cid)
        if path != current:
            if current is not None:
                yield current, group
            current, group = path, []
        group.append(snapshot)
    if current is not None:
        yield current, group


def conversation_frames(client: Any, path: str) -> List[Any]:
    return list(client.document(path).collection(FRAMES).select(['storage_bucket']).stream())


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


def run_scan(client: Any, *, source: str, dest: str, page_size: int = 500, limit: Optional[int] = None) -> Dict:
    frames = Tally()
    users_to_move: set = set()
    conversations: Dict[str, Tally] = {}
    for count, snapshot in enumerate(iter_frame_docs(client, cursor=None, page_size=page_size)):
        if limit is not None and count >= limit:
            break
        uid, cid, _fid = split_frame_path(snapshot.reference.path)
        data = snapshot.to_dict() or {}
        bucket = frame_bucket(data)
        if bucket is None:
            klass = 'unstamped'
        elif bucket == source:
            klass = 'source'
        elif bucket == dest:
            klass = 'dest'
        else:
            klass = 'other'
        frames[klass] += 1
        conversations.setdefault(conversation_path(uid, cid), Tally())[klass] += 1
        if is_source(data, source):
            users_to_move.add(uid)
    legacy_is_source = source == LEGACY_SCREEN_FRAMES_BUCKET

    def movable(tally: Tally) -> int:
        return tally['source'] + (tally['unstamped'] if legacy_is_source else 0)

    to_move = {path: tally for path, tally in conversations.items() if movable(tally)}
    mixed = {path for path, tally in to_move.items() if tally['dest']}
    frames_to_move = sum(movable(tally) for path, tally in to_move.items() if path not in mixed)
    return {
        'phase': 'scan',
        'source': source,
        'dest': dest,
        'frames_total': sum(frames.values()),
        'frames_by_class': dict(frames),
        'users_with_frames_to_move': len(users_to_move),
        'conversations_total': len(conversations),
        'conversations_to_move': len(to_move) - len(mixed),
        'frames_to_move': frames_to_move,
        'objects_to_move': 2 * frames_to_move,
        'conversations_mixed_skipped': len(mixed),
        'frames_in_mixed_conversations': sum(movable(to_move[path]) for path in mixed),
    }


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------


def _copy_object(storage_client: Any, source: str, dest: str, path: str) -> Dict[str, Any]:
    """Server-side create-only copy; returns {'status', 'generation'}."""
    from google.api_core.exceptions import NotFound, PreconditionFailed

    source_blob = storage_client.bucket(source).blob(path)
    try:
        source_blob.reload()
    except NotFound:
        return {'status': 'source_missing'}
    dest_blob = storage_client.bucket(dest).blob(path)
    try:
        token, _done, _total = dest_blob.rewrite(source_blob, if_generation_match=0)
        while token is not None:
            token, _done, _total = dest_blob.rewrite(source_blob, token=token, if_generation_match=0)
    except PreconditionFailed:
        dest_blob.reload()
        if dest_blob.md5_hash and dest_blob.md5_hash == source_blob.md5_hash:
            return {'status': 'already_present', 'generation': None}
        return {'status': 'dest_conflict'}
    return {'status': 'copied', 'generation': dest_blob.generation}


def _update_with_cas(doc_ref: Any, client: Any, build: Any, field_paths: List[str]) -> Any:
    """Read, build an update from the projected data, write guarded by the read's update time."""
    from google.api_core.exceptions import FailedPrecondition

    for _attempt in range(CAS_ATTEMPTS):
        snapshot = doc_ref.get(field_paths=field_paths)
        if not getattr(snapshot, 'exists', False):
            return None
        update = build(snapshot.to_dict() or {})
        if update is None:
            return None
        try:
            doc_ref.update(update, option=client.write_option(last_update_time=snapshot.update_time))
            return update
        except FailedPrecondition:
            continue
    raise RuntimeError('compare-and-set lost three times; rerun to resume')


def migrate_conversation(
    client: Any,
    storage_client: Any,
    path: str,
    *,
    source: str,
    dest: str,
    apply: bool,
    journal: Journal,
    scanned: Optional[List[Any]] = None,
    resuming: bool = False,
) -> Dict[str, int]:
    """Move one conversation. ``resuming`` marks the conversation a crashed run left
    half done: frames it already repointed are not "mixed", and its markers are
    carried even when no frame is left to move."""
    result = Tally()
    if (
        not resuming
        and scanned is not None
        and not any(is_source(snapshot.to_dict() or {}, source) for snapshot in scanned)
    ):
        return dict(result)
    # Re-read the whole conversation: the scan page is a projection taken earlier.
    snapshots = conversation_frames(client, path) if apply or scanned is None else scanned
    datas = [(snapshot, snapshot.to_dict() or {}) for snapshot in snapshots]
    to_move = [(snapshot, data) for snapshot, data in datas if is_source(data, source)]
    if not to_move and not resuming:
        return dict(result)
    if not resuming and any(frame_bucket(data) == dest for _snapshot, data in datas):
        result['conversations_mixed_skipped'] += 1
        result['frames_mixed_skipped'] += len(to_move)
        return dict(result)
    result['conversations_to_move'] += 1
    if not apply:
        result['frames_to_move'] += len(to_move)
        return dict(result)

    moved = 0
    for snapshot, data in to_move:
        uid, cid, fid = split_frame_path(snapshot.reference.path)
        copies = {}
        for object_path in object_paths(uid, cid, fid):
            copies[object_path] = _copy_object(storage_client, source, dest, object_path)
        statuses = {outcome['status'] for outcome in copies.values()}
        if statuses & {'source_missing', 'dest_conflict'}:
            for status in statuses & {'source_missing', 'dest_conflict'}:
                result[f'frames_{status}'] += 1
            journal.append({'op': 'copy_skipped', 'path': snapshot.reference.path, 'objects': copies})
            continue
        prior = frame_bucket(data)
        journal.append({'op': 'copy', 'path': snapshot.reference.path, 'prior_bucket': prior, 'objects': copies})

        def repoint(current: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            return {'storage_bucket': dest} if is_source(current, source) else None

        if _update_with_cas(snapshot.reference, client, repoint, ['storage_bucket']) is None:
            result['frames_changed_concurrently'] += 1
            continue
        journal.append({'op': 'repoint', 'path': snapshot.reference.path, 'prior_bucket': prior, 'bucket': dest})
        moved += 1
    result['frames_moved'] += moved
    if not moved and not resuming:
        return dict(result)

    key = state_key(dest)
    paths = bucket_state_field_paths(source) + bucket_state_field_paths(dest)
    recorded: Dict[str, Any] = {}

    def carry_markers(current: Dict[str, Any]) -> Dict[str, Any]:
        source_state = bucket_state_from_conversation(current, source)
        dest_state = bucket_state_from_conversation(current, dest)
        written = dict(dest_state)
        if dest_state.get('adjudicated_at') is None and source_state.get('adjudicated_at') is not None:
            written['adjudicated_at'] = source_state['adjudicated_at']
            if source_state.get('selection_fingerprint') is not None:
                written['selection_fingerprint'] = source_state['selection_fingerprint']
        written['revision'] = max(int(source_state.get('revision') or 0), int(dest_state.get('revision') or 0)) + 1
        recorded['prior'] = dest_state or None
        recorded['written'] = written
        return {f'{ENV_STATE_FIELD}.{key}': written}

    conversation_ref = client.document(path)
    if _update_with_cas(conversation_ref, client, carry_markers, paths) is not None:
        journal.append({'op': 'markers', 'path': path, 'bucket': dest, **recorded})
        result['conversations_markers_carried'] += 1
    return dict(result)


def run_copy(
    client: Any,
    storage_client: Any,
    *,
    source: str,
    dest: str,
    apply: bool,
    state_path: Optional[Path],
    journal: Journal,
    rescan: bool = False,
    page_size: int = 500,
    max_conversations: Optional[int] = None,
) -> Dict[str, Any]:
    if dest == LEGACY_SCREEN_FRAMES_BUCKET or dest == source:
        raise ValueError('destination must be a stamped, different bucket')
    state = {'cursor': None, 'complete': False} if rescan else load_state(state_path)
    totals = Tally()
    processed = 0
    for path, scanned in iter_conversations(client, cursor=state['cursor'] if apply else None, page_size=page_size):
        if max_conversations is not None and processed >= max_conversations:
            break
        resuming = apply and state.get('in_progress') == path
        if apply:
            state['in_progress'] = path
            save_state(state_path, state)
        totals.update(
            migrate_conversation(
                client,
                storage_client,
                path,
                source=source,
                dest=dest,
                apply=apply,
                journal=journal,
                scanned=scanned,
                resuming=resuming,
            )
        )
        processed += 1
        if apply:
            state['cursor'] = path
            state['in_progress'] = None
            save_state(state_path, state)
    else:
        if apply:
            state['complete'] = True
            save_state(state_path, state)
    return {
        'phase': 'copy',
        'apply': apply,
        'conversations_visited': processed,
        **dict(totals),
        'complete': state['complete'],
    }


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


def run_rollback(client: Any, storage_client: Any, *, dest: str, apply: bool, journal: Journal) -> Dict[str, Any]:
    from google.api_core.exceptions import NotFound, PreconditionFailed
    from google.cloud import firestore

    totals = Tally()
    records = journal.records()
    if any(record['op'] == 'purge' for record in records):
        raise RuntimeError('purge-source already ran for this journal; rollback would orphan frames')
    copies = {record['path']: record for record in records if record['op'] == 'copy'}
    for record in reversed(records):
        if record['op'] == 'markers':
            key = state_key(dest)

            def restore(current: Dict[str, Any], record=record) -> Optional[Dict[str, Any]]:
                if bucket_state_from_conversation(current, dest) != record['written']:
                    return None
                return {f'{ENV_STATE_FIELD}.{key}': record['prior'] or firestore.DELETE_FIELD}

            if not apply:
                totals['markers_to_restore'] += 1
            elif _update_with_cas(client.document(record['path']), client, restore, bucket_state_field_paths(dest)):
                totals['markers_restored'] += 1
            else:
                totals['markers_changed_since'] += 1
        elif record['op'] == 'repoint':

            def unpoint(current: Dict[str, Any], record=record) -> Optional[Dict[str, Any]]:
                if frame_bucket(current) != dest:
                    return None
                return {'storage_bucket': record['prior_bucket'] or firestore.DELETE_FIELD}

            if not apply:
                totals['frames_to_restore'] += 1
                continue
            if _update_with_cas(client.document(record['path']), client, unpoint, ['storage_bucket']):
                totals['frames_restored'] += 1
            else:
                totals['frames_changed_since'] += 1
    for path, record in copies.items():
        for object_path, outcome in record['objects'].items():
            if outcome.get('status') != 'copied':
                continue
            if not apply:
                totals['objects_to_delete'] += 1
                continue
            try:
                storage_client.bucket(dest).blob(object_path).delete(if_generation_match=outcome['generation'])
                totals['objects_deleted'] += 1
            except (NotFound, PreconditionFailed):
                totals['objects_changed_since'] += 1
    if apply:
        journal.append({'op': 'rollback', 'totals': dict(totals)})
    return {'phase': 'rollback', 'apply': apply, **dict(totals)}


# ---------------------------------------------------------------------------
# purge-source
# ---------------------------------------------------------------------------


def run_purge(
    client: Any, storage_client: Any, *, source: str, dest: str, apply: bool, journal: Journal, cleanup_limit: int = 500
) -> Dict[str, Any]:
    from google.api_core.exceptions import NotFound

    totals = Tally()
    records = journal.records()
    if any(record['op'] == 'rollback' for record in records):
        raise RuntimeError('this journal was rolled back; nothing to purge')
    repointed = {record['path'] for record in records if record['op'] == 'repoint'}
    for path in sorted(repointed):
        snapshot = client.document(path).get(field_paths=['storage_bucket'])
        if not getattr(snapshot, 'exists', False) or frame_bucket(snapshot.to_dict() or {}) != dest:
            totals['frames_not_on_dest'] += 1
            continue
        uid, cid, fid = split_frame_path(path)
        paths = object_paths(uid, cid, fid)
        if not all(storage_client.bucket(dest).blob(p).exists() for p in paths):
            totals['frames_dest_incomplete'] += 1
            continue
        if not apply:
            totals['objects_to_purge'] += len(paths)
            continue
        for object_path in paths:
            try:
                storage_client.bucket(source).blob(object_path).delete()
                totals['objects_purged'] += 1
            except NotFound:
                totals['objects_already_gone'] += 1
        journal.append({'op': 'purge', 'path': path})
    query = client.collection(CLEANUP_COLLECTION).where('bucket', '==', source).limit(cleanup_limit)
    for doc in query.stream():
        record = doc.to_dict() or {}
        if not apply:
            totals['cleanups_to_drain'] += 1
            continue
        for object_path in record.get('object_paths') or []:
            try:
                storage_client.bucket(source).blob(object_path).delete()
            except NotFound:
                pass
        doc.reference.delete()
        totals['cleanups_drained'] += 1
    return {'phase': 'purge-source', 'apply': apply, **dict(totals)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _clients(project: str, need_storage: bool):
    from google.cloud import firestore, storage

    return firestore.Client(project=project), (storage.Client(project=project) if need_storage else None)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('phase', choices=['scan', 'copy', 'rollback', 'purge-source'])
    parser.add_argument('--apply', action='store_true', help='perform writes (default: dry run)')
    parser.add_argument('--confirm-irreversible', action='store_true', help='required with purge-source --apply')
    parser.add_argument('--state', type=Path, help='resumable cursor file (copy)')
    parser.add_argument('--journal', type=Path, help='append-only JSONL journal (copy, rollback, purge-source)')
    parser.add_argument('--rescan', action='store_true', help='copy: restart from the first conversation')
    parser.add_argument('--source-bucket', default=SOURCE_BUCKET)
    parser.add_argument('--dest-bucket', default=DEST_BUCKET)
    parser.add_argument('--project', default=FIRESTORE_PROJECT)
    parser.add_argument('--page-size', type=int, default=500)
    parser.add_argument('--max-conversations', type=int)
    parser.add_argument('--scan-limit', type=int, help='scan: stop after this many frame docs')
    args = parser.parse_args(argv)

    if args.phase != 'scan' and args.journal is None:
        parser.error('--journal is required for copy, rollback and purge-source')
    if args.phase == 'copy' and args.apply and args.state is None:
        parser.error('copy --apply requires --state')
    if args.phase == 'purge-source' and args.apply and not args.confirm_irreversible:
        parser.error('purge-source --apply also requires --confirm-irreversible')

    client, storage_client = _clients(args.project, need_storage=args.phase != 'scan')
    journal = Journal(args.journal)
    lock_target = args.state or args.journal
    lock = lock_target.with_suffix(lock_target.suffix + '.lock').open('a') if lock_target else None
    try:
        if lock is not None:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.phase == 'scan':
            result = run_scan(
                client,
                source=args.source_bucket,
                dest=args.dest_bucket,
                page_size=args.page_size,
                limit=args.scan_limit,
            )
        elif args.phase == 'copy':
            result = run_copy(
                client,
                storage_client,
                source=args.source_bucket,
                dest=args.dest_bucket,
                apply=args.apply,
                state_path=args.state,
                journal=journal,
                rescan=args.rescan,
                page_size=args.page_size,
                max_conversations=args.max_conversations,
            )
        elif args.phase == 'rollback':
            result = run_rollback(client, storage_client, dest=args.dest_bucket, apply=args.apply, journal=journal)
        else:
            result = run_purge(
                client,
                storage_client,
                source=args.source_bucket,
                dest=args.dest_bucket,
                apply=args.apply,
                journal=journal,
            )
    finally:
        if lock is not None:
            lock.close()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
