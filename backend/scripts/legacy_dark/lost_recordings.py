"""Zero-lost-recordings census for legacy dark (contract (h), soak check 5).

Read-only. Emits the ``lost_recordings`` evidence that
``scripts/parity/soak_check.py`` check 5 consumes, as aggregate counts only
(never a uid, content id, job id or transcript)::

    source ~/.local/bin/gcp-agent-env.sh ro-prod        # ro-dev for staging
    cd backend && .venv/bin/python -m scripts.legacy_dark.lost_recordings \
        --env prod --since <draining write time, ISO-8601> [--until <ISO>] --output evidence.json

Definitions (lead ruling 10-20):

* **accepted**: ``sync_content_ledger`` rows whose ``created_at`` lies in
  ``[since, min(until, now - grace)]`` (grace 1h, the soak's stuck-unit bound).
  Only batch admission writes ``created_at``
  (``database/batch_pipeline_intake.py`` ``admit``); outside ``on`` no legacy
  claim may be created, and any that is would show in
  ``omi_legacy_sync_admissions_total`` (soak check 1), not here.
* **accounted**: the row is ``completed`` with a valid result (the projection
  receipt), or a valid ``stt_cap_hold_v1`` hold, or every batch segment job it
  names has reached a terminal or custody state (``TERMINAL_JOB_STATES``).
  Quarantined units keep their audio for recovery; they are counted as
  accounted and reported separately as ``in_custody``.
* **lost**: ``accepted - accounted``.
* **legacy_and_batch**: a ``batch_v1`` row that also carries a field only the
  legacy runner writes (``LEGACY_WRITER_FIELDS``; batch projection also writes
  ``processed_segment_ids``, so it is not one). Batch admission replaces the
  whole row, so such a field means a legacy writer touched content batch owns.
  Rows batch adopted from a stranded legacy claim carry
  ``adopted_legacy_job_id`` and are counted as ``adopted`` (informational).

Fail closed: any failed read, including a missing collection-group index on
``sync_content_ledger.created_at`` (``FIELD_INDEX_REQUIREMENTS``), omits
``lost_recordings`` from the evidence. ``soak_check`` then reports check 5 as
PENDING (``input_missing``), never PASS.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Optional

LEDGER_COLLECTION = 'sync_content_ledger'
GRACE_SECONDS = 3600
BATCH_PROTOCOL = 'batch_v1'
CAP_HOLD_PROTOCOL = 'stt_cap_hold_v1'
# Batch segment job states that end the unit's obligation (custody included):
# the audio was transcribed and committed, or the owner erased it, or privacy
# blocked it, or the unit is quarantined with its audio held for recovery.
TERMINAL_JOB_STATES = frozenset({'completed', 'committed', 'erased', 'privacy_blocked', 'dead', 'quarantined'})
CUSTODY_JOB_STATES = frozenset({'quarantined'})
# Fields only the legacy runner writes on a ledger row (database/sync_ledger.py). Not
# ``processed_segment_ids``: batch projection writes it too
# (database/batch_pipeline_projection_session.py).
LEGACY_WRITER_FIELDS = ('partial_result', 'ledger_run_token', 'ledger_run_epoch')
ADOPTION_MARKER = 'adopted_legacy_job_id'


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp must carry a timezone')
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def classify(
    rows: Iterable[Mapping[str, Any]],
    job_states: Callable[[str, list[str]], dict[str, Optional[str]]],
    *,
    valid_completed: Callable[[Any], bool],
    valid_held: Callable[[Any], bool],
) -> dict[str, Any]:
    """Pure accounting over ledger rows. ``job_states(namespace, segment_ids)`` maps id -> state (None if absent)."""
    accepted = accounted = double = adopted = custody = 0
    pending_states: Counter[str] = Counter()
    for row in rows:
        accepted += 1
        protocol = row.get('dispatch_protocol')
        status = row.get('status')
        if protocol == BATCH_PROTOCOL:
            if any(field in row for field in LEGACY_WRITER_FIELDS):
                double += 1
            if row.get(ADOPTION_MARKER):
                adopted += 1
        if status == 'completed' and valid_completed(row.get('result')):
            accounted += 1
            continue
        if protocol == CAP_HOLD_PROTOCOL and status == 'held' and valid_held(row.get('result')):
            accounted += 1
            continue
        batch = row.get('batch_pipeline') or {}
        segment_ids = [s for s in batch.get('segment_ids') or [] if isinstance(s, str)]
        namespace = batch.get('namespace')
        if protocol == BATCH_PROTOCOL and segment_ids and isinstance(namespace, str):
            states = job_states(namespace, segment_ids)
            if all(states.get(s) in TERMINAL_JOB_STATES for s in segment_ids):
                accounted += 1
                if any(states.get(s) in CUSTODY_JOB_STATES for s in segment_ids):
                    custody += 1
                continue
            for s in segment_ids:
                if states.get(s) not in TERMINAL_JOB_STATES:
                    pending_states[states.get(s) or 'absent'] += 1
        else:
            pending_states[f'ledger:{status or "none"}'] += 1
    return {
        'accepted_content_ids': accepted,
        'receipted_or_terminal_content_ids': accounted,
        'lost_content_ids': accepted - accounted,
        'legacy_and_batch_content_ids': double,
        'adopted': adopted,
        'in_custody': custody,
        'unaccounted_states': dict(sorted(pending_states.items())),
    }


def take_census(env: str, since: datetime, until: Optional[datetime], now: datetime) -> dict[str, Any]:
    """Read the ledger window and segment jobs; raise on any read failure (caller fails closed)."""
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter

    from database.sync_ledger import is_valid_completed_sync_content_result, is_valid_held_sync_content_result
    from scripts.legacy_dark.drain_census import ENVIRONMENTS

    project, database, _location = ENVIRONMENTS[env]
    client = firestore.Client(project=project, database=database)
    end = min(until or now, now - timedelta(seconds=GRACE_SECONDS))
    if end < since:
        raise ValueError('window_not_yet_closed')
    query = (
        client.collection_group(LEDGER_COLLECTION)
        .where(filter=FieldFilter('created_at', '>=', since))
        .where(filter=FieldFilter('created_at', '<=', end))
    )
    rows = [snapshot.to_dict() or {} for snapshot in query.stream()]

    def job_states(namespace: str, segment_ids: list[str]) -> dict[str, Optional[str]]:
        collection = client.collection(f'{namespace}_jobs')
        states: dict[str, Optional[str]] = {}
        for snapshot in client.get_all([collection.document(s) for s in segment_ids]):
            data = snapshot.to_dict() if snapshot.exists else None
            states[snapshot.id] = (data or {}).get('state') if data is not None else None
        return states

    counts = classify(
        rows,
        job_states,
        valid_completed=is_valid_completed_sync_content_result,
        valid_held=is_valid_held_sync_content_result,
    )
    return {'since': _iso(since), 'until': _iso(end), **counts}


def build_evidence(env: str, since: datetime, until: Optional[datetime], now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    try:
        census = take_census(env, since, until, now)
    except Exception as error:  # fail closed: soak check 5 stays PENDING
        return {'lost_recordings_error': type(error).__name__, 'env': env, 'observed_at': _iso(now)}
    return {'lost_recordings': census, 'env': env, 'observed_at': _iso(now)}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--env', required=True, choices=('prod', 'staging'))
    parser.add_argument('--since', required=True, help='draining write time (ISO-8601 with zone)')
    parser.add_argument('--until', help='window end (ISO-8601); default now - 1h')
    parser.add_argument('--output', help='write the evidence JSON here as well as stdout')
    args = parser.parse_args(argv)
    evidence = build_evidence(
        args.env, _parse_iso(args.since), _parse_iso(args.until) if args.until else None, datetime.now(timezone.utc)
    )
    text = json.dumps(evidence, sort_keys=True)
    if args.output:
        with open(args.output, 'w') as handle:
            handle.write(text + '\n')
    print(text)
    return 0 if 'lost_recordings' in evidence else 3


if __name__ == '__main__':
    sys.exit(main())
