"""One heavy locked closure through the real live builder: load, planner and commit on the emulator.

The shape is the one 21 production owners were parked on (2026-11-26, SCA-2918). One long recording owns
hundreds of locked one-line windows (median 8 s) left by the old moving cap cut. Settled neighbour
recordings join through the time query. Only the LLM, Cloud Tasks and notes drain are stubbed. Every
Firestore read, transaction and write is real. The test asserts custody (pending cleared, claims and
published ownership kept, every recording segment owned by exactly one live row) and reports the cost
of each pass. Set V3_CLOSURE_COST_REPORT to a file path to save the per-pass numbers as JSON lines.

Run: FIRESTORE_EMULATOR_HOST=127.0.0.1:<port> GOOGLE_CLOUD_PROJECT=demo-v3-closure-cost \\
     pytest -s tests/integration/test_conversations_v3_locked_closure_cost_firestore.py
"""

from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
import os
import time
from unittest.mock import patch
from uuid import uuid4

import pytest

from database import _client
from database import conversations_v3 as store, conversations_v3_leases as leases, firestore_write_probe
from testing.firestore_read_budget import delta_reads, snapshot_reads
from utils.conversations.v3 import outline as outline_module, refinement, service

ROOT = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=2)
STEP, SPOKEN = 8, 6  # one six-second line every eight seconds: the measured median fragment


