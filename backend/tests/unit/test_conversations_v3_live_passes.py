"""Live builder passes: one sit-down stays one card while its speech arrives (pass after pass).

Each test runs the real ``service.reconcile`` and ``commit_projection`` against the strict Firestore
fixture, feeding every pass the rows and claims the previous pass committed. The source loader is
replaced by a full read of the fixture (recordings plus every derived row), so these pin the timing,
cap and preservation paths, not the loader's query plan.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from database import conversations_v3 as store
from utils.conversations.v3 import policy, service
from utils.home_feed.projection import reveal_display
from tests.unit.test_conversations_v3_claim_growth import strict, owners_import, path, UID  # noqa: F401

T0 = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)
LOCK_ENV = ('CONVERSATIONS_V3_SILENCE_GAP_SECONDS', 'CONVERSATIONS_V3_LOCK_SECONDS')


@pytest.fixture(autouse=True)
def disable_live_title_unless_test_opts_in(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_TITLE', 'off')


def speech(count, step=30.0):
    return [
        {'id': f's{i}', 'text': 'word ' * 12, 'start': i * step, 'end': i * step + step - 2, 'is_user': True}
        for i in range(count)
    ]


def put_recording(strict, segments, *, status, landed):
    current = strict.rows.get(path('r'), {})
    strict.rows[path('r')] = {
        **current,
        'id': 'r',
        'recording': True,
        'source': 'omi',
        'status': status,
        'started_at': T0,
        'finished_at': T0 + timedelta(seconds=segments[-1]['end']),
        'data_protection_level': 'standard',
        'transcript_segments': segments,
        'claims': current.get('claims', []),
        'v3_pending': True,
        'v3_pending_since': current.get('v3_pending_since') or landed,
        'v3_speech_landed_at': landed,  # what the speech write stamps
    }


async def reconcile_at(strict, monkeypatch, now, outline_entries=None, derive_run=None):
    for row in strict.rows.values():
        row['_test_revision'] = 1

    def load(uid, **kwargs):
        recordings = {
            p[3]: {**deepcopy(r), '_v3_revision': 1}
            for p, r in strict.rows.items()
            if len(p) == 4 and p[2] == 'conversations' and r.get('recording')
        }
        existing = {
            p[3]: {**deepcopy(r), '_v3_revision': 1}
            for p, r in strict.rows.items()
            # Tombstones load too: store.load reads every row a recording's claims name.
            if len(p) == 4 and p[2] == 'conversations' and r.get('v3_derived')
        }
        return recordings, existing, []

    def load_derive(uid, **kwargs):
        recordings, existing, cache = load(uid)
        recordings = {
            k: {**r, '_v3_derive': True, '_v3_backfill_run': derive_run, '_v3_backfill_prior': {}}
            for k, r in recordings.items()
        }
        return recordings, {k: r for k, r in existing.items() if r.get('v3_backfill_run') == derive_run}, cache

    async def blocking(pool, fn, *args, **kwargs):
        if fn is store.load:
            return load(*args, **kwargs)
        if fn is store.load_derive:
            return load_derive(*args, **kwargs)
        if fn is store.adoptable:
            return {}
        return fn(*args, **kwargs)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    def outline(uid, messages):
        entries = outline_entries or [
            {'first_line': 1, 'kind': 'conversation', 'title': 'Talk', 'line': '', 'people': [], 'sections': []}
        ]
        return json.dumps({'conversations': entries})

    async def nothing(*args, **kwargs):
        return None

    monkeypatch.setattr(service, 'datetime', Clock)
    monkeypatch.setattr(store, 'datetime', Clock)
    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', nothing)
    monkeypatch.setattr(service, 'has_pending', lambda *args, **kwargs: False)
    monkeypatch.setattr(service, 'enqueue', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.models, 'outline', outline)
    monkeypatch.setattr(service.visibility, 'hydrate_recognition', lambda uid, recordings, windows: None)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *args: ({}, [], []))
    if derive_run:
        return await service.reconcile(
            UID, derive=True, since=T0 - timedelta(days=1), until=T0 + timedelta(days=1), run_id=derive_run
        )
    return await service.reconcile(UID)


def derived(strict):
    return sorted(
        (r for p, r in strict.rows.items() if len(p) == 4 and r.get('v3_derived') and not r.get('deleted')),
        key=lambda r: r['started_at'],
    )


def slivers(rows):
    return [r for r in rows if r['finished_at'] - r['started_at'] < timedelta(minutes=2)]


def timing(monkeypatch, gap, lock):
    monkeypatch.setenv(LOCK_ENV[0], str(gap))
    monkeypatch.setenv(LOCK_ENV[1], str(lock))


@pytest.mark.asyncio
async def test_live_recording_inside_the_lock_delay_keeps_one_open_card(strict, monkeypatch):
    # (a) A ten-minute recording arrives a minute at a time; its latest speech stays inside the lock delay.
    timing(monkeypatch, 900, 900)
    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_TITLE', 'off')
    calls = []
    monkeypatch.setattr(service.models, 'live_title', lambda *args: calls.append(args))
    ids = set()
    for minute in range(1, 11):
        segments = speech(minute * 2)
        landed = T0 + timedelta(seconds=segments[-1]['end'] + 30)
        put_recording(strict, segments, status='in_progress', landed=landed)
        assert await reconcile_at(strict, monkeypatch, landed) == 'committed'
        rows = derived(strict)
        assert len(rows) == 1 and planner_open(rows[0]), [(r['started_at'], r['status']) for r in rows]
        ids.add(rows[0]['id'])
    assert len(ids) == 1
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('gap', [300, 900])
@pytest.mark.parametrize('provider_fails', [False, True])
async def test_live_title_is_attempted_once_and_final_outline_wins(strict, monkeypatch, gap, provider_fails):
    timing(monkeypatch, gap, gap)
    monkeypatch.delenv('CONVERSATIONS_V3_LIVE_TITLE', raising=False)
    calls = []

    def live_title(uid, segments):
        calls.append(uid)
        assert derived(strict)[0]['status'] == 'in_progress'
        if provider_fails:
            raise TimeoutError()
        return 'Planning the fall release'

    monkeypatch.setattr(service.models, 'live_title', live_title)
    for count in (6, 7, 8):
        segments = speech(count)
        now = T0 + timedelta(seconds=segments[-1]['end'] + 1)
        put_recording(strict, segments, status='in_progress', landed=now)
        assert await reconcile_at(strict, monkeypatch, now) == 'committed'
        (row,) = derived(strict)
        assert row['status'] == 'in_progress' and not row['title_locked']
        assert len(calls) == int(count >= 7)
        expected = '' if count == 6 or provider_fails else 'Planning the fall release'
        assert row['structured']['title'] == expected
        if count == 7 and not provider_fails:
            assert reveal_display(UID, row['home_display'])['title'] == expected

    put_recording(strict, segments, status='completed', landed=now)
    assert await reconcile_at(strict, monkeypatch, now + timedelta(seconds=gap + 1)) == 'committed'
    (row,) = derived(strict)
    assert not planner_open(row)
    assert row['structured']['title'] == 'Talk'
    assert calls == [UID]


@pytest.mark.parametrize(
    'exclusion',
    [
        {'data_protection_level': 'private'},
        {'data_protection_level': 'e2ee'},
        {'is_locked': True},
        {'backfilled': True},
        {'title_locked': True},
        {'home_content_invalidated': True},
        {'home_hidden': True},
    ],
)
def test_live_title_excludes_protected_or_hidden_rows(exclusion):
    row = {'v3_derived': True, 'status': 'in_progress', 'tile_state': 'live'}
    assert policy.live_title_candidate(row)
    assert not policy.live_title_candidate({**row, **exclusion})


@pytest.mark.parametrize('protection', ['private', 'e2ee'])
def test_live_title_claim_rechecks_current_privacy(strict, protection):
    cid = 'protected'
    row = {
        'v3_derived': True,
        'status': 'in_progress',
        'tile_state': 'live',
        'sync_content_revision': 1,
        'data_protection_level': protection,
    }
    strict.rows[path(cid)] = row
    token = store.leases.acquire(UID, 'builder', firestore_client=strict)
    assert token
    assert not store.write_live_title_preview(UID, token, cid, 1, firestore_client=strict)
    assert policy.LIVE_TITLE_STATE not in strict.rows[path(cid)]


@pytest.mark.asyncio
async def test_live_title_skips_legacy_row_without_content_revision(monkeypatch):
    def unexpected_store_call(*args):
        pytest.fail('A row without a content revision must not claim a title attempt')

    monkeypatch.setattr(service, 'run_blocking', unexpected_store_call)
    await service._maybe_publish_live_title(UID, 'builder', 'token', {'id': 'legacy', 'transcript_segments': speech(8)})


def test_live_title_model_caps_multibyte_input_and_output(monkeypatch):
    class Model:
        def bind(self, **options):
            assert options == {'reasoning_effort': 'none', 'max_completion_tokens': 32}
            return self

        def invoke(self, messages):
            prompt, transcript = (message.encode('utf-8') for _, message in messages)
            assert len(prompt) + len(transcript) <= 1024 - 64
            assert transcript.decode('utf-8').startswith('秋')
            return SimpleNamespace(content=' 秋のリリース計画 ', response_metadata={'finish_reason': 'stop'})

    def gateway(lane, *, options, feature):
        assert lane == 'omi:auto:conversation-v3-live-title'
        assert options['max_retries'] == 0
        assert feature == 'conversation_v3_live_title'
        return Model()

    monkeypatch.setattr(service.models, 'get_or_create_omi_gateway_llm', gateway)
    assert service.models.live_title(UID, [{'text': '秋' * 1500}]) == '秋のリリース計画'


@pytest.mark.asyncio
async def test_live_title_does_not_overwrite_a_concurrent_user_rename(strict, monkeypatch):
    def live_title(uid, segments):
        (row,) = derived(strict)
        row['user_title'] = row['structured']['title'] = 'My own title'
        return 'Planning the fall release'

    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_TITLE', 'on')
    monkeypatch.setattr(service.models, 'live_title', live_title)
    segments = speech(7)
    now = T0 + timedelta(seconds=segments[-1]['end'] + 1)
    put_recording(strict, segments, status='in_progress', landed=now)
    assert await reconcile_at(strict, monkeypatch, now) == 'committed'
    (row,) = derived(strict)
    assert row['structured']['title'] == 'My own title'


def planner_open(row):
    from utils.conversations.v3 import planner

    return planner.is_unlocked(row)


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(900, 900), (300, 300)])
async def test_offline_batches_of_old_speech_do_not_lock_on_arrival(strict, monkeypatch, gap, lock):
    # (b) Offline sync lands the same ten minutes in three batches two hours later: every batch's speech
    # is already older than the lock delay. Custom timing counts the lock from landing, so the batches
    # build one card. Default timing keeps today's behaviour (asserted below, documented in the PR).
    timing(monkeypatch, gap, lock)
    arrival = T0 + timedelta(hours=2)
    for batch, count in enumerate((7, 14, 20)):
        landed = arrival + timedelta(minutes=2 * batch)
        put_recording(strict, speech(count), status='in_progress' if count < 20 else 'completed', landed=landed)
        assert await reconcile_at(strict, monkeypatch, landed) == 'committed'
    rows = derived(strict)
    if (gap, lock) == (300, 300):
        assert len(rows) >= 1  # unchanged default: each aged batch may lock on arrival
        return
    assert len(rows) == 1 and not slivers(rows), [(r['started_at'], r['finished_at'], r['status']) for r in rows]
    # Once the lock delay passes after the last landing, the card locks whole.
    assert await reconcile_at(strict, monkeypatch, arrival + timedelta(minutes=4, seconds=lock + 60)) == 'committed'
    rows = derived(strict)
    assert len(rows) == 1 and not planner_open(rows[0])


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 900)])
async def test_cap_cut_survives_the_first_paid_outline(strict, monkeypatch, gap, lock):
    # (c) Two and a half hours of continuous talk crosses the two-hour cap under the initial one-entry
    # outline; the first paid outline then adds a section before the committed cut. The locked prefix
    # keeps its id and boundary, and no sliver card appears.
    timing(monkeypatch, gap, lock)
    segments = speech(300)  # 30 s apart: 2.5 h
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='in_progress', landed=end + timedelta(seconds=30))
    assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=30)) == 'committed'
    first = derived(strict)
    assert len(first) == 2
    prefix = first[0]
    assert not planner_open(prefix)
    paid = [
        {
            'first_line': 1,
            'kind': 'conversation',
            'title': 'Long talk',
            'line': '',
            'people': [],
            'sections': [{'first_line': 190, 'title': 'Around ninety-five minutes'}],
        }
    ]
    put_recording(strict, segments, status='completed', landed=end + timedelta(seconds=30))
    later = end + timedelta(seconds=max(gap, lock) + 120)
    assert await reconcile_at(strict, monkeypatch, later, outline_entries=paid) == 'committed'
    rows = derived(strict)
    kept = next(r for r in rows if r['id'] == prefix['id'])
    assert (kept['started_at'], kept['finished_at']) == (prefix['started_at'], prefix['finished_at'])
    # Exactly the locked prefix and one card for the rest: nothing stranded between old and new cuts.
    assert len(rows) == 2 and not slivers(rows), [(r['started_at'], r['finished_at']) for r in rows]


@pytest.mark.asyncio
@pytest.mark.parametrize('gap', [300, 900])
async def test_cap_cut_ignores_a_section_a_later_outline_drops(strict, monkeypatch, gap):
    # A paid outline with a section at 95 minutes is in place when the stretch first crosses the cap;
    # a later outline (more speech) drops that section. The cut must not have followed the section, or
    # the lines between it and the later cut are stranded as their own card.
    timing(monkeypatch, gap, 3600)
    sectioned = [
        {
            'first_line': 1,
            'kind': 'conversation',
            'title': 'Long talk',
            'line': '',
            'people': [],
            'sections': [{'first_line': 190, 'title': 'Around ninety-five minutes'}],
        }
    ]
    segments = speech(300)
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='in_progress', landed=end + timedelta(seconds=30))
    assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=gap + 30), sectioned) == 'committed'
    first = derived(strict)
    assert len(first) == 2
    prefix = first[0]
    more = speech(330)
    later_end = T0 + timedelta(seconds=more[-1]['end'])
    put_recording(strict, more, status='in_progress', landed=later_end + timedelta(seconds=30))
    assert await reconcile_at(strict, monkeypatch, later_end + timedelta(seconds=gap + 30)) == 'committed'
    rows = derived(strict)
    kept = next(r for r in rows if r['id'] == prefix['id'])
    assert (kept['started_at'], kept['finished_at']) == (prefix['started_at'], prefix['finished_at'])
    assert len(rows) == 2 and not slivers(rows), [(r['started_at'], r['finished_at']) for r in rows]


def test_mark_pending_leaves_the_landing_time_to_the_speech_write(strict):
    # The re-arm can run after a reconcile has already seen the speech, so it must not be the stamp.
    strict.rows[path('r')] = {'id': 'r', 'recording': True, 'v3_pending_since': T0}
    assert store.mark_pending(UID, 'r')
    row = strict.rows[path('r')]
    assert 'v3_speech_landed_at' not in row and row['v3_pending_since'] == T0 and row['v3_pending']


@pytest.mark.asyncio
async def test_old_speech_written_live_does_not_lock_before_the_rearm(strict, monkeypatch):
    # Offline speech two hours old lands through the transcript write. A reconcile runs after that
    # transaction commits and before changed() re-arms the row: the landing time must already be there.
    from database import conversations as db
    from utils.conversations.v3 import triggers

    timing(monkeypatch, 900, 900)
    first = speech(7)
    arrival = T0 + timedelta(hours=2)
    put_recording(strict, first, status='in_progress', landed=arrival)
    assert await reconcile_at(strict, monkeypatch, arrival) == 'committed'

    landed = arrival + timedelta(minutes=20)  # past the lock delay from the first batch

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return landed

    rearmed = []
    monkeypatch.setattr(db, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(db, 'datetime', Clock)
    monkeypatch.setattr(triggers, 'changed', lambda uid, cid: rearmed.append(cid))
    more = speech(14)
    assert db.update_conversation_segments(UID, 'r', more, finished_at=T0 + timedelta(seconds=more[-1]['end']))
    row = strict.rows[path('r')]
    assert row['v3_speech_landed_at'] == landed  # committed with the speech, before the re-arm
    assert rearmed == ['r']
    row['transcript_segments'] = db._decode_transcript_segments_strict(
        UID, row['transcript_segments'], row.get('transcript_segments_compressed', False)
    )
    row['transcript_segments_compressed'] = False

    assert await reconcile_at(strict, monkeypatch, landed + timedelta(seconds=30)) == 'committed'
    rows = derived(strict)
    assert len(rows) == 1 and planner_open(rows[0]), [(r['started_at'], r['status']) for r in rows]


def test_derive_ignores_the_landing_clock(monkeypatch):
    # Backfill derive plans at default timing whatever the live setting, so it never settles on landing.
    from config import conversations_v3 as cfg

    timing(monkeypatch, 900, 900)
    assert cfg.boundary_seconds(cohesion=True) == (900, 900)
    assert cfg.boundary_seconds(cohesion=False) == (cfg.DEFAULT_BOUNDARY_SECONDS,) * 2
    source = __import__('inspect').getsource(service.reconcile)
    assert 'boundary_seconds(cohesion=cohesion and not derive)' in source


def ownership(rows):
    owners = {}
    for row in rows:
        for segment in row.get('transcript_segments') or []:
            owners.setdefault(segment['id'], []).append(row['id'])
    return owners


def claim_spans(strict):
    return sorted((c['start'], c['end'], c['conversation_id']) for c in strict.rows[path('r')].get('claims') or [])


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 900)])
async def test_overlapping_turns_at_the_cap_keep_one_owner_across_passes(strict, monkeypatch, gap, lock):
    # Turns at [0, 119), [118, 121) and [118.5, 119) minutes: the cap puts the first in the prefix and
    # the other two in the tail, whose claim is clipped to [119, 121). A retry must not hand the short
    # turn to the prefix too (its window and claim contain it), and claims must never overlap.
    timing(monkeypatch, gap, lock)
    minute = 60.0
    segments = [
        {'id': 'a', 'text': 'word ' * 400, 'start': 0.0, 'end': 119 * minute, 'is_user': True},
        {'id': 'b', 'text': 'word ' * 40, 'start': 118 * minute, 'end': 121 * minute, 'is_user': True},
        {'id': 'c', 'text': 'word ' * 5, 'start': 118.5 * minute, 'end': 119 * minute, 'is_user': True},
    ]
    end = T0 + timedelta(minutes=121)
    put_recording(strict, segments, status='in_progress', landed=end)
    seen = []
    for now in (
        end + timedelta(seconds=30),
        end + timedelta(seconds=60),
        end + timedelta(seconds=max(gap, lock) + 120),
    ):
        if len(seen) == 2:
            put_recording(strict, segments, status='completed', landed=end)
        assert await reconcile_at(strict, monkeypatch, now) == 'committed'
        rows = derived(strict)
        owners = ownership(rows)
        assert all(len(ids) == 1 for ids in owners.values()), owners
        spans = claim_spans(strict)
        assert all(left[1] <= right[0] for left, right in zip(spans, spans[1:])), spans
        seen.append({sid: ids[0] for sid, ids in owners.items()})
    assert seen[0] == seen[1] == seen[2], seen
    assert seen[0]['a'] != seen[0]['b'] == seen[0]['c']


def main_capped(lines, sections, committed=()):
    # planner._capped before this change (main b301dc3): cut at the section nearest the middle.
    from utils.conversations.v3.planner import CAP

    end = max(line['end'] for line in lines)
    if end - lines[0]['start'] <= CAP:
        return [lines]
    middle = lines[0]['start'] + (end - lines[0]['start']) / 2
    candidates = [i for i in sections if 0 < i < len(lines)] or list(range(1, len(lines)))
    cut = min(candidates, key=lambda i: abs((lines[i]['start'] - middle).total_seconds()))
    return main_capped(lines[:cut], ()) + main_capped(lines[cut:], ())


def locked_state(strict, rows):
    claims = strict.rows[path('r')].get('claims') or []
    return {
        r['id']: (
            r['started_at'],
            r['finished_at'],
            sorted(s['id'] for s in r.get('transcript_segments') or []),
            sorted((c['start'], c['end']) for c in claims if c['conversation_id'] == r['id']),
        )
        for r in rows
        if not planner_open(r)
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 900)])
async def test_rows_cut_by_the_old_midpoint_cap_keep_their_cuts_after_upgrade(strict, monkeypatch, gap, lock):
    # Upgrade: main cut a 2.5 h live stretch at its middle and locked the prefix. The new code then
    # runs on the same owner as more speech lands. Locked rows keep boundaries, segments and claims;
    # only the live edge changes, and no segment or audio gets two owners.
    from utils.conversations.v3 import planner

    timing(monkeypatch, gap, lock)
    segments = speech(300)
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='in_progress', landed=end + timedelta(seconds=30))
    with monkeypatch.context() as old:
        old.setattr(planner, '_capped', main_capped)
        assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=30)) == 'committed'
    before = locked_state(strict, derived(strict))
    assert len(before) == 1
    (prefix,) = before.values()
    assert timedelta(minutes=70) < prefix[1] - prefix[0] < timedelta(minutes=80)  # the old midpoint cut

    for count in (330, 360):
        more = speech(count)
        later = T0 + timedelta(seconds=more[-1]['end'])
        put_recording(strict, more, status='in_progress', landed=later + timedelta(seconds=30))
        assert await reconcile_at(strict, monkeypatch, later + timedelta(seconds=30)) == 'committed'
        rows = derived(strict)
        after = locked_state(strict, rows)
        assert {k: after[k] for k in before} == before
        owners = ownership(rows)
        assert sorted(owners) == sorted(s['id'] for s in more)
        assert all(len(ids) == 1 for ids in owners.values()), owners
        spans = claim_spans(strict)
        assert all(left[1] <= right[0] for left, right in zip(spans, spans[1:])), spans
        # The cap counts from the committed cut: the old tail (under two hours) stays one open card.
        assert len(rows) == 2 and planner_open(rows[1]), [(r['started_at'], r['finished_at']) for r in rows]


@pytest.mark.asyncio
async def test_resuming_a_backfill_run_cut_by_the_old_cap_keeps_its_rows(strict, monkeypatch):
    # A backfill run derived by main (middle cut) is resumed by the new code (a redelivered step, or
    # the operator's resume after a block). The committed rows keep boundaries, segments and claims.
    from utils.conversations.v3 import planner

    segments = speech(300)
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='completed', landed=end)
    later = end + timedelta(hours=1)
    with monkeypatch.context() as old:
        old.setattr(planner, '_capped', main_capped)
        assert await reconcile_at(strict, monkeypatch, later, derive_run='run-1') == 'committed'
    rows = derived(strict)
    before = locked_state(strict, rows)
    assert len(before) == 2 and all(r.get('backfilled') for r in rows)
    assert await reconcile_at(strict, monkeypatch, later + timedelta(minutes=5), derive_run='run-1') == 'committed'
    rows = derived(strict)
    assert locked_state(strict, rows) == before
    assert all(len(ids) == 1 for ids in ownership(rows).values())
    spans = claim_spans(strict)
    assert all(left[1] <= right[0] for left, right in zip(spans, spans[1:])), spans


def overlapping_speech(count, step=30.0):
    # Every turn runs 10 s into the next one, so any cut between turns is straddled.
    return [
        {'id': f's{i}', 'text': 'word ' * 12, 'start': i * step, 'end': i * step + step + 10, 'is_user': True}
        for i in range(count)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 900)])
async def test_an_old_cut_a_turn_straddles_still_holds_after_upgrade(strict, monkeypatch, gap, lock):
    # main cut at the middle; the open tail's first turn starts before the locked prefix's last turn
    # ends. The new code recognises the cut by what the prefix holds, not by a gap between turns, so
    # it never cuts into the old open tail (#25829 review).
    from utils.conversations.v3 import planner

    timing(monkeypatch, gap, lock)
    segments = overlapping_speech(300)
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='in_progress', landed=end + timedelta(seconds=30))
    with monkeypatch.context() as old:
        old.setattr(planner, '_capped', main_capped)
        assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=30)) == 'committed'
    rows = derived(strict)
    before = locked_state(strict, rows)
    assert len(before) == 1 and len(rows) == 2
    tail = next(r for r in rows if planner_open(r))
    assert tail['started_at'] < next(iter(before.values()))[1]  # the straddle
    for count in (330, 360):
        more = overlapping_speech(count)
        later = T0 + timedelta(seconds=more[-1]['end'])
        put_recording(strict, more, status='in_progress', landed=later + timedelta(seconds=30))
        assert await reconcile_at(strict, monkeypatch, later + timedelta(seconds=30)) == 'committed'
        rows = derived(strict)
        after = locked_state(strict, rows)
        assert {k: after[k] for k in before} == before
        assert len(rows) == 2 and planner_open(rows[1]), [(r['started_at'], r['finished_at']) for r in rows]
        assert rows[1]['id'] == tail['id']
        assert all(len(ids) == 1 for ids in ownership(rows).values())


def test_a_full_write_that_changes_no_speech_keeps_the_landing_time(strict, monkeypatch):
    # A retried full-payload write must not refresh the landing time and extend the lock.
    from database import conversations as db
    from utils.conversations.v3 import triggers

    clock = {'now': T0 + timedelta(hours=2)}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock['now']

    monkeypatch.setattr(db, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(db, 'datetime', Clock)
    monkeypatch.setattr(triggers, 'changed', lambda uid, cid: None)
    put_recording(strict, speech(3), status='in_progress', landed=T0)
    first = speech(5)
    assert db.update_conversation_segments(UID, 'r', deepcopy(first))
    stamped = strict.rows[path('r')]['v3_speech_landed_at']
    assert stamped == clock['now']
    clock['now'] += timedelta(minutes=10)
    assert db.update_conversation_segments(UID, 'r', deepcopy(first))  # same speech again
    assert strict.rows[path('r')]['v3_speech_landed_at'] == stamped
    first[-1]['text'] += 'more '
    assert db.update_conversation_segments(UID, 'r', deepcopy(first))
    assert strict.rows[path('r')]['v3_speech_landed_at'] == clock['now']


def boundaries_and_claims(strict, rows):
    claims = strict.rows[path('r')].get('claims') or []
    return {
        r['id']: (
            r['started_at'],
            r['finished_at'],
            sorted((c['start'], c['end']) for c in claims if c['conversation_id'] == r['id']),
        )
        for r in rows
        if not planner_open(r)
    }


def revised(segments, *indices):
    out = deepcopy(segments)
    for i in indices:
        out[i] = {**out[i], 'id': out[i]['id'] + '-rev', 'text': 'revised ' * 12}
    return out


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 900)])
async def test_a_revised_held_turn_does_not_move_a_committed_cut(strict, monkeypatch, gap, lock):
    # A transcript revision gives a held turn a new id but keeps its audio inside the locked row's
    # claim. The cut must stay: revising the first held turn and an interior one keeps the locked
    # boundary, its claims and the open card's id (#25829 review).
    from utils.conversations.v3 import planner

    timing(monkeypatch, gap, lock)
    segments = speech(300)
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='in_progress', landed=end + timedelta(seconds=30))
    with monkeypatch.context() as old:
        old.setattr(planner, '_capped', main_capped)
        assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=30)) == 'committed'
    rows = derived(strict)
    before = boundaries_and_claims(strict, rows)
    assert len(before) == 1 and len(rows) == 2
    tail = next(r for r in rows if planner_open(r))
    for count, indices in ((330, (0,)), (360, (0, 10))):
        more = revised(speech(count), *indices)
        later = T0 + timedelta(seconds=more[-1]['end'])
        put_recording(strict, more, status='in_progress', landed=later + timedelta(seconds=30))
        assert await reconcile_at(strict, monkeypatch, later + timedelta(seconds=30)) == 'committed'
        rows = derived(strict)
        assert boundaries_and_claims(strict, rows) == before
        assert len(rows) == 2 and rows[1]['id'] == tail['id'] and planner_open(rows[1]), [
            (r['started_at'], r['finished_at'], planner_open(r)) for r in rows
        ]
        owners = ownership(rows)
        assert all(len(ids) == 1 for ids in owners.values()), owners
        assert {owners[f's{i}-rev'][0] for i in indices} == set(before)
        spans = claim_spans(strict)
        assert all(left[1] <= right[0] for left, right in zip(spans, spans[1:])), spans


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 900)])
async def test_an_open_tail_turn_inside_the_prefix_claim_stays_in_the_open_tail(strict, monkeypatch, gap, lock):
    # main cut [0, 119) min | [118.5, 119) + [118.7, 121) + more. The short turn is published in the open
    # tail, while its audio lies wholly inside the locked prefix's claim. The cap and the projection
    # use one owner rule (exact hold first, any row), so the cap does not finish that turn with the
    # prefix and leave a finished fragment beside the open tail (#25829 review).
    from utils.conversations.v3 import planner

    timing(monkeypatch, gap, lock)
    minute = 60.0

    def turns(extra):
        return [
            {'id': 'a', 'text': 'word ' * 400, 'start': 0.0, 'end': 119 * minute, 'is_user': True},
            {'id': 't', 'text': 'word ' * 5, 'start': 118.5 * minute, 'end': 119 * minute, 'is_user': True},
            {'id': 'b', 'text': 'word ' * 40, 'start': 118.7 * minute, 'end': 121 * minute, 'is_user': True},
            *(
                {
                    'id': f'd{i}',
                    'text': 'word ' * 12,
                    'start': (121 + i) * minute,
                    'end': (121.9 + i) * minute,
                    'is_user': True,
                }
                for i in range(extra)
            ),
        ]

    segments = turns(2)
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='in_progress', landed=end + timedelta(seconds=30))
    with monkeypatch.context() as old:
        old.setattr(planner, '_capped', main_capped)
        assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=30)) == 'committed'
    rows = derived(strict)
    before = boundaries_and_claims(strict, rows)
    tail = next(r for r in rows if planner_open(r))
    assert len(rows) == 2 and ownership(rows)['t'] == [tail['id']]
    prefix_claims = next(iter(before.values()))[2]
    assert any(a <= T0 + timedelta(minutes=118.5) and T0 + timedelta(minutes=119) <= b for a, b in prefix_claims)
    for extra in (4, 8):
        more = turns(extra)
        later = T0 + timedelta(seconds=more[-1]['end'])
        put_recording(strict, more, status='in_progress', landed=later + timedelta(seconds=30))
        assert await reconcile_at(strict, monkeypatch, later + timedelta(seconds=30)) == 'committed'
        rows = derived(strict)
        assert boundaries_and_claims(strict, rows) == before
        assert len(rows) == 2 and rows[1]['id'] == tail['id'] and planner_open(rows[1]), [
            (r['started_at'], r['finished_at'], planner_open(r)) for r in rows
        ]
        owners = ownership(rows)
        assert all(len(ids) == 1 for ids in owners.values()), owners
        assert owners['t'] == [tail['id']]


def tombstone(segments, first, last, claims):
    start = T0 + timedelta(seconds=segments[first]['start'])
    end = T0 + timedelta(seconds=segments[last]['end'])
    claims.append({'conversation_id': 'tomb', 'start': start, 'end': end})
    return {
        'id': 'tomb',
        'v3_derived': True,
        'deleted': True,
        'status': 'completed',
        'v3_recording_ids': ['r'],
        'started_at': start,
        'finished_at': end,
        'transcript_segments': [
            {**s, 'start': s['start'] - segments[first]['start'], 'end': s['end'] - segments[first]['start']}
            for s in segments[first : last + 1]
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 900)])
async def test_valid_speech_either_side_of_a_deleted_card_survives(strict, monkeypatch, gap, lock):
    # The owner deleted the middle card of one stretch; its tombstone keeps the claim. The deleted
    # speech stays isolated in the tombstone's window (skipped), and the valid turns either side are
    # built as live cards, not joined into one window that time-matches the tombstone and is dropped.
    timing(monkeypatch, gap, lock)
    segments = speech(30)
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='completed', landed=end)
    claims = []
    strict.rows[path('tomb')] = tombstone(segments, 10, 19, claims)
    strict.rows[path('r')]['claims'] = claims
    assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=max(gap, lock) + 60)) == 'committed'
    live = [r for r in derived(strict)]
    kept = {s['id'] for r in live for s in r.get('transcript_segments') or []}
    assert {f's{i}' for i in (*range(10), *range(20, 30))} <= kept, sorted(kept)
    assert not kept & {f's{i}' for i in range(10, 20)}
    assert strict.rows[path('tomb')]['deleted']


@pytest.mark.asyncio
async def test_one_ownership_index_per_plan(strict, monkeypatch):
    # The cap and both projections share one Ownership per plan (cost: one index, one rule).
    from utils.conversations.v3 import planner

    built = []
    real = planner.Ownership

    class Counting(real):
        def __init__(self, *args, **kwargs):
            built.append(1)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(planner, 'Ownership', Counting)
    timing(monkeypatch, 300, 300)
    segments = speech(300)
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='in_progress', landed=end)
    assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=30)) == 'committed'
    assert built == [1]
