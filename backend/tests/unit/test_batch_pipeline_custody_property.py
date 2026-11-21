"""Custody property: the phone hears ``completed`` only when every unit of the upload is terminal.

`completed` is the one status released phones treat as permission to mark the WAL synced and later
age-delete their independent audio copy (app/lib/services/wals/sync_job_policy.dart). #24335 found three
branches of ``durable_status`` that answered ``completed`` while units were still held. Instead of one
golden per branch, this enumerates every per-unit job state beside every ledger shape and kill-switch
setting, and checks the property over the whole product. The distinct response shapes are pinned in a
shared fixture that the phone test replays through its real terminal policy, so a new backend answer
cannot reach phones without a phone-side custody check.
"""

from dataclasses import replace
import itertools
import json
from pathlib import Path

import pytest

from tests.unit.test_batch_pipeline_intake import NAMESPACE, cohort, proposal, submit  # noqa: F401
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.intake import durable_status

FIXTURE = Path(__file__).parents[1] / 'fixtures/custody_status_shapes.json'

# One unit's stored state: (state, recovery_state, open operator intent).
IN_FLIGHT = [(state, None, None) for state in ('ready', 'leased', 'retry', 'result_ready')]
COMMITTED = [('committed', recovery, None) for recovery in (None, 'held', 'recovered')]
QUARANTINED = [
    ('quarantined', recovery, None)
    for recovery in (None, 'held', 'prepared', 'running', 'failed_held', 'recovered', 'cancelled')
]
INTENTS = [
    ('quarantined', 'failed_held', intent)
    for intent in ('speech_redrive', 'terminal_disposition', 'silence_disposition')
]
UNIT_STATES = IN_FLIGHT + COMMITTED + QUARANTINED + INTENTS

# Recovery states under which a unit's words are still owed (#23932 also marks a committed job `held`
# when its projection receipt is quarantine-held).
UNRESOLVED_RECOVERY = {'held', 'prepared', 'running', 'failed_held'}


def unit_terminal(state, recovery, intent):
    """Words for this unit are durably projected; nothing automatic or operator-driven is still owed."""
    return state == 'committed' and recovery not in UNRESOLVED_RECOVERY and intent is None


def ledger(kind, total):
    if kind == 'admitted':
        return None  # as written by admission
    if kind == 'partial':
        held = 1
        return {
            'status': 'partial',
            'result': {
                'new_memories': [],
                'updated_memories': [],
                'failed_segments': held,
                'held_segments': held,
                'total_segments': total,
                'errors': [],
                'outcome': 'partial',
            },
        }
    if kind == 'completed_held_audio':
        result = {'failed_segments': 0, 'total_segments': total, 'errors': [], 'held_audio': True}
        return {'status': 'completed', 'result': result}
    result = {'new_memories': [], 'updated_memories': [], 'failed_segments': 0, 'total_segments': total}
    return {'status': 'completed', 'result': {**result, 'errors': [], 'outcome': 'success'}}


LEDGERS = ['admitted', 'partial', 'completed_held_audio', 'completed']


def upload(units, ledger_kind):
    store = MemoryStore()
    works, binding = proposal()
    ids = tuple(f'segment-{index}' for index in range(len(units)))
    batch = [replace(works[0], segment_id=sid, capture_at=works[0].capture_at + 30 * i) for i, sid in enumerate(ids)]
    submit(store, batch, replace(binding, segment_ids=ids))
    for sid, (state, recovery, intent) in zip(ids, units):
        job = store.rows['jobs', sid]
        job.update(state=state, recovery_state=recovery, merge_pending=False)
        if state == 'committed':
            job['conversation_id'] = f'projected-{sid}'
        if intent:
            job[intent] = {'state': 'prepared'}
    row = ledger(ledger_kind, len(units))
    if row is not None:
        store.rows['content', 'synthetic-owner/content'].update(row)
    return store


def cases():
    for size in (1, 2):
        # durable_status reads units as a set (no order dependence), so unordered pairs cover the product.
        for units in itertools.combinations_with_replacement(UNIT_STATES, size):
            for ledger_kind in LEDGERS:
                # A completed ledger is the projection's own receipt that every unit landed; it is
                # authoritative over job rows (test_status_is_durable_and_completed_result_is_authoritative)
                # and is only written once all units commit. Pair it only with all-terminal units.
                if ledger_kind == 'completed' and not all(unit_terminal(*unit) for unit in units):
                    continue
                yield units, ledger_kind


def shape(status):
    return {key: status.get(key) for key in ('status', 'reason_code', 'poll_after_ms')}


_COLLECTED = {}  # held-terminal kill switch value -> (resolved, unresolved, violations); one sweep each


def collect(monkeypatch, held_terminal):
    if held_terminal not in _COLLECTED:
        monkeypatch.setenv('BATCH_PIPELINE_HELD_TERMINAL_STATUS_ENABLED', held_terminal)
        resolved, unresolved, violations = set(), set(), []
        for units, ledger_kind in cases():
            status = durable_status(upload(units, ledger_kind), 'synthetic-owner', 'bp_first')
            key = json.dumps(shape(status), sort_keys=True)
            if all(unit_terminal(*unit) for unit in units):
                resolved.add(key)
            else:
                unresolved.add(key)
                if status['status'] == 'completed':
                    violations.append((units, ledger_kind))
        _COLLECTED[held_terminal] = resolved, unresolved, violations
    return _COLLECTED[held_terminal]


@pytest.mark.parametrize('held_terminal', ['true', 'false'])
def test_phone_hears_completed_only_when_every_unit_is_terminal(cohort, monkeypatch, held_terminal):  # noqa: F811
    _, _, violations = collect(monkeypatch, held_terminal)
    assert violations == [], f'{len(violations)} unresolved uploads answered completed, e.g. {violations[:3]}'


def test_every_response_shape_is_pinned_for_the_phone_custody_test(cohort, monkeypatch):  # noqa: F811
    shapes = {'resolved': set(), 'unresolved': set()}
    for held_terminal in ('true', 'false'):
        resolved, unresolved, _ = collect(monkeypatch, held_terminal)
        shapes['resolved'] |= resolved
        shapes['unresolved'] |= unresolved
    produced = {name: sorted((json.loads(item) for item in items), key=json.dumps) for name, items in shapes.items()}
    pinned = json.loads(FIXTURE.read_text())
    # A new backend answer must be added to the fixture, which the phone test replays through
    # syncJobTerminalPolicy (app/test/unit/custody_status_shapes_test.dart). The message is the new fixture.
    assert produced == {name: pinned[name] for name in ('resolved', 'unresolved')}, json.dumps(
        produced, indent=2, sort_keys=True
    )
