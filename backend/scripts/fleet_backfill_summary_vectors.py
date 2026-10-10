#!/usr/bin/env python3
"""Fleet-wide, retry-safe driver for scripts/backfill_summary_vectors.py.

Reads a uid list (one uid per line), runs the per-user backfill for each uid
within a bounded window, and records durable per-uid progress in a state file
so any re-execution resumes exactly where the previous one stopped:

    {"done": {"<uid>": {"scanned": .., "selected": .., "created": .., ...}},
     "failed": {"<uid>": "<error-class>"},
     "started_at": .., "updated_at": ..}

Design contracts (mirror the per-user script's runbook):
- Dry-run by default; --apply required for writes. Cost sign-off reads the
  dry-run totals across the whole list first.
- A uid whose run fails (non-zero exit / error budget stop) goes to `failed`
  and the driver CONTINUES to the next uid; rerunning the driver skips done
  uids, and `--retry-failed` retries the failed ones.
- State file writes are atomic (tmp + rename) after every uid, so a killed
  run loses at most the in-flight uid.
- Embedding/Pinecone call rate is bounded by the per-user script itself
  (10% error budget per batch); this driver adds --sleep between users to
  smooth provider load.
- Output prints one JSON line per uid (counts only, never content or ids
  beyond the uid you supplied).

Usage (inside the backend container with the prod backend env):
    python scripts/fleet_backfill_summary_vectors.py \\
        --uid-file /mnt/inputs/uids.txt --state-file /tmp/fleet-state.json \\
        [--limit 500] [--since 2026-08-25T00:00:00Z] [--apply] [--sleep 5]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.backfill_summary_vectors import (  # noqa: E402
    backfill_user,
    iso_timestamp,
    metadata_rows,
)
from scripts.backfill_summary_vectors import DEFAULT_SINCE  # noqa: E402
from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: E402


def enumerate_user_uids(since: datetime) -> list[str]:
    """Distinct uids with at least one finalization job created since `since`.

    Pages the finalization-jobs collection ascending on created_at (the only
    indexed order), selecting only created_at and uid. Read-only.
    """
    from database._client import get_firestore_client

    client = get_firestore_client()
    jobs = client.collection('conversation_finalization_jobs')
    uids: set[str] = set()
    cursor = since
    last_snapshot = None
    while True:
        query = (
            jobs.where(filter=FieldFilter('created_at', '>=', cursor))
            .order_by('created_at')
            .select(['created_at', 'uid'])
            .limit(9999)
        )
        if last_snapshot is not None:
            # start_after on the snapshot gives a (created_at, __name__)
            # tiebreak, so same-timestamp jobs beyond a full page are not
            # skipped and the cursor never needs a hand-rolled epsilon.
            query = query.start_after(last_snapshot)
        docs = list(query.stream())
        if not docs:
            break
        for doc in docs:
            uid = (doc.get('uid') or '').strip()
            if uid:
                uids.add(uid)
        last_snapshot = docs[-1]
        if len(docs) < 9999:
            break
    return sorted(uids)


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            backup = path.with_suffix(".corrupt")
            path.rename(backup)
            print(f"state file corrupt; moved to {backup}", file=sys.stderr)
    return {"done": {}, "failed": {}, "started_at": None, "updated_at": None}


def save_state(path: Path, state: dict) -> None:
    state.pop('_mirror_read_ok', None)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.rename(path)


MIRROR_COLLECTION = '_meta_summary_vector_backfill'


def _mirror_doc_id(uid: str) -> str:
    # Shard by uid prefix: keeps each Firestore doc far below the 1 MiB cap
    # for a 27k-uid fleet (~256 shards x ~100-1k uids x ~170B).
    return f'shard-{uid[:2]}'


def load_state_durable(path: Path, uids: list[str]) -> dict:
    """Local state, mirrored to Firestore for cross-execution resume.

    A Cloud Run execution's /tmp dies with the task; the Firestore mirror
    (one shard doc per uid prefix) lets a rerun resume where the last one
    stopped. Only shards covering this run's uid list are read/written.
    Local file stays the working copy (fast, atomic).
    """
    state = load_state(path)
    state['_mirror_read_ok'] = True
    try:
        from database._client import get_firestore_client

        col = get_firestore_client().collection(MIRROR_COLLECTION)
        for shard_id in sorted({_mirror_doc_id(uid) for uid in uids}):
            doc = col.document(shard_id).get()
            if not doc.exists:
                continue
            remote = doc.to_dict() or {}
            for uid, record in (remote.get('done') or {}).items():
                state['done'].setdefault(uid, record)
            for uid, reason in (remote.get('failed') or {}).items():
                state['failed'].setdefault(uid, reason)
    except Exception as error:
        # A failed read leaves local state partial; mirror writes are skipped
        # for the whole run so partial state cannot erase remote entries.
        state['_mirror_read_ok'] = False
        print(f'state mirror read failed (mirror writes disabled this run): {type(error).__name__}', file=sys.stderr)
    return state


def save_state_durable(path: Path, state: dict, dirty_uids: list[str]) -> None:
    """Persist only the shards that this run actually changed.

    `dirty_uids` are the uids whose done/failed entries changed since load.
    Shards with no changed entries are never written: a merge write of an
    empty map would erase resume entries recorded by another execution, and
    rewriting untouched shards would multiply fleet write cost by the shard
    count.
    """
    mirror_ok = state.get('_mirror_read_ok', True)
    save_state(path, state)
    if not dirty_uids:
        return
    if not mirror_ok:
        print('mirror writes skipped: initial mirror read failed this run', file=sys.stderr)
        return
    try:
        from database._client import get_firestore_client

        col = get_firestore_client().collection(MIRROR_COLLECTION)
        dirty_shards = sorted({_mirror_doc_id(uid) for uid in dirty_uids})
        for shard_id in dirty_shards:
            done = {u: rec for u, rec in state.get('done', {}).items() if _mirror_doc_id(u) == shard_id}
            failed = {u: why for u, why in state.get('failed', {}).items() if _mirror_doc_id(u) == shard_id}
            if not done and not failed:
                continue
            # Omit empty maps from the payload: with merge=True the installed
            # client turns an empty dict into a parent-field replace, which
            # would erase the other map's entries recorded by another run.
            payload: dict = {'updated_at': state.get('updated_at')}
            if done:
                payload['done'] = done
            if failed:
                payload['failed'] = failed
            col.document(shard_id).set(payload, merge=True)
    except Exception as error:
        print(f'state mirror write failed (local only): {type(error).__name__}', file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--uid-file', help='one uid per line')
    parser.add_argument(
        '--all-users',
        action='store_true',
        help='Enumerate uids from conversation_finalization_jobs since --since instead of --uid-file.',
    )
    parser.add_argument('--state-file', required=True, help='durable progress JSON (created if missing)')
    parser.add_argument('--since', type=iso_timestamp, default=DEFAULT_SINCE)
    parser.add_argument('--limit', type=int, default=500, help='max eligible rows per uid')
    parser.add_argument('--sleep', type=float, default=2.0, help='seconds between users')
    parser.add_argument('--retry-failed', action='store_true', help='retry uids recorded as failed')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--dry-run', action='store_true', help='metadata-only preview (the default).')
    args = parser.parse_args(argv)

    state_path = Path(args.state_file)
    if args.all_users:
        uids = enumerate_user_uids(args.since)
    else:
        if not args.uid_file:
            parser.error('one of --uid-file or --all-users is required')
        uid_file = Path(args.uid_file)
        if not uid_file.exists():
            parser.error(f'uid file not found: {uid_file}')
        uids = sorted(
            {line.strip() for line in uid_file.read_text().splitlines() if line.strip() and not line.startswith('#')}
        )
    if not uids:
        parser.error('uid file is empty')
    if args.apply:
        from database import vector_db

        if vector_db.index is None:
            print('Refusing --apply: no vector index configured.', file=sys.stderr)
            return 2

    state = load_state_durable(state_path, uids)
    if state.get('started_at') is None:
        state['started_at'] = datetime.now(timezone.utc).isoformat()

    pending_uids = [u for u in uids if u not in state['done'] and (args.retry_failed or u not in state['failed'])]
    mode_str = 'APPLY' if args.apply else 'DRY-RUN'
    print(
        json.dumps(
            {
                'mode': mode_str,
                'total_uids': len(uids),
                'already_done': len(state['done']),
                'already_failed': len(state['failed']),
                'to_run': len(pending_uids),
            }
        )
    )

    exit_code = 0
    for uid in pending_uids:
        try:
            summary = backfill_user(
                uid,
                metadata_rows(uid, args.since, scan_limit=args.limit * 10),
                since=args.since,
                limit=args.limit,
                apply=args.apply,
                write=_writer() if args.apply else None,
            )
        except Exception as error:
            if args.apply:
                state['failed'][uid] = type(error).__name__
                save_state_durable(state_path, state, [uid])
            print(json.dumps({'uid': uid, 'outcome': 'select_failed', 'error': type(error).__name__}))
            exit_code = 1
            time.sleep(args.sleep)
            continue
        record = _asdict(summary)
        if not args.apply:
            # A cost preview must never poison the resume state: a later
            # --apply has to revisit every previewed uid.
            print(json.dumps({'uid': uid, 'outcome': 'preview', **record}))
            time.sleep(args.sleep)
            continue
        if summary.stopped_error_budget or summary.error:
            state['failed'][uid] = f'error_budget:{summary.error}'
            exit_code = 1
        else:
            state['done'][uid] = record
            state['failed'].pop(uid, None)
        save_state_durable(state_path, state, [uid])
        print(json.dumps({'uid': uid, 'outcome': 'applied', **record}))
        time.sleep(args.sleep)
    if args.apply:
        save_state_durable(state_path, state, [])
    print(
        json.dumps(
            {'mode': mode_str, 'finished': True, 'done_total': len(state['done']), 'failed_total': len(state['failed'])}
        )
    )
    return exit_code


def _writer():
    from scripts.backfill_summary_vectors import write_summary

    return write_summary


def _asdict(summary):
    from dataclasses import asdict

    return asdict(summary)


if __name__ == '__main__':
    sys.exit(main())
