#!/usr/bin/env python3
"""One bounded no-speech page. Default dry-run; aggregate output only.

Approval binds a freshly reconstructed plan; no plan, identity or object path is
printed. The private cursor and rollback ledger must not be committed or copied
into coordination systems. The kill switch gates only new closes; undo remains
available when it is off.
"""

import argparse
from contextlib import redirect_stdout, redirect_stderr
import fcntl
import json
import importlib
import logging
import os
from pathlib import Path
import secrets
import stat
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.refactor_modes import no_speech_terminal_enabled
from database._client import get_firestore_client
from config.no_speech_terminal import EXITS, OPERATION
from utils.batch_pipeline.no_speech_undo import undo_no_speech


class CountsOnlyParser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({'operation': OPERATION, 'outcome': 'invalid_arguments'}))
        raise SystemExit(2)


class Ledger:
    """Exclusive, mode-0600 write-ahead file; no audio or content payloads."""

    def __init__(self, path, *, create=False):
        path = Path(path)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError('private ledger path required')
        parent = path.parent.resolve()
        if not parent.is_dir() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
            raise ValueError('private ledger directory required')
        flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if create else 0)
        fd = os.open(path, flags, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            os.close(fd)
            raise ValueError('private ledger mode required')
        self.file = os.fdopen(fd, 'r+', encoding='utf-8')
        fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def token(self):
        return secrets.token_hex(16)

    def append(self, body):
        self.file.seek(0, os.SEEK_END)
        self.file.write(json.dumps(body, sort_keys=True) + '\n')
        self.file.flush()
        os.fsync(self.file.fileno())

    def prepare(self, entry, uid, cid, run_id):
        token = self.token()
        self.append(
            {
                'event': 'prepared',
                'token': token,
                'uid': uid,
                'conversation_id': cid,
                'run_id': run_id,
                'before_sha256': entry['row_sha256'],
                'revision': entry['revision'],
                'speech_seconds': entry.get('speech_seconds'),
                'audio_seconds': entry.get('audio_seconds'),
            }
        )
        return token

    def committed(self, token, revision):
        self.append({'event': 'committed', 'token': token, 'revision': revision})

    def entries(self):
        self.file.seek(0)
        prepared, committed = [], {}
        for line in self.file:
            body = json.loads(line)
            if body.get('event') == 'prepared':
                prepared.append(body)
            elif body.get('event') == 'committed':
                committed[body['token']] = body['revision']
            else:
                raise ValueError('ledger event unproven')
        for entry in prepared:
            entry['committed_revision'] = committed.get(entry['token'])
        return prepared

    def close(self):
        self.file.close()


class Refused(ValueError):
    pass


def _plan_dependencies():
    # Dynamic loading keeps secret-validating audio imports off the undo path.
    # All imports are defined here through the stdlib loader at this boundary.
    return SimpleNamespace(
        planner=importlib.import_module('utils.batch_pipeline.no_speech'),
        store=importlib.import_module('database.batch_pipeline_store').FirestoreStore,
        storage=importlib.import_module('utils.other.local_storage').create_storage_client,
        write_cursor=importlib.import_module('scripts.backfill_record_seal_nojob').write_cursor,
    )


def run(args):
    client = get_firestore_client()
    if args.undo:
        ledger = Ledger(args.ledger)
        try:
            entries = ledger.entries()[: args.limit]
            if args.apply:
                outcomes = undo_no_speech(
                    SimpleNamespace(client=client), entries, ledger=ledger, pace=args.pace_seconds
                )
            else:
                outcomes = {'would_restore': len(entries)}
        finally:
            ledger.close()
        return {
            'operation': OPERATION,
            'mode': 'apply' if args.apply else 'dry_run',
            'undo': True,
            'outcomes': outcomes,
        }
    if len(os.getenv('ENCRYPTION_SECRET', '')) < 32:
        raise Refused('encryption_secret_required')
    dependencies = _plan_dependencies()
    store = dependencies.store('batch_pipeline_prod', firestore_client=client)
    storage = dependencies.storage()
    after = json.loads(Path(args.after_file).read_text())['after'] if args.after_file else None
    paths, next_after = dependencies.planner.discover(client, limit=args.limit, after=after)
    planned = dependencies.planner.plan_no_speech(store, paths, storage, pace=args.pace_seconds)
    report = {**dependencies.planner.summary(planned), 'apply': args.apply}
    if args.next_file:
        dependencies.write_cursor(args.next_file, next_after)
    if args.apply:
        ledger = Ledger(args.ledger, create=True)
        try:
            outcomes = dependencies.planner.apply_no_speech(
                store,
                planned,
                args.approve_plan_sha256,
                storage,
                ledger=ledger,
                pace=args.pace_seconds,
            )
        finally:
            ledger.close()
        report.update(outcomes=outcomes, outcome_exits={key: EXITS[key] for key in outcomes})
    return report


def main(argv=None):
    parser = CountsOnlyParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=128)
    parser.add_argument('--after-file')
    parser.add_argument('--next-file')
    parser.add_argument('--pace-seconds', type=float, default=0.5)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-plan-sha256')
    parser.add_argument('--undo', action='store_true')
    parser.add_argument('--ledger')
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    allowed = {'prod-operator'} if args.apply else {'ro-prod', 'prod-operator'}
    if os.getenv('FIRESTORE_EMULATOR_HOST') or os.getenv('GCP_AGENT_TIER') not in allowed:
        parser.error('wrong identity')
    if not 1 <= args.limit <= 128:
        parser.error('bounded page required')
    if not 0.1 <= args.pace_seconds <= 60:
        parser.error('bounded pace required')
    if args.apply and not args.undo and not no_speech_terminal_enabled():
        parser.error('kill switch is off')
    if args.apply and not args.undo and not args.approve_plan_sha256:
        parser.error('explicit digest approval required')
    if (args.apply or args.undo) and not args.ledger:
        parser.error('private ledger required')
    if args.undo and (args.after_file or args.next_file):
        parser.error('undo reads only the private ledger')
    if args.after_file and args.next_file and Path(args.after_file).resolve() == Path(args.next_file).resolve():
        parser.error('distinct private cursor files required')
    os.environ['OMI_ENV_STAGE'] = 'prod'
    # SDK/provider diagnostics can contain private object paths. Suppress them
    # even on exceptions; only our closed aggregate vocabulary reaches output.
    try:
        with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
            report = run(args)
    except Refused as error:
        print(json.dumps({'operation': OPERATION, 'outcome': 'refused', 'reason': str(error)}))
        raise SystemExit(2)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'operation': OPERATION, 'outcome': 'error'}))
        sys.exit(1)