@pytest.fixture
def owner(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('requires a loopback Firestore emulator')
    monkeypatch.setenv('CONVERSATIONS_V3_SKIP_UNCHANGED_WRITES', 'on')
    monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', '*')
    monkeypatch.setenv('CONVERSATIONS_V3_TASKS_URL', 'https://tasks.example.test')
    client = _client.get_firestore_client()
    user = client.collection('users').document('test-' + uuid4().hex)
    try:
        yield client, user
    finally:
        client.recursive_delete(user)


LONG = ' '.join(['and then we planned the rest of the synthetic day together'] * 4)


def segment(rid, index, offset, *, long=False):
    return {
        'id': f'{rid}-s{index}',
        'text': f'Synthetic heavy owner line {index} about the plan for the day' + (' ' + LONG if long else ''),
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'is_user': True,
        'start': float(offset),
        'end': float(offset + SPOKEN),
    }


def fragment(rid, seg, started, *, eligible):
    start = started + timedelta(seconds=seg['start'])
    end = started + timedelta(seconds=seg['end'])
    row = {
        'id': f"frag-{seg['id']}",
        'v3_derived': True,
        'status': 'completed',
        'source': 'omi',
        'language': 'en',
        'data_protection_level': 'standard',
        'created_at': end,
        'started_at': start,
        'finished_at': end,
        'v3_recording_ids': [rid],
        'kind': 'conversation',
        'discarded': False,
        'transcript_segments': [{**seg, 'start': 0.0, 'end': float(SPOKEN)}],
        'structured': {
            'title': 'Synthetic fragment',
            'overview': 'A one-line card left by the old cap cut.',
            'emoji': '💬',
            'category': 'other',
            'sections': [{'title': 'Plan'}],
        },
    }
    if eligible:
        row.update(summary_covers_through=end, visibility='private')
    return row


def recording(rid, started, lines, *, pending, claimed, eligible):
    segments = [segment(rid, i, i * STEP, long=eligible == 'long') for i in range(lines)]
    rows = [fragment(rid, seg, started, eligible=eligible) for seg in segments[:claimed]]
    doc = {
        'id': rid,
        'recording': True,
        'status': 'completed',
        'source': 'omi',
        'language': 'en',
        'data_protection_level': 'standard',
        'created_at': started,
        'started_at': started,
        'finished_at': started + timedelta(seconds=segments[-1]['end']),
        'transcript_segments': segments,
        'claims': [{'conversation_id': r['id'], 'start': r['started_at'], 'end': r['finished_at']} for r in rows],
        'v3_pending': pending,
        'v3_pending_since': ROOT if pending else None,
    }
    return doc, rows


def bridge(later, earlier, *, eligible):
    """One window spanning two adjacent recordings: the earlier one's last line and the later one's first."""
    last, first = earlier['transcript_segments'][-1], later['transcript_segments'][0]
    start = earlier['started_at'] + timedelta(seconds=last['start'])
    end = later['started_at'] + timedelta(seconds=first['end'])
    offset = lambda rec, seg: (rec['started_at'] + timedelta(seconds=seg['start']) - start).total_seconds()
    row = fragment(earlier['id'], last, earlier['started_at'], eligible=eligible)
    row.update(
        id=f"bridge-{earlier['id']}-{later['id']}",
        finished_at=end,
        v3_recording_ids=[earlier['id'], later['id']],
        transcript_segments=[
            {**seg, 'start': offset(rec, seg), 'end': offset(rec, seg) + SPOKEN}
            for rec, seg in ((earlier, last), (later, first))
        ],
    )
    if eligible:
        row['summary_covers_through'] = end
    for rec, seg in ((earlier, last), (later, first)):
        span = rec['started_at'] + timedelta(seconds=seg['start']), rec['started_at'] + timedelta(seconds=seg['end'])
        rec['claims'] = [c for c in rec['claims'] if c['conversation_id'] != f"frag-{seg['id']}"]
        rec['claims'].append({'conversation_id': row['id'], 'start': span[0], 'end': span[1]})
    return row, {f"frag-{last['id']}", f"frag-{first['id']}"}


def seed(user, *, heavy, neighbours, per_neighbour, tail, eligible):
    """One pending heavy recording plus settled neighbours chained to it by windows that span two recordings.

    Production closures reached 17-64 recordings with rows naming up to 5-18 recordings; a settled
    neighbour joins only through such a row (or the pending recording's 20-minute time query).
    """
    heavy_doc, heavy_rows = recording('heavy', ROOT, heavy + tail, pending=True, claimed=heavy, eligible=eligible)
    chain, rows = [heavy_doc], {r['id']: r for r in heavy_rows}
    span = per_neighbour * STEP + 2
    for k in range(neighbours):
        started = ROOT - timedelta(seconds=(k + 1) * span)
        doc, own = recording(
            f'n{k:02d}', started, per_neighbour, pending=False, claimed=per_neighbour, eligible=eligible
        )
        rows.update((r['id'], r) for r in own)
        joined, replaced = bridge(chain[-1], doc, eligible=eligible)
        for cid in replaced:
            rows.pop(cid, None)
        rows[joined['id']] = joined
        chain.append(doc)
    docs = [*chain, *rows.values()]
    coll = user.collection('conversations')
    for start in range(0, len(docs), 400):
        batch = user._client.batch()
        for doc in docs[start : start + 400]:
            batch.set(coll.document(doc['id']), doc)
        batch.commit()
    user.collection('conversation_v3_leases').document('builder').set(
        {
            'v3_blocked_reason': 'v3_derived_budget',
            'v3_blocked_count': 4,
            'v3_backoff_until': datetime.now(timezone.utc) - timedelta(minutes=1),
            'v3_bounded_pending_attempted': True,
        }
    )
    return len(rows), len(chain)


def append_tail(user, count):
    """Late speech lands on the heavy recording: the next pass is a steady-state drain pass."""
    ref = user.collection('conversations').document('heavy')
    doc = ref.get().to_dict()
    n = len(doc['transcript_segments'])
    long = len(doc['transcript_segments'][0]['text']) > 100
    segments = doc['transcript_segments'] + [segment('heavy', n + i, (n + i) * STEP, long=long) for i in range(count)]
    ref.update(
        {
            'transcript_segments': segments,
            'finished_at': doc['started_at'] + timedelta(seconds=segments[-1]['end']),
            'v3_pending': True,
            'v3_pending_since': datetime.now(timezone.utc) - timedelta(hours=1),
        }
    )


def outline_entries(group, every):
    count = len(group['lines'])
    firsts = range(1, count + 1, every) if every else [1]
    return json.dumps(
        {
            'conversations': [
                {
                    'first_line': f,
                    'title': 'Synthetic plan',
                    'line': 'You planned the day.',
                    'kind': 'conversation',
                    # Different people per topic keep sit-down joining from merging the topics back together.
                    **({'people': [f'Person {f}']} if every else {}),
                }
                for f in firsts
            ]
        }
    )


async def one_pass(client, user, *, outline_every, after_batch=None):
    """One reconcile (no inline follow-up pass), with its reads, writes, transactions and phase timings."""
    paths, commits, rollbacks, phases, outline_calls = [], [], [], Counter(), []
    reads_at = {}
    api = client._firestore_api
    original_commit, original_rollback = api.commit, api.rollback
    after = firestore_write_probe._after
    real_parse = outline_module.parse

    def capture(writes, response, partial):
        after(writes, response, partial)
        if not partial:
            paths.extend('/'.join(firestore_write_probe.write_op(w)[2][2:]) for w in writes)

    def commit(*args, **kwargs):
        request = kwargs.get('request') or {}
        commits.append(bool(request.get('transaction')))
        result = original_commit(*args, **kwargs)
        if after_batch and phases['in_commit'] and len(request.get('writes') or ()) > 1:
            after_batch()  # projection batches only; a lease renewal writes one document
        return result

    def rollback(*args, **kwargs):
        rollbacks.append(1)
        return original_rollback(*args, **kwargs)

    def timed(name, fn):
        def run(*args, **kwargs):
            before, started, rpcs = snapshot_reads(), time.monotonic(), len(commits)
            phases['in_' + name] += 1
            phases['calls_' + name] += 1
            try:
                return fn(*args, **kwargs)
            finally:
                phases['in_' + name] -= 1
                phases[name] += time.monotonic() - started
                phases[name + '_transactions'] += len(commits) - rpcs
                reads_at[name] = reads_at.get(name, 0) + delta_reads(before).reads

        return run

    real_candidate = refinement.candidate
    refined = []

    def candidate(windows, existing, recordings):
        chosen = real_candidate(windows, existing, recordings)
        eligible = sum(1 for row in existing.values() if refinement._eligible(row))
        refined.append((len(windows), max((len(w['lines']) for w in windows), default=0), eligible, chosen))
        return chosen

    def model(uid, messages):
        outline_calls.append(1)
        return '{}'

    with ExitStack() as stack:
        stack.enter_context(patch.object(firestore_write_probe, '_after', side_effect=capture))
        stack.enter_context(patch.object(api, 'commit', side_effect=commit))
        stack.enter_context(patch.object(api, 'rollback', side_effect=rollback))
        stack.enter_context(patch.object(store, 'load', timed('load', store.load)))
        stack.enter_context(patch.object(store, 'commit_projection', timed('commit', store.commit_projection)))
        stack.enter_context(patch.object(service, '_commit', timed('commit_outer', service._commit)))
        stack.enter_context(patch.object(service.models, 'outline', model))
        stack.enter_context(
            patch.object(outline_module, 'parse', lambda c, g: real_parse(outline_entries(g, outline_every), g))
        )
        stack.enter_context(patch.object(service.refinement, 'candidate', candidate))
        stack.enter_context(patch.object(service.context, 'outline_sources', lambda *a: ({}, [], [])))
        stack.enter_context(patch.object(service, 'enqueue', lambda *a, **k: None))
        stack.enter_context(patch.object(service, 'drain_processing', lambda uid: _noop()))
        stack.enter_context(patch.object(service, 'has_pending', lambda *a, **k: False))
        before, started = snapshot_reads(), time.monotonic()
        result = await service.reconcile(user.id)
        elapsed = time.monotonic() - started
        reads = delta_reads(before)
    conversation_writes = [p for p in paths if p.startswith('conversations/')]
    return {
        'result': result,
        'seconds': round(elapsed, 2),
        'load_seconds': round(phases['load'], 2),
        'commit_seconds': round(phases['commit'], 2),
        'commit_calls': int(phases['calls_commit']),
        'plan_seconds': round(elapsed - phases['load'] - phases['commit_outer'], 2),
        'reads': int(reads.reads),
        'reads_load': int(reads_at.get('load', 0)),
        'reads_commit': int(reads_at.get('commit', 0)),
        'writes': len(paths),
        'writes_conversations': len(conversation_writes),
        'writes_other': dict(Counter(p.split('/')[0] for p in paths if not p.startswith('conversations/'))),
        'transactions': sum(commits),
        'transactions_commit': int(phases['commit_transactions']),
        'commit_rpcs': len(commits),
        'rollbacks': len(rollbacks),
        'outline_calls': len(outline_calls),
        # refinement.candidate runs before preserve_finished_windows (refine_locked: custom timing on)
        'refinement_offered': bool(refined),
        'proposed_windows': refined[0][0] if refined else None,
        'largest_window_lines': refined[0][1] if refined else None,
        'refinement_eligible_rows': refined[0][2] if refined else None,
        'refinement_donors': len(refined[0][3][1]['_v3_absorbed']) if refined and refined[0][3] else 0,
    }


async def _noop():
    return None


def custody(user, *, recordings):
    """Pending cleared, park cleared, every recording segment owned by exactly one live derived row."""
    docs = {
        d.id: (store.decode_row(user.id, d) if (d.to_dict() or {}).get('v3_derived') else d.to_dict())
        for d in user.collection('conversations').stream()
    }
    lease = user.collection('conversation_v3_leases').document('builder').get().to_dict() or {}
    live = {
        cid: d
        for cid, d in docs.items()
        if d.get('v3_derived') and not d.get('deleted') and not d.get('sync_merged_into')
    }
    owners = Counter()
    for d in live.values():
        for s in d.get('transcript_segments') or []:
            if isinstance(s, dict):
                owners[s.get('id')] += 1
    segments = [s['id'] for rid in recordings for s in docs[rid]['transcript_segments']]
    claims = {rid: [(c['conversation_id'], c['start'], c['end']) for c in docs[rid]['claims']] for rid in recordings}
    return docs, live, lease, owners, segments, claims


SIX_BATCHES = dict(heavy=1300, neighbours=16, per_neighbour=62)  # about 2,280 rows: more batches than measured (5)

SHAPES = {
    # measured closures: 1,994 rows / 17 recordings (most rows), 1,678 / 64 (most sources), ~1,150 / 20 (median)
    'rows_1992_sources_17': dict(heavy=1000, neighbours=16, per_neighbour=62),
    'rows_1708_sources_64': dict(heavy=700, neighbours=63, per_neighbour=16),
    'rows_1156_sources_20': dict(heavy=700, neighbours=19, per_neighbour=24),
}


def _report(shape, mode, label, numbers):
    line = json.dumps({'shape': shape, 'refinement': mode, 'pass': label, **numbers}, default=str)
    print(line)
    path = os.getenv('V3_CLOSURE_COST_REPORT')
    if path:
        with open(path, 'a') as handle:
            handle.write(line + '\n')


@pytest.mark.asyncio
@pytest.mark.parametrize('shape', list(SHAPES))
@pytest.mark.parametrize(
    'mode',
    [
        # Serving timing (backend-sync sets no silence or lock seconds: 300/300). The live planner offers
        # refinement only under custom timing, so refinement.candidate is never called.
        'serving_timing',
        # Custom timing (1800/3600 sit-down profile) and every fragment eligible. The outline makes one window
        # over the stretch (short topics fold, sit-downs join), so it covers more than 8 rows and nothing merges.
        'custom_timing_one_window',
        # Custom timing with windows of exactly 4 eligible fragments (each topic over the 150-word Home minimum,
        # with its own people). Refinement runs before preserve_finished_windows and merges at most 8 donors.
        'custom_timing_four_line_windows',
    ],
)
async def test_heavy_locked_closure_commits_and_keeps_custody(owner, monkeypatch, shape, mode):
    if mode != 'serving_timing' and shape != 'rows_1992_sources_17':
        pytest.skip('refinement variants run on the largest closure only')
    client, user = owner
    if mode != 'serving_timing':
        monkeypatch.setenv('CONVERSATIONS_V3_SILENCE_GAP_SECONDS', '1800')
        monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    every = 4 if mode == 'custom_timing_four_line_windows' else 0
    eligible = 'long' if every else mode != 'serving_timing'
    recordings = ['heavy', *(f'n{k:02d}' for k in range(SHAPES[shape]['neighbours']))]
    rows, sources = seed(user, tail=3, eligible=eligible, **SHAPES[shape])
    docs, _, _, _, _, claims_before = custody(user, recordings=recordings)
    bounds = {cid: (d['started_at'], d['finished_at']) for cid, d in docs.items() if d.get('v3_derived')}

    first = await one_pass(client, user, outline_every=every)
    _report(shape, mode, 'first', {'closure_rows': rows, 'closure_sources': sources, **first})
    assert first['result'] == 'committed'
    docs, live, lease, owners, segments, claims = custody(user, recordings=recordings)
    assert not lease.get('v3_blocked_reason') and not lease.get('v3_blocked_count')
    assert all(not docs[rid].get('v3_pending') for rid in recordings)
    # Every recording segment is owned by exactly one live derived row (no double or missing ownership).
    assert {sid: owners[sid] for sid in segments if owners[sid] != 1} == {}
    merged = sorted(cid for cid, d in docs.items() if d.get('sync_merged_into'))
    survivors = {docs[cid]['sync_merged_into'] for cid in merged}
    assert first['refinement_offered'] is (mode != 'serving_timing')
    if mode == 'custom_timing_four_line_windows':
        # Refinement runs before preserve_finished_windows: exactly one bounded merge (2-8 donors) per pass.
        assert 2 <= len(merged) <= 8 and first['refinement_donors'] == len(merged)
        assert len(survivors) == 1 and next(iter(survivors)) in live
    else:
        assert merged == []
    for rid in recordings:
        before = {c for c in claims_before[rid] if c[0] not in merged}
        after = set(claims[rid])
        # Published ownership: every surviving fragment keeps its claims.
        assert before <= after, rid
    # ...and its boundaries (a refinement survivor keeps its id and covers its donors).
    kept = {cid: b for cid, b in bounds.items() if cid not in merged and cid not in survivors}
    assert {cid: b for cid, b in kept.items() if (live[cid]['started_at'], live[cid]['finished_at']) != b} == {}
    tail_owners = {cid for cid, *_ in claims['heavy']} - {c[0] for c in claims_before['heavy']}
    assert tail_owners and all(live[cid]['v3_recording_ids'] == ['heavy'] for cid in tail_owners)

    append_tail(user, 3)
    steady = await one_pass(client, user, outline_every=every)
    _report(shape, mode, 'steady', {'closure_rows': rows, 'closure_sources': sources, **steady})
    assert steady['result'] == 'committed'
    docs, live, lease, owners, segments, _ = custody(user, recordings=recordings)
    assert all(not docs[rid].get('v3_pending') for rid in recordings)
    assert {sid: owners[sid] for sid in segments if owners[sid] != 1} == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('switch', ['unlisted', 'zero_allowance'])
async def test_kill_switch_keeps_the_heavy_owner_parked(owner, monkeypatch, switch):
    client, user = owner
    if switch == 'unlisted':
        monkeypatch.setenv('CONVERSATIONS_V3_LOCKED_CLOSURE_OWNERS', '0123456789ab')
    else:
        monkeypatch.setattr(store, 'LOCKED_DERIVED_ALLOWANCE', 0)
    seed(user, tail=3, eligible=False, **SHAPES['rows_1156_sources_20'])
    blocked = await one_pass(client, user, outline_every=0)
    _report('rows_1156_sources_20', 'serving_timing', f'kill_switch_{switch}', blocked)
    assert blocked['result'] == 'blocked'
    lease = user.collection('conversation_v3_leases').document('builder').get().to_dict()
    assert lease['v3_blocked_reason'] == 'v3_derived_budget'
    assert user.collection('conversations').document('heavy').get().to_dict()['v3_pending'] is True


class _Clock(datetime):
    """The commit's clock: a fixed base (taken when the commit starts) plus an offset the fixture advances after
    every projection batch. Real elapsed time is ignored, so a slow read or a contention retry cannot move it."""

    base = datetime.now(timezone.utc)
    offset = timedelta(0)

    @classmethod
    def now(cls, tz=None):
        return (cls.base + cls.offset).astimezone(tz) if tz else (cls.base + cls.offset).replace(tzinfo=None)


@pytest.mark.asyncio
@pytest.mark.parametrize('renewed', [True, False], ids=['renewed_per_batch', 'control_without_renewal'])
async def test_a_commit_with_more_batches_than_measured_outlives_its_lease_by_renewing(owner, monkeypatch, renewed):
    """A 6-batch commit takes longer than the lease. Per-batch renewal keeps it, and without renewal the lease is lost.

    The lease and commit clocks start at a fixed base when the commit starts (right after the caller's renewal,
    which set the lease to its real start + 240 s) and advance 200 s after every projection batch. Without renewal,
    the third batch is at base + 400 s and must see the lease as expired. Real elapsed time is ignored, so a slow
    host or a contention retry cannot change the outcome.
    """
    client, user = owner
    rows, sources = seed(user, tail=3, eligible=False, **SIX_BATCHES)
    real_commit, real_renew = store.commit_projection, leases.renew
    _Clock.offset = timedelta(0)

    def advance():
        _Clock.offset += timedelta(seconds=200)

    def clocked_commit(uid, token, *args, **kwargs):
        _Clock.base = datetime.now(timezone.utc)
        monkeypatch.setattr(store, 'datetime', _Clock)
        monkeypatch.setattr(leases, 'datetime', _Clock)
        if not renewed:
            monkeypatch.setattr(leases, 'renew', lambda *a, **k: None)
        try:
            return real_commit(uid, token, *args, **kwargs)
        finally:
            monkeypatch.setattr(store, 'datetime', datetime)
            monkeypatch.setattr(leases, 'datetime', datetime)
            monkeypatch.setattr(leases, 'renew', real_renew)

    monkeypatch.setattr(store, 'commit_projection', clocked_commit)
    result = await one_pass(client, user, outline_every=0, after_batch=advance)
    label = f'six_batches_{"renewed" if renewed else "control"}'
    _report(
        'rows_2276_sources_17', 'serving_timing', label, {'closure_rows': rows, 'closure_sources': sources, **result}
    )
    heavy = user.collection('conversations').document('heavy').get().to_dict()
    if renewed:
        assert result['result'] == 'committed'
        assert result['transactions_commit'] == 6 + 5  # six batches plus a renewal before each later one
        assert heavy['v3_pending'] is False
    else:
        assert result['result'] == 'raced'  # lease_lost after a two-batch prefix; pending stays owed
        assert result['transactions_commit'] == 2
        assert heavy['v3_pending'] is True


@pytest.mark.asyncio
async def test_a_closure_past_the_batch_cap_parks_without_writing(owner, monkeypatch):
    client, user = owner
    monkeypatch.setattr(store, 'LOCKED_MAX_BATCHES', 5)
    rows, sources = seed(user, tail=3, eligible=False, **SIX_BATCHES)
    result = await one_pass(client, user, outline_every=0)
    _report(
        'rows_2276_sources_17',
        'serving_timing',
        'batch_cap_5',
        {'closure_rows': rows, 'closure_sources': sources, **result},
    )
    assert result['result'] == 'blocked' and result['writes_conversations'] == 0 and result['transactions_commit'] == 0
    # It parked at the commit's batch cap, after a full load within the allowance and the outline step, not at
    # load time (a load overflow would shrink to 8, then 1, seeds and never plan or reach the commit).
    assert result['reads_load'] > 3000 and result['outline_calls'] >= 1 and result['reads_commit'] == 0
    assert result['commit_calls'] == 1
    lease = user.collection('conversation_v3_leases').document('builder').get().to_dict()
    assert lease['v3_blocked_reason'] == 'v3_derived_budget'
    assert user.collection('conversations').document('heavy').get().to_dict()['v3_pending'] is True
