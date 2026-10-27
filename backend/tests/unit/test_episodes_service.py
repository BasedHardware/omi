"""Episode orchestration over the strict Firestore fake: moments, boundaries, reconciliation, wrap-up."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import episodes as config
from database import episode_receipts
from database import episodes as episodes_db
from models.episode import Episode
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.episodes import service
from utils.episodes.service import Collaborators, MomentInput

UID = 'uid-episodes'
T0 = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)
    monkeypatch.setenv('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
    # These tests exercise a user whose app shows episodes (test_episodes_client_gate covers the marker).
    monkeypatch.setattr(service.client_gate, 'client_seen', lambda uid: True)
    service.client_gate.reset_for_tests()
    service.reset_for_tests()


def _consumed(store, conversation_id='c1', *, all_shards=True):
    return episode_receipts.get_consumed_ids(UID, conversation_id, all_shards=all_shards, firestore_client=store)


class FakeModel:
    """Returns scripted answers and records exactly what each call was shown."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, uid, messages):
        self.calls.append(messages)
        answer = self.answers.pop(0) if self.answers else {'bullets': ['x']}
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(content=json.dumps(answer), usage_metadata={'input_tokens': 400, 'output_tokens': 120})


def _collaborators(model, *, now, ask=None, saved=None, store=None):
    return Collaborators(
        invoke=model,
        ask=ask or (lambda *a, **k: None),
        tz_name='UTC',
        firestore_client=store,
        saved_tasks=lambda uid, cid: list((saved or {}).get(cid, [])),
        people_names=lambda uid, ids: {pid: 'Huong' for pid in ids},
        now=lambda: now,
    )


@pytest.fixture(autouse=True)
def _speaker_names(monkeypatch):
    monkeypatch.setattr(service, 'get_user_name', lambda *_a, **_kw: None)
    monkeypatch.setattr(service.incremental, 'get_user_name', lambda *_a, **_kw: None)


def test_new_episode_resets_the_bounded_voice_order():
    from dataclasses import replace

    store = StrictFirestore()
    model = FakeModel({'title': 'First'}, {'title': 'Next'})

    def moment(cid, speaker, minutes):
        return replace(
            _moment(cid, minutes=minutes),
            segments=[
                {'id': cid, 'text': LONG, 'speaker_id': speaker, 'is_user': False, 'start': 0, 'end': 30},
            ],
        )

    first = moment('c1', 378, 0)
    assert (
        service.record_moment(UID, first, _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
        == 'applied'
    )
    ask = lambda *_a, **_kw: SimpleNamespace(noul=lambda _name: 0.05)
    later = moment('c2', 379, 12)
    assert (
        service.record_moment(UID, later, _collaborators(model, now=T0 + timedelta(minutes=13), ask=ask, store=store))
        == 'applied'
    )
    newest_prompt = str(model.calls[-1])
    assert 'Speaker A:' in newest_prompt and 'Speaker B:' not in newest_prompt
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert len(current['speaker_display_order']) == 1


def _segments(text, *, start=0.0, step=5.0, person=None):
    words = text.split('. ')
    return [
        {
            'text': w,
            'start': start + i * step,
            'end': start + (i + 1) * step,
            'is_user': i % 2 == 0,
            'person_id': person,
        }
        for i, w in enumerate(words)
    ]


LONG = 'okay so 12:30 works for lunch near the office. perfect now the git thing where each agent gets its own worktree. and the server owns the diff so agents can just apply it cleanly. remind me to book the lunch table for twelve thirty'


def _unplaced(sid, *, minutes=0, text=LONG, trigger='interval'):
    return MomentInput(
        conversation_id='c1',
        source='omi',
        segments=[{'id': sid, 'text': text, 'start': -1.0, 'end': -1.0, 'audio_alignment': 'unplaced'}],
        started_at=T0 + timedelta(minutes=minutes),
        ended_at=T0 + timedelta(minutes=minutes + 1),
        trigger=trigger,
    )


def test_unplaced_only_notes_consume_each_segment_id_once_without_audio_offsets():
    store = StrictFirestore()
    model = FakeModel({'title': 'Unplaced speech', 'bullets': ['Still retained']}, {'bullets': ['More speech']})
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)
    first = _unplaced('s1')
    assert service.record_moment(UID, first, c) == 'applied'
    # A duplicate id in the same batch and a replay/finalization tail both cost no call.
    assert (
        service.record_moment(UID, replace(first, segments=first.segments * 2, trigger='finalize'), c)
        == 'skipped_applied'
    )
    second = _unplaced('s2', minutes=3)
    assert service.record_moment(UID, replace(second, segments=second.segments * 2), c) == 'applied'
    assert len(model.calls) == 2
    assert model.calls[1][1][1].count(LONG) == 1
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert _consumed(store) == ({'s1', 's2'}, True)
    assert 'applied_segment_ids' not in episode
    assert episode['applied']['c1'] == -1
    assert all(m['start_offset'] == m['end_offset'] == -1 for m in episode['moments'])
    assert first.segments[0]['start'] == first.segments[0]['end'] == -1
    # Placement repaired later is the same speech, not another notes input.
    placed = replace(first, segments=[{**first.segments[0], 'start': 0, 'end': 5, 'audio_alignment': None}])
    assert service.record_moment(UID, placed, c) == 'skipped_applied'


def test_placed_cursor_still_consumes_text_extended_under_an_existing_id():
    store = StrictFirestore()
    model = FakeModel()
    c = _collaborators(model, now=T0 + timedelta(minutes=5), store=store)
    first = replace(_moment(trigger='interval'), segments=[{'id': 'placed-1', 'text': LONG, 'start': 30, 'end': 40}])
    assert service.record_moment(UID, first, c) == 'applied'
    late = replace(first, segments=[{'id': 'placed-1', 'text': LONG + ' later words', 'start': 30, 'end': 50}])
    assert service.record_moment(UID, late, c) == 'applied'
    assert service.record_moment(UID, first, c) == 'skipped_applied'
    assert len(model.calls) == 2


def test_unplaced_migrates_from_rca_offset_cursor_and_failed_notes_remain_retryable():
    store = StrictFirestore()
    model = FakeModel(
        {'title': 'Call', 'bullets': ['Earlier notes']}, RuntimeError('provider down'), {'bullets': ['Recovered']}
    )
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)
    assert service.record_moment(UID, _moment(), c) == 'applied'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    raw = store.rows[('users', UID, 'episodes', episode['id'])]
    raw['applied'] = {'c1': 280.404102}
    fresh = _unplaced('new-after-280', minutes=10)
    c.now = lambda: T0 + timedelta(minutes=11)
    assert service.record_moment(UID, fresh, c) == 'llm_error'
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['last_activity_at'] == fresh.ended_at
    assert after['bullets'] == ['Earlier notes']
    assert _consumed(store) == (set(), False)
    assert service.record_moment(UID, fresh, c) == 'applied'
    assert 'new-after-280' in _consumed(store)[0]
    assert service.record_moment(UID, replace(fresh, trigger='finalize'), c) == 'skipped_applied'
    assert len(model.calls) == 3


def test_short_retained_speech_keeps_episode_live_through_notes_outage():
    store = StrictFirestore()
    model = FakeModel({'title': 'Call'}, RuntimeError('provider down'))
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)
    service.record_moment(UID, _moment(), c)
    for minute in range(5, 66, 5):
        c.now = lambda minute=minute: T0 + timedelta(minutes=minute)
        service.attach_conversation(UID, 'c1', 'omi', started_at=c.now(), collaborators=c)
        assert service.live_episode(UID, collaborators=c)['status'] == 'live'
    c.now = lambda: T0 + timedelta(minutes=66)
    assert service.record_moment(UID, _unplaced('outage', minutes=65), c) == 'llm_error'
    assert service.record_moment(UID, _unplaced('short', minutes=66, text='still talking'), c) == 'skipped_short'
    episode = service.live_episode(UID, collaborators=c)
    assert episode['last_activity_at'] == T0 + timedelta(minutes=67)
    assert episode['usage']['calls'] == 1


def test_rca_idle_close_preserves_a_discoverable_recap_with_in_progress_member():
    store = StrictFirestore()
    model = FakeModel({'title': 'Retained call', 'bullets': ['Call notes']})
    # RCA: activity stopped at 05:47:41; member stayed in_progress past 06:17:41.
    activity = datetime(2026, 10, 24, 5, 47, 41, 909750, tzinfo=timezone.utc)
    moment = replace(_unplaced('rca'), started_at=activity - timedelta(minutes=5), ended_at=activity)
    c = _collaborators(model, now=activity, store=store)
    assert service.record_moment(UID, moment, c) == 'applied'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    store.rows[('users', UID, 'conversations', 'c1')] = {'status': 'in_progress'}
    c.now = lambda: datetime(2026, 10, 24, 7, 42, tzinfo=timezone.utc)
    assert service.live_episode(UID, collaborators=c) is None
    recap = service.last_closed_episode(UID, collaborators=c)
    assert recap['id'] == episode['id'] and recap['status'] == 'closed'
    assert recap['closed_at'] == activity + timedelta(minutes=30)
    assert recap['bullets'] == ['Call notes']
    assert service.episode_by_id(UID, recap['id'], collaborators=c)['title'] == 'Retained call'
    assert service.episode_by_id('another-account', recap['id'], collaborators=c) is None
    assert service.last_closed_episode('another-account', collaborators=c) is None
    assert service.episode_for_conversation(UID, 'c1', collaborators=c)['id'] == recap['id']
    assert store.rows[('users', UID, 'conversations', 'c1')]['status'] == 'in_progress'


def test_speech_during_model_call_does_not_invalidate_notes_or_regress_activity():
    store = StrictFirestore()
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=1), store=store)
    service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c)
    original = episodes_db.get_current_episode(UID, firestore_client=store)
    calls = []

    def invoke(uid, messages):
        calls.append(messages)
        assert episodes_db.record_activity(UID, original['id'], 'c1', T0 + timedelta(minutes=2), firestore_client=store)
        return SimpleNamespace(content='{"title":"Call","bullets":["Notes arrived"]}', usage_metadata={})

    c.invoke = invoke
    assert service.record_moment(UID, _unplaced('during-call'), c) == 'applied'
    assert len(calls) == 1
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['last_activity_at'] == T0 + timedelta(minutes=2)
    assert after['state_version'] == original['state_version'] + 1
    assert after['bullets'] == ['Notes arrived']


def test_retained_speech_wins_race_with_stale_idle_reader(monkeypatch):
    store = StrictFirestore()
    c = _collaborators(FakeModel(), now=T0, store=store)
    service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c)
    stale = episodes_db.get_current_episode(UID, firestore_client=store)
    c.now = lambda: T0 + timedelta(minutes=31)
    episodes_db.record_activity(UID, stale['id'], 'c1', c.now(), firestore_client=store)
    get_current = episodes_db.get_current_episode
    reads = []

    def race(uid, **kwargs):
        reads.append(1)
        return stale if len(reads) == 1 else get_current(uid, **kwargs)

    monkeypatch.setattr(episodes_db, 'get_current_episode', race)
    live = service.live_episode(UID, collaborators=c)
    assert live['id'] == stale['id'] and live['status'] == 'live'
    assert service.last_closed_episode(UID, collaborators=c) is None


def test_unplaced_consumption_survives_episode_boundary_and_failed_open():
    store = StrictFirestore()
    model = FakeModel(
        {'title': 'First recap'}, RuntimeError('provider down'), {'title': 'Next recap'}, {'bullets': ['Tail']}
    )
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)
    first = _unplaced('s1', text='original-only-marker ' + LONG)
    assert service.record_moment(UID, first, c) == 'applied'
    c.now = lambda: T0 + timedelta(minutes=32)
    assert service.live_episode(UID, collaborators=c) is None
    second = _unplaced('s2', minutes=35, text='second-only-marker ' + LONG)
    c.now = lambda: T0 + timedelta(minutes=36)
    assert service.record_moment(UID, second, c) == 'llm_error'
    assert service.record_moment(UID, second, c) == 'applied'
    third = _unplaced('s3', minutes=37, text='tail-only-marker ' + LONG, trigger='finalize')
    tail = replace(third, segments=[*first.segments, *second.segments, *third.segments])
    assert service.record_moment(UID, tail, c) == 'applied'
    assert 'original-only-marker' not in model.calls[-1][1][1]
    assert 'second-only-marker' not in model.calls[-1][1][1]
    assert 'tail-only-marker' in model.calls[-1][1][1]
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert _consumed(store) == ({'s1', 's2', 's3'}, True)
    assert 'applied_segment_ids' not in episode


def test_fifty_thousand_unplaced_segments_keep_every_document_small_and_never_reprocess():
    """A pathological all-unplaced conversation: receipts must shard out of the episode
    document (no document may approach the 1 MiB limit) while the finalization tail of
    the whole transcript still dedupes against everything consumed live."""
    store = StrictFirestore()
    model = FakeModel({'title': 'Long unplaced call', 'bullets': ['Notes']})
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)
    c.owner_name = lambda uid: 'Owner'

    def unplaced_batch(first_index, count, *, minutes, trigger='interval'):
        return MomentInput(
            conversation_id='c1',
            source='omi',
            segments=[
                {
                    'id': f'seg-{i:05d}',
                    'text': f'speech {i} alpha beta',
                    'start': -1.0,
                    'end': -1.0,
                    'audio_alignment': 'unplaced',
                }
                for i in range(first_index, first_index + count)
            ],
            started_at=T0 + timedelta(minutes=minutes),
            ended_at=T0 + timedelta(minutes=minutes + 1),
            trigger=trigger,
        )

    batches = 25
    per_batch = 2_000
    total = batches * per_batch
    consumed_ids = set()
    for index in range(batches):
        minute = 1 + index * 1.5  # Faster than the idle gap, slower than the rate limit.
        c.now = lambda minute=minute: T0 + timedelta(minutes=minute + 1)
        moment = unplaced_batch(index * per_batch, per_batch, minutes=minute)
        assert service.record_moment(UID, moment, c) == 'applied'
        consumed_ids |= {s['id'] for s in moment.segments}

    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    raw_episode = store.rows[('users', UID, 'episodes', episode['id'])]
    episode_bytes = len(json.dumps(raw_episode, default=str))
    assert episode_bytes < 65_536, episode_bytes
    assert 'applied_segment_ids' not in episode

    # The receipts sharded: a bounded base window plus immutable archives, each small.
    base = store.rows[('users', UID, 'episode_segment_receipts', 'c1')]
    assert len(base['ids']) <= episode_receipts.SHARD_SIZE
    archived = 0
    receipt_docs = 0
    for path, row in store.rows.items():
        if path[:4] == ('users', UID, 'episode_segment_receipts', 'c1'):
            receipt_docs += 1
            assert len(json.dumps(row, default=str)) < 128_000, path
            if len(path) == 6 and path[4] == 's':
                archived += len(row['ids'])
    assert base['shards'] == (total - len(base['ids'])) // episode_receipts.SHARD_SIZE
    assert archived + len(base['ids']) == total
    assert _consumed(store) == (consumed_ids, True)

    # The whole-transcript finalization tail costs nothing: no id is processed twice.
    calls_before = len(model.calls)
    tail = unplaced_batch(0, total, minutes=1 + batches * 1.5, trigger='finalize')
    assert service.record_moment(UID, tail, c) == 'skipped_applied'
    assert len(model.calls) == calls_before


def test_past_the_cap_the_receipt_base_keeps_the_most_recent_ids_for_live_replays():
    """Past the cap the base holds the most recently consumed ids, not the
    alphabetically highest: the live tracker re-presents its buffered segments,
    so a just-consumed id (or its repaired placement) would otherwise be
    re-fed to the model on the live path."""
    store = StrictFirestore()
    model = FakeModel({'title': 'Long unplaced call', 'bullets': ['Notes']}, {'bullets': ['More']})
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)

    def unplaced(ids, *, minutes):
        return MomentInput(
            conversation_id='c1',
            source='omi',
            segments=[
                {
                    'id': sid,
                    'text': f'speech {sid} alpha beta',
                    'start': -1.0,
                    'end': -1.0,
                    'audio_alignment': 'unplaced',
                }
                for sid in ids
            ],
            started_at=T0 + timedelta(minutes=minutes),
            ended_at=T0 + timedelta(minutes=minutes + 1),
            trigger='interval',
        )

    # The late batch sorts below every early id: an alphabetical window archived
    # exactly these and kept the old ids instead.
    early = [f'm-{i:05d}' for i in range(episode_receipts.SHARD_SIZE)]
    late = [f'a-{i:05d}' for i in range(50)]
    assert service.record_moment(UID, unplaced(early, minutes=1), c) == 'applied'
    c.now = lambda: T0 + timedelta(minutes=3)
    assert service.record_moment(UID, unplaced(late, minutes=2), c) == 'applied'

    # The base keeps the most recent SHARD_SIZE ids (every late one included);
    # only the oldest early ids rolled into the first archive.
    base = store.rows[('users', UID, 'episode_segment_receipts', 'c1')]
    assert len(base['ids']) == episode_receipts.SHARD_SIZE
    assert set(base['ids']) == set(early[50:]) | set(late)
    assert base['shards'] == 1
    assert store.rows[('users', UID, 'episode_segment_receipts', 'c1', 's', '0')]['ids'] == early[:50]
    assert _consumed(store) == (set(early) | set(late), True)

    # The live path dedupes against the base alone: the just-consumed batch
    # replay (the tracker re-presenting its buffer) and its repaired placement
    # both cost no model call.
    calls = len(model.calls)
    c.now = lambda: T0 + timedelta(minutes=4)
    assert service.record_moment(UID, unplaced(late, minutes=3), c) == 'skipped_applied'
    repaired = replace(
        unplaced(late, minutes=4),
        segments=[
            {**s, 'start': 5.0, 'end': 10.0, 'audio_alignment': None} for s in unplaced(late, minutes=4).segments
        ],
    )
    c.now = lambda: T0 + timedelta(minutes=5)
    assert service.record_moment(UID, repaired, c) == 'skipped_applied'
    assert len(model.calls) == calls


def test_legacy_episode_document_receipts_are_adopted_and_retired():
    """Episodes written before the receipts collection kept consumed ids in the episode
    document: the first post-upgrade write adopts them and retires the in-document list."""
    store = StrictFirestore()
    model = FakeModel({'title': 'Call', 'bullets': ['Earlier notes']}, {'bullets': ['Later notes']})
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)
    assert service.record_moment(UID, _moment(), c) == 'applied'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    raw = store.rows[('users', UID, 'episodes', episode['id'])]
    raw['applied_segment_ids'] = {'c1': ['legacy-1', 'legacy-2'], 'other-conversation': ['kept']}
    # A live replay of a legacy-consumed id, then new speech in the same moment.
    legacy_replay = {
        'id': 'legacy-1',
        'text': LONG,
        'start': -1.0,
        'end': -1.0,
        'audio_alignment': 'unplaced',
    }
    fresh = {
        'id': 'fresh-1',
        'text': 'so a brand new topic for the running notes',
        'start': -1.0,
        'end': -1.0,
        'audio_alignment': 'unplaced',
    }
    moment = MomentInput(
        conversation_id='c1',
        source='omi',
        segments=[legacy_replay, fresh, fresh],
        started_at=T0 + timedelta(minutes=3),
        ended_at=T0 + timedelta(minutes=4),
        trigger='interval',
    )
    c.now = lambda: T0 + timedelta(minutes=5)
    assert service.record_moment(UID, moment, c) == 'skipped_short'
    # A short moment records nothing; the legacy list still serves the fallback.
    assert _consumed(store) == (set(), False)
    longer = replace(moment, segments=[legacy_replay, fresh, fresh, dict(fresh, id='fresh-2', text=LONG)])
    assert service.record_moment(UID, longer, c) == 'applied'
    assert _consumed(store) == ({'legacy-1', 'legacy-2', 'fresh-1', 'fresh-2'}, True)
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after.get('applied_segment_ids') == {'other-conversation': ['kept']}
    raw_after = store.rows[('users', UID, 'episodes', episode['id'])]
    assert raw_after.get('applied_segment_ids') == {'other-conversation': ['kept']}


def test_last_closed_recap_poll_cache_reads_firestore_once_per_window(monkeypatch):
    reads = []

    def read(uid, *, firestore_client=None):
        reads.append(uid)
        return {'id': 'e1', 'status': 'closed'}

    monkeypatch.setattr(episodes_db, 'get_last_closed_episode', read)
    assert service.last_closed_episode(UID, now=0.0)['id'] == 'e1'
    assert service.last_closed_episode(UID, now=29.9)['id'] == 'e1'  # inside the cache window
    assert len(reads) == 1
    assert service.last_closed_episode(UID, fresh=True, now=29.95)['id'] == 'e1'  # recovery navigation reads through
    assert len(reads) == 2
    assert service.last_closed_episode(UID, now=75.0)['id'] == 'e1'  # window expired
    assert len(reads) == 3


def _moment(conversation_id='c1', *, minutes=0.0, trigger='pause', text=LONG, start=0.0, source='omi', person=None):
    return MomentInput(
        conversation_id=conversation_id,
        source=source,
        segments=_segments(text, start=start, person=person),
        started_at=T0 + timedelta(minutes=minutes),
        ended_at=T0 + timedelta(minutes=minutes + 1),
        trigger=trigger,
    )


def test_first_moment_opens_an_episode_with_sealed_content():
    store = StrictFirestore()
    model = FakeModel(
        {
            'title': 'Coding at the café',
            'moment_heading': 'Lunch plans',
            'bullets': ['Lunch with Huong at 12:30', 'Git worktree per agent'],
            'people': ['Huong'],
            'items': [{'text': 'Book lunch table for 12:30', 'kind': 'reminder'}],
        }
    )
    c = _collaborators(model, now=T0 + timedelta(minutes=1), store=store)
    assert service.record_moment(UID, _moment(person='p1'), c) == 'applied'

    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['title'] == 'Coding at the café'
    assert episode['conversation_ids'] == ['c1'] and episode['sources'] == ['omi']
    assert episode['moments'][0]['heading'] == 'Lunch plans'
    assert episode['provisional_items'][0]['status'] == 'provisional'
    assert episode['applied']['c1'] == 20.0
    assert episode['usage'] == {'calls': 1, 'input_tokens': 400, 'output_tokens': 120}
    # Speech-derived text never sits in plaintext on the document.
    raw = store.rows[('users', UID, 'episodes', episode['id'])]
    assert 'Huong' not in json.dumps(raw, default=str) and isinstance(raw['content'], str)
    # The model saw only the empty state and this moment, with the named speaker.
    system, user = model.calls[0]
    assert system[0] == 'system' and '"bullets":[]' in user[1] and 'Huong:' in user[1]
    assert user[1].index('Episode state so far') < user[1].index('Newest moment')


def test_next_moment_sends_only_state_plus_new_text_and_dedupes_applied_segments():
    store = StrictFirestore()
    model = FakeModel({'title': 'T', 'moment_heading': 'Lunch', 'bullets': ['Lunch at 12:30']}, {'bullets': ['B2']})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    later = _moment(minutes=3, text=LONG.upper(), start=0.0)
    # Same conversation, same offsets: already applied, no call.
    assert (
        service.record_moment(UID, later, _collaborators(model, now=T0 + timedelta(minutes=4), store=store))
        == 'skipped_applied'
    )
    fresh = _moment(
        minutes=3,
        text='so pricing for the hosted tier. we said twenty dollars a month for teams. and a free tier for students. that sounds right to me',
        start=30.0,
    )
    assert (
        service.record_moment(UID, fresh, _collaborators(model, now=T0 + timedelta(minutes=4), store=store))
        == 'applied'
    )
    user_message = model.calls[1][1][1]
    assert '"Lunch at 12:30"' in user_message and 'git thing' not in user_message and 'pricing' in user_message
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert [m['heading'] for m in episode['moments']] == ['Lunch', '']
    assert episode['bullets'] == ['B2'] and episode['applied']['c1'] == 50.0


def test_short_and_rate_limited_moments_cost_nothing():
    store = StrictFirestore()
    model = FakeModel({'bullets': ['A']})
    assert (
        service.record_moment(UID, _moment(text='hi there'), _collaborators(model, now=T0, store=store))
        == 'skipped_short'
    )
    assert model.calls == []
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    soon = _moment(minutes=1, start=40.0, text=LONG.replace('lunch', 'dinner'))
    assert (
        service.record_moment(UID, soon, _collaborators(model, now=T0 + timedelta(minutes=1, seconds=20), store=store))
        == 'rate_limited'
    )
    assert len(model.calls) == 1


def test_model_failure_keeps_state_and_reports_outcome():
    store = StrictFirestore()
    model = FakeModel(RuntimeError('provider down'))
    assert service.record_moment(UID, _moment(), _collaborators(model, now=T0, store=store)) == 'llm_error'
    # The occasion still exists, without notes; the next moment fills them in.
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['title'] == '' and episode['bullets'] == [] and episode['usage']['calls'] == 0

    def garbage(uid, messages):
        return SimpleNamespace(content='no json at all', usage_metadata={})

    assert service.record_moment(UID, _moment(), _collaborators(garbage, now=T0, store=store)) == 'parse_error'


def test_disabled_does_nothing(monkeypatch):
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    store = StrictFirestore()
    model = FakeModel({'bullets': ['A']})
    assert service.record_moment(UID, _moment(), _collaborators(model, now=T0, store=store)) == 'disabled'
    assert model.calls == [] and store.rows == {}
    assert service.on_conversation_finalized(UID, 'c1', {}, trigger='capture_end') == 'skipped'


def test_jev_moved_on_closes_and_opens_a_new_episode():
    store = StrictFirestore()
    model = FakeModel(
        {'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]}, {'title': 'Standup'}
    )
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    asked = []

    def ask(state, questions, **kwargs):
        asked.append(state)
        return SimpleNamespace(noul=lambda name: 0.05)

    later = _moment('c2', minutes=12)
    assert (
        service.record_moment(UID, later, _collaborators(model, now=T0 + timedelta(minutes=13), ask=ask, store=store))
        == 'applied'
    )
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'moved_on'
    assert closed['provisional_items'][0]['status'] == 'dropped'
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current['id'] != first['id'] and current['conversation_ids'] == ['c2']
    assert 'minutes_since_last_speech' in asked[0] and 'Lunch' in asked[0]


def test_parallel_capture_attaches_a_source_without_a_model_call():
    store = StrictFirestore()
    model = FakeModel({'title': 'Meeting', 'bullets': ['A']})
    service.record_moment(UID, _moment(minutes=0), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    other = _moment('c-desktop', minutes=0.5, source='desktop')
    assert (
        service.record_moment(UID, other, _collaborators(model, now=T0 + timedelta(minutes=2), store=store))
        == 'parallel'
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['c1', 'c-desktop'] and episode['sources'] == ['omi', 'desktop']
    assert len(model.calls) == 1
    assert episodes_db.get_episode_for_conversation(UID, 'c-desktop', firestore_client=store)['id'] == episode['id']


def test_finalization_applies_the_tail_and_reconciles_provisional_items():
    store = StrictFirestore()
    model = FakeModel(
        {
            'title': 'Lunch',
            'bullets': ['A'],
            'items': [{'text': 'Book lunch table for 12:30'}, {'text': 'Water the plants'}],
        },
        {'bullets': ['A', 'B']},
    )
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    row = {
        'id': 'c1',
        'source': 'omi',
        'started_at': T0,
        'finished_at': T0 + timedelta(minutes=2),
        'transcript_segments': _segments(LONG)
        + _segments(
            'and one more thing about the agents. they also need a sandbox for builds. that is all for now', start=30.0
        ),
    }
    saved = {'c1': [{'id': 'task-1', 'description': 'Book a lunch table'}]}
    c = _collaborators(model, now=T0 + timedelta(minutes=3), saved=saved, store=store)
    assert service.on_conversation_finalized(UID, 'c1', row, trigger='capture_end', collaborators=c) == 'reconciled'
    # The phone's occasion conversation ended on silence, so its episode ended with it.
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    episode = episodes_db.get_episode_for_conversation(UID, 'c1', firestore_client=store)
    assert episode['status'] == 'closed' and episode['close_reason'] == 'gap'
    statuses = {item['text']: (item['status'], item['action_item_id']) for item in episode['provisional_items']}
    assert statuses == {'Book lunch table for 12:30': ('kept', 'task-1'), 'Water the plants': ('dropped', None)}
    # The tail call saw only the unapplied tail.
    assert 'sandbox' in model.calls[1][1][1] and 'git thing' not in model.calls[1][1][1]
    assert service.on_conversation_finalized(UID, 'c1', row, trigger='user_reprocess', collaborators=c) == 'skipped'


def _row(conversation_id='c1', *, text=None, start=30.0, source='omi', **extra):
    return {
        'id': conversation_id,
        'source': source,
        'started_at': T0,
        'finished_at': T0 + timedelta(minutes=2),
        'transcript_segments': _segments(LONG) + (_segments(text, start=start) if text else []),
        **extra,
    }


TAIL = 'and one more thing about the agents. they also need a sandbox for builds. that is all for now'


def test_wrap_up_with_a_conversation_closes_now_and_reconciles_when_it_lands():
    store = StrictFirestore()
    model = FakeModel(
        {'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table for 12:30'}]},
        {'bullets': ['A', 'B']},
    )
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    closed = service.wrap_up(UID, episode['id'], conversation_id='c1', collaborators=c)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    assert closed['closing_conversation_id'] == 'c1' and closed['wrap_up_requested_at'] == T0 + timedelta(minutes=2)
    # Nothing live for the app to pick back up; the conversation's item waits for its processing.
    assert service.live_episode(UID, collaborators=c) is None
    assert [i['status'] for i in closed['provisional_items']] == ['provisional']

    saved = {'c1': [{'id': 'task-1', 'description': 'Book a lunch table'}]}
    c = _collaborators(model, now=T0 + timedelta(minutes=3), saved=saved, store=store)
    row = _row(text=TAIL)
    assert service.on_conversation_finalized(UID, 'c1', row, trigger='client_finalize', collaborators=c) == 'reconciled'
    after = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    # The tail completed the closed episode's notes instead of opening a new live one.
    assert after['status'] == 'closed' and after['bullets'] == ['A', 'B']
    assert {i['text']: i['status'] for i in after['provisional_items']} == {'Book lunch table for 12:30': 'kept'}
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    assert service.live_episode(UID, collaborators=c) is None


def test_a_client_finalize_closes_the_live_episode_at_once_and_is_idempotent():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    # A pendant double-tap: the finalize closes the episode before the conversation processes.
    assert service.close_on_finalize(UID, 'c1', trigger='client_finalize', collaborators=c) == 'closed'
    closed = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    assert closed['closed_at'] == T0 + timedelta(minutes=2)
    assert service.live_episode(UID, collaborators=c) is None
    # A second double-tap, or Wrap up after it, changes nothing and never errors.
    assert service.close_on_finalize(UID, 'c1', trigger='client_finalize', collaborators=c) == 'not_live'
    again = service.wrap_up(UID, episode['id'], conversation_id='c1', collaborators=c)
    assert again['status'] == 'closed' and again['state_version'] == closed['state_version']
    assert service.wrap_up(UID, episode['id'], conversation_id=None, collaborators=c)['status'] == 'closed'
    # Processing finishing afterwards reconciles onto the closed episode and opens nothing.
    row = _row()
    assert service.on_conversation_finalized(UID, 'c1', row, trigger='client_finalize', collaborators=c) == 'reconciled'
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    final = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert [i['status'] for i in final['provisional_items']] == ['dropped']


def test_an_ended_conversation_never_reopens_its_episode_and_the_next_words_open_a_new_one():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'title': 'Standup', 'bullets': ['S']})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    service.close_on_finalize(UID, 'c1', trigger='client_finalize', collaborators=c)
    # The old conversation's late live moment and a re-attach (a reconnect) are both dropped.
    late = _moment('c1', minutes=1, start=60.0, text=TAIL + '. and a little more to say here')
    assert service.record_moment(UID, late, c) == 'skipped_closed'
    assert service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c) == 'attached'
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    assert len(model.calls) == 1
    # The next live words open the new episode, which the old conversation never joins.
    assert _attach(store, 'c2', minutes=3) == 'opened'
    second = episodes_db.get_current_episode(UID, firestore_client=store)
    assert second['id'] != first['id'] and second['conversation_ids'] == ['c2']
    assert service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c) == 'attached'
    assert service.record_moment(UID, late, c) == 'skipped_closed'
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current['conversation_ids'] == ['c2'] and current['state_version'] == second['state_version']
    assert episodes_db.get_episode_for_conversation(UID, 'c1', firestore_client=store)['id'] == first['id']


def test_a_finalize_tail_never_opens_an_episode_after_its_own_closed():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['A', 'B']})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    # Closed by the idle rule, not by this conversation's end: its tail still stays with it.
    idle = _collaborators(model, now=T0 + timedelta(hours=2), store=store)
    assert service.live_episode(UID, collaborators=idle) is None
    service.on_conversation_finalized(UID, 'c1', _row(text=TAIL), trigger='client_finalize', collaborators=idle)
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['close_reason'] == 'idle' and closed['bullets'] == ['A', 'B']


def test_server_recovery_reconciles_and_closes_the_occasion():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table for 12:30'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    saved = {'c1': [{'id': 'task-1', 'description': 'Book a lunch table'}]}
    c = _collaborators(model, now=T0 + timedelta(minutes=30), saved=saved, store=store)
    assert service.close_on_finalize(UID, 'c1', trigger='server_recovery', source='omi', collaborators=c) == 'closed'
    assert (
        service.on_conversation_finalized(UID, 'c1', _row(), trigger='server_recovery', collaborators=c) == 'reconciled'
    )
    episode = episodes_db.get_episode_for_conversation(UID, 'c1', firestore_client=store)
    assert episode['status'] == 'closed' and episode['close_reason'] == 'gap'
    assert [(i['status'], i['action_item_id']) for i in episode['provisional_items']] == [('kept', 'task-1')]


def test_a_server_side_end_keeps_the_episode_when_the_occasion_goes_on():
    store = StrictFirestore()
    _attach(store, 'c1', minutes=0, source='desktop')
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=5), store=store)
    # Desktop capture still splits on short silences: its end is not the occasion's end.
    assert service.close_on_finalize(UID, 'c1', trigger='capture_end', source='desktop', collaborators=c) == 'kept_open'
    # A conversation that joined after this one (a rollover, another device) keeps it going.
    _attach(store, 'c2', minutes=1)
    assert service.close_on_finalize(UID, 'c1', trigger='capture_end', source='omi', collaborators=c) == 'continued'
    assert episodes_db.get_current_episode(UID, firestore_client=store)['status'] == 'live'
    # A client finalize is the user ending it, whatever else is attached.
    assert service.close_on_finalize(UID, 'c1', trigger='client_finalize', collaborators=c) == 'closed'
    assert service.close_on_finalize(UID, 'c1', trigger='user_reprocess', collaborators=c) == 'skipped'


def test_a_wrap_up_left_live_by_an_older_server_is_never_served_as_live():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    episodes_db.update_episode(
        UID,
        episode['id'],
        expected_version=episode['state_version'],
        updates={'wrap_up_requested_at': T0 + timedelta(minutes=2), 'closing_conversation_id': 'c1'},
        firestore_client=store,
    )
    c = _collaborators(model, now=T0 + timedelta(minutes=2, seconds=5), store=store)
    assert service.live_episode(UID, collaborators=c) is None
    closed = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    # Its conversation's item still waits for that conversation's reconciliation.
    assert [i['status'] for i in closed['provisional_items']] == ['provisional']


def test_a_discarded_conversation_still_ends_its_episode_and_drops_its_items():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    row = _row(discarded=True)
    assert (
        service.on_conversation_finalized(UID, 'c1', row, trigger='client_finalize', collaborators=c)
        == 'skipped_discarded'
    )
    closed = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    assert [i['status'] for i in closed['provisional_items']] == ['dropped']


def test_wrap_up_without_a_conversation_closes_now_and_dismiss_marks_an_item():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    item_id = episode['provisional_items'][0]['id']
    dismissed = service.dismiss_item(UID, episode['id'], item_id, collaborators=c)
    assert dismissed['provisional_items'][0]['status'] == 'dismissed'
    closed = service.wrap_up(UID, episode['id'], conversation_id=None, collaborators=c)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'user'
    assert closed['provisional_items'][0]['status'] == 'dismissed'
    assert service.wrap_up(UID, 'missing', conversation_id=None, collaborators=c) is None


def test_reads_close_idle_episodes_lazily_and_wire_projection_hides_internals():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A'], 'items': [{'text': 'Book lunch table'}]})
    service.record_moment(UID, _moment(), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    live = service.live_episode(UID, collaborators=_collaborators(model, now=T0 + timedelta(minutes=5), store=store))
    wire = service.to_wire(live)
    assert set(wire) == {
        'id',
        'status',
        'started_at',
        'last_activity_at',
        'closed_at',
        'close_reason',
        'title',
        'bullets',
        'people',
        'provisional_items',
        'moments',
        'conversation_ids',
        'sources',
        'state_updated_at',
    }
    assert Episode.model_validate(wire).provisional_items[0].text == 'Book lunch table'
    idle = _collaborators(model, now=T0 + timedelta(hours=2), store=store)
    assert service.live_episode(UID, collaborators=idle) is None
    closed = service.episode_for_conversation(UID, 'c1', collaborators=idle)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'idle'


def test_smart_merge_absorb_repoints_the_episode_to_the_survivor():
    store = StrictFirestore()
    model = FakeModel({'title': 'Dinner', 'bullets': ['A']}, {'title': 'Dinner', 'bullets': ['B']})
    service.record_moment(UID, _moment('survivor'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    service.record_moment(
        UID, _moment('donor', minutes=3), _collaborators(model, now=T0 + timedelta(minutes=4), store=store)
    )
    donor_row = {'id': 'donor', 'smart_merge': {'role': 'donor', 'survivor_id': 'survivor'}, 'finished_at': T0}
    c = _collaborators(model, now=T0 + timedelta(minutes=5), store=store)
    service.on_conversation_finalized(
        UID, 'survivor', donor_row, trigger='capture_end', absorbed_from='donor', collaborators=c
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['survivor']
    assert {m['conversation_id'] for m in episode['moments']} == {'survivor'}


def test_commit_conflict_is_reported_not_raised(monkeypatch):
    store = StrictFirestore()
    model = FakeModel({'bullets': ['A']}, {'bullets': ['B']})

    def always_conflict(*args, **kwargs):
        raise episodes_db.EpisodeConflict('state_version_changed')

    monkeypatch.setattr(episodes_db, 'commit_moment', always_conflict)
    assert service.record_moment(UID, _moment(), _collaborators(model, now=T0, store=store)) == 'conflict'
    assert len(model.calls) == 2


def test_mentor_state_is_the_compact_render_or_none(monkeypatch):
    monkeypatch.setattr(
        service, 'live_episode', lambda uid: {'title': 'Lunch', 'bullets': ['A'], 'provisional_items': []}
    )
    assert json.loads(service.mentor_episode_state(UID))['topic'] == 'Lunch'
    monkeypatch.setattr(service, 'live_episode', lambda uid: None)
    assert service.mentor_episode_state(UID) is None
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    assert service.mentor_episode_state(UID) is None


# --------------------------------------------------------------------------- structure before notes


def _attach(store, conversation_id, *, minutes, source='omi', now_minutes=None):
    c = _collaborators(
        FakeModel(), now=T0 + timedelta(minutes=now_minutes if now_minutes is not None else minutes), store=store
    )
    return service.attach_conversation(
        UID, conversation_id, source, started_at=T0 + timedelta(minutes=minutes), collaborators=c
    )


def test_first_words_open_the_episode_without_a_model_call():
    store = StrictFirestore()
    model = FakeModel()
    c = _collaborators(model, now=T0, store=store)
    assert service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c) == 'opened'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    # The app gets a live episode, its real start and its member conversation right away.
    assert episode['status'] == 'live' and episode['title'] == '' and model.calls == []
    assert episode['started_at'] == T0 and episode['conversation_ids'] == ['c1'] and episode['sources'] == ['omi']
    assert episodes_db.get_episode_for_conversation(UID, 'c1', firestore_client=store)['id'] == episode['id']
    # Attaching again (a reconnect, another replica) is a no-op.
    assert service.attach_conversation(UID, 'c1', 'omi', started_at=T0, collaborators=c) == 'attached'


def test_fragments_join_the_live_episode_so_home_can_hide_them():
    store = StrictFirestore()
    _attach(store, 'c1', minutes=0)
    # A live split a minute later, and an overlapping capture from another device.
    assert _attach(store, 'c2', minutes=1) == 'joined'
    assert _attach(store, 'c3', minutes=0.5, source='phone', now_minutes=1) == 'joined'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['c1', 'c2', 'c3'] and episode['sources'] == ['omi', 'phone']
    # Then the first moment's notes land on that same episode.
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(
        UID, _moment('c2', minutes=1), _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    )
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['id'] == episode['id'] and after['title'] == 'Lunch'


def test_an_ambiguous_gap_joins_provisionally_and_jev_splits_it_off():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'title': 'Standup'})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    assert _attach(store, 'c2', minutes=12) == 'pending'
    joined = episodes_db.get_current_episode(UID, firestore_client=store)
    assert joined['conversation_ids'] == ['c1', 'c2'] and set(joined['pending_boundary']) == {'c2'}

    ask = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05)  # noqa: E731
    later = _moment('c2', minutes=12)
    c = _collaborators(model, now=T0 + timedelta(minutes=13), ask=ask, store=store)
    assert service.record_moment(UID, later, c) == 'applied'
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['close_reason'] == 'moved_on' and closed['conversation_ids'] == ['c1']
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current['id'] != first['id'] and current['conversation_ids'] == ['c2'] and current['title'] == 'Standup'
    assert episodes_db.get_episode_for_conversation(UID, 'c2', firestore_client=store)['id'] == current['id']


def test_jev_same_occasion_keeps_the_provisional_join():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['B']})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    _attach(store, 'c2', minutes=12)
    ask = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9)  # noqa: E731
    c = _collaborators(model, now=T0 + timedelta(minutes=13), ask=ask, store=store)
    assert service.record_moment(UID, _moment('c2', minutes=12), c) == 'applied'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['conversation_ids'] == ['c1', 'c2'] and episode['pending_boundary'] == {}
    assert episode['bullets'] == ['B']


def test_a_long_gap_attach_closes_the_old_episode_and_opens_a_new_one():
    store = StrictFirestore()
    _attach(store, 'c1', minutes=0)
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    # 29 minutes later sits between the continue and close gaps: a provisional join.
    assert _attach(store, 'c2', minutes=29, now_minutes=29) == 'pending'
    assert _attach(store, 'c9', minutes=120, now_minutes=120) == 'opened'
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['status'] == 'closed'


def test_an_idle_close_is_stamped_when_the_quiet_reached_the_gap():
    store = StrictFirestore()
    _attach(store, 'c1', minutes=0)
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    # Nobody looks for eight hours; the next read closes it, dated at the gap, not at the read.
    reader = _collaborators(FakeModel(), now=T0 + timedelta(hours=8), store=store)
    assert service.live_episode(UID, collaborators=reader) is None
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['close_reason'] == 'idle'
    assert closed['closed_at'] == T0 + timedelta(seconds=config.CLOSE_GAP_SECONDS)


def test_two_provisional_joins_are_each_settled_at_their_own_first_moment():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, {'bullets': ['B']}, {'bullets': ['C']})
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    _attach(store, 'c2', minutes=12)
    _attach(store, 'c3', minutes=12.5, source='phone', now_minutes=12.5)
    assert set(episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary']) == {'c2', 'c3'}
    keep = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.9)  # noqa: E731
    service.record_moment(
        UID, _moment('c2', minutes=12), _collaborators(model, now=T0 + timedelta(minutes=13), ask=keep, store=store)
    )
    assert set(episodes_db.get_current_episode(UID, firestore_client=store)['pending_boundary']) == {'c3'}


def test_a_failed_model_call_after_a_split_still_leaves_a_live_episode():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']}, RuntimeError('provider down'))
    service.record_moment(UID, _moment('c1'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    _attach(store, 'c2', minutes=12)
    moved_on = lambda *a, **k: SimpleNamespace(noul=lambda name: 0.05)  # noqa: E731
    c = _collaborators(model, now=T0 + timedelta(minutes=13), ask=moved_on, store=store)
    assert service.record_moment(UID, _moment('c2', minutes=12), c) == 'llm_error'
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert current is not None and current['id'] != first['id'] and current['conversation_ids'] == ['c2']
    assert current['title'] == ''


def test_moment_render_receives_account_and_conversation_and_language_reaches_update(monkeypatch):
    from dataclasses import replace
    from unittest.mock import Mock

    render = Mock(wraps=service.incremental.render_moment)
    update = Mock(wraps=service.incremental.run_incremental_update)
    monkeypatch.setattr(service.incremental, 'render_moment', render)
    monkeypatch.setattr(service.incremental, 'run_incremental_update', update)
    moment = replace(_moment(), language='en')
    model = FakeModel({'title': 'Fixture', 'moment_heading': 'Fixture', 'bullets': ['Fixture']})
    result = service.record_moment(
        UID, moment, _collaborators(model, now=T0 + timedelta(minutes=1), store=StrictFirestore())
    )
    assert result == 'applied'
    assert render.call_args.kwargs == {
        'uid': UID,
        'conversation_id': moment.conversation_id,
        'owner_name': 'You',
        'voice_order': [],
    }
    assert update.call_args.kwargs['conversation_language'] == 'en'
    assert len(model.calls) == 1


# --------------------------------------------------------------------------- offline-sync finalize


def _wal_row(conversation_id='c-wal', *, minutes=0.5, text=LONG, source='omi', **extra):
    started = T0 + timedelta(minutes=minutes)
    return {
        'id': conversation_id,
        'source': source,
        'started_at': started,
        'finished_at': started + timedelta(minutes=1),
        'transcript_segments': _segments(text),
        **extra,
    }


def test_a_sync_finalized_conversation_joins_the_live_episode_covering_it():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    # A pendant's safety-WAL conversation, finalized by offline sync inside the live span.
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    assert (
        service.on_conversation_finalized(UID, 'c-wal', _wal_row(), trigger='sync_update', collaborators=c) == 'joined'
    )
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['id'] == episode['id'] and after['status'] == 'live'
    assert after['conversation_ids'] == ['c-live', 'c-wal']
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store)['id'] == episode['id']
    # A parallel capture: no model call, and its duplicate text never feeds the notes.
    assert len(model.calls) == 1
    assert after['applied'].keys() == {'c-live'} and [m['conversation_id'] for m in after['moments']] == ['c-live']
    # A later WAL chunk re-runs the hook and feeds nothing either.
    assert (
        service.on_conversation_finalized(UID, 'c-wal', _wal_row(), trigger='sync_update', collaborators=c)
        == 'finalized'
    )
    replay = episodes_db.get_current_episode(UID, firestore_client=store)
    assert replay['applied'].keys() == {'c-live'} and len(model.calls) == 1


def test_a_sync_finalized_conversation_never_reopens_a_closed_episode():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    assert service.close_on_finalize(UID, 'c-live', trigger='client_finalize', collaborators=c) == 'closed'
    # The WAL row's span sits inside the closed episode: it stays an ordinary row.
    assert (
        service.on_conversation_finalized(UID, 'c-wal', _wal_row(), trigger='sync_update', collaborators=c)
        == 'no_episode'
    )
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store) is None
    closed = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['conversation_ids'] == ['c-live']


def test_a_discarded_sync_conversation_never_joins():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    assert (
        service.on_conversation_finalized(
            UID, 'c-wal', _wal_row(discarded=True), trigger='sync_update', collaborators=c
        )
        == 'skipped_discarded'
    )
    # The live occasion goes on untouched.
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['id'] == episode['id'] and after['status'] == 'live' and after['conversation_ids'] == ['c-live']
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store) is None


def test_an_ambiguous_or_stale_sync_row_stays_an_ordinary_row():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=13), store=store)
    # Twelve minutes after the last speech sits in Jev's zone: not a basis to join,
    # and never a basis to close the occasion.
    assert (
        service.on_conversation_finalized(UID, 'c-wal', _wal_row(minutes=12), trigger='sync_update', collaborators=c)
        == 'no_episode'
    )
    assert episodes_db.get_episode(UID, episode['id'], firestore_client=store)['status'] == 'live'
    # Audio from an occasion already over: it began far before this episode and
    # its span ended long before the episode's first recorded words.
    _attach(store, 'c-next', minutes=60, now_minutes=60)
    current = episodes_db.get_current_episode(UID, firestore_client=store)
    assert (
        service.on_conversation_finalized(UID, 'c-wal', _wal_row(minutes=45), trigger='sync_update', collaborators=c)
        == 'no_episode'
    )
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['id'] == current['id'] and 'c-wal' not in after['conversation_ids']


def test_sync_finalize_with_no_live_episode_creates_nothing_but_capture_end_still_opens_one():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    # No live occasion: a late WAL row never mints an episode for itself.
    assert (
        service.on_conversation_finalized(UID, 'c-wal', _wal_row(), trigger='sync_update', collaborators=c)
        == 'no_episode'
    )
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store) is None
    # An existing trigger keeps today's behavior: the tail opens the episode.
    assert service.on_conversation_finalized(
        UID, 'c-cap', _wal_row('c-cap'), trigger='capture_end', collaborators=c
    ) in {
        'finalized',
        'reconciled',
    }
    opened = episodes_db.get_episode_for_conversation(UID, 'c-cap', firestore_client=store)
    assert opened is not None and 'c-cap' in opened['conversation_ids']


# --------------------------------------------------------------------------- sync intake attach


def test_a_sync_clip_joins_the_live_episode_at_intake_and_the_finalize_hook_stays_idempotent():
    store = StrictFirestore()
    _attach(store, 'c-live', minutes=0)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    model = FakeModel()
    c = _collaborators(model, now=T0 + timedelta(minutes=2), store=store)
    # The WAL row exists the moment intake persisted it; Home must fold it now, not
    # after enrichment finishes.
    assert service.attach_synced_intake(UID, 'c-wal', _wal_row(), collaborators=c) == 'joined'
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['id'] == episode['id'] and after['status'] == 'live'
    assert after['conversation_ids'] == ['c-live', 'c-wal']
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store)['id'] == episode['id']
    # The cheap rules alone decided: no model call, and no text fed.
    assert model.calls == [] and after['applied'].keys() == set() and after['moments'] == []
    # Enrichment finishing later neither re-joins nor replays the duplicate transcript.
    assert service.on_conversation_finalized(UID, 'c-wal', _wal_row(), trigger='sync_update', collaborators=c) == (
        'finalized'
    )
    replay = episodes_db.get_current_episode(UID, firestore_client=store)
    assert replay['conversation_ids'] == ['c-live', 'c-wal'] and model.calls == []
    # A replayed intake is a no-op on the same membership.
    assert service.attach_synced_intake(UID, 'c-wal', _wal_row(), collaborators=c) == 'attached'


def test_intake_attach_skips_discarded_rows_and_merge_donors():
    store = StrictFirestore()
    _attach(store, 'c-live', minutes=0)
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=2), store=store)
    for extra in ({'discarded': True}, {'deleted': True}, {'sync_merged_into': 'c-other'}):
        assert service.attach_synced_intake(UID, 'c-wal', _wal_row(**extra), collaborators=c) == 'skipped_discarded'
    assert episodes_db.get_current_episode(UID, firestore_client=store)['conversation_ids'] == ['c-live']


def test_a_sync_merge_donor_member_is_repointed_to_the_survivor_at_intake():
    store = StrictFirestore()
    _attach(store, 'c-live', minutes=0)
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=2), store=store)
    assert service.attach_synced_intake(UID, 'c-donor', _wal_row('c-donor'), collaborators=c) == 'joined'
    # A later segment folds the donor into the canonical row: the member follows the survivor.
    survivor = _wal_row('c-survivor', sync_merged_from=['c-donor'])
    assert service.attach_synced_intake(UID, 'c-survivor', survivor, collaborators=c) == 'attached'
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['conversation_ids'] == ['c-live', 'c-survivor']


def test_intake_attach_respects_the_gates_and_an_existing_episode_ownership(monkeypatch):
    store = StrictFirestore()
    _attach(store, 'c-live', minutes=0)
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=2), store=store)
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    assert service.attach_synced_intake(UID, 'c-wal', _wal_row(), collaborators=c) == 'disabled'
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV)
    monkeypatch.setattr(service.client_gate, 'client_seen_cached', lambda uid: False)
    assert service.attach_synced_intake(UID, 'c-wal', _wal_row(), collaborators=c) == 'skipped_no_client'
    assert episodes_db.get_current_episode(UID, firestore_client=store)['conversation_ids'] == ['c-live']
    monkeypatch.setattr(service.client_gate, 'client_seen_cached', lambda uid: True)
    # A member of the live episode never re-joins, and an episode owner never moves.
    assert service.attach_synced_intake(UID, 'c-live', _wal_row('c-live'), collaborators=c) == 'attached'
    assert service.close_on_finalize(UID, 'c-live', trigger='client_finalize', collaborators=c) == 'closed'
    assert service.attach_synced_intake(UID, 'c-live', _wal_row('c-live'), collaborators=c) == 'no_episode'
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store) is None


def test_intake_attach_with_no_live_episode_creates_nothing():
    store = StrictFirestore()
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=2), store=store)
    assert service.attach_synced_intake(UID, 'c-wal', _wal_row(), collaborators=c) == 'no_episode'
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store) is None


def test_a_clip_starting_slightly_before_the_episode_start_joins_within_the_continue_gap():
    store = StrictFirestore()
    # The pendant caught the opening words before the phone's stream recorded the start.
    _attach(store, 'c-live', minutes=1)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=2), store=store)
    # Span overlap: started before the episode, finished inside it.
    assert service.attach_synced_intake(UID, 'c-ov', _wal_row('c-ov', minutes=0.75), collaborators=c) == 'joined'
    # Clock skew: began a minute before the recorded start, ended half a minute before it.
    skew = _wal_row('c-skew', minutes=0)
    skew['finished_at'] = skew['started_at'] + timedelta(seconds=30)
    assert service.attach_synced_intake(UID, 'c-skew', skew, collaborators=c) == 'joined'
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['id'] == episode['id'] and after['conversation_ids'] == ['c-live', 'c-ov', 'c-skew']


def test_a_clip_that_ended_before_the_episode_stays_out_beyond_the_continue_gap():
    store = StrictFirestore()
    _attach(store, 'c-live', minutes=10)
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=11), store=store)
    assert service.attach_synced_intake(UID, 'c-old', _wal_row('c-old'), collaborators=c) == 'no_episode'
    assert episodes_db.get_episode_for_conversation(UID, 'c-old', firestore_client=store) is None
    after = episodes_db.get_current_episode(UID, firestore_client=store)
    assert after['id'] == episode['id'] and after['conversation_ids'] == ['c-live']


def test_an_intake_joined_clip_merged_away_follows_membership_to_the_survivor():
    store = StrictFirestore()
    _attach(store, 'survivor', minutes=0)
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=2), store=store)
    assert service.attach_synced_intake(UID, 'donor', _wal_row('donor'), collaborators=c) == 'joined'
    # Smart merge folds the donor away: the episode keeps standing for the survivor
    # only, and the deleted donor row can never render on Home.
    donor_row = {'id': 'donor', 'smart_merge': {'role': 'donor', 'survivor_id': 'survivor'}, 'finished_at': T0}
    assert (
        service.on_conversation_finalized(
            UID, 'survivor', donor_row, trigger='sync_update', absorbed_from='donor', collaborators=c
        )
        == 'finalized'
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode is not None and episode['conversation_ids'] == ['survivor']
    assert episodes_db.get_episode_for_conversation(UID, 'survivor', firestore_client=store)['id'] == episode['id']


# ---------------------------------------------------------------- silence-closed rejoin


def _close_on_gap(store, conversation_id='c-live', *, at_minutes=20):
    """The server ends the phone's occasion conversation on silence: the episode closes on gap."""
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=at_minutes), store=store)
    assert (
        service.close_on_finalize(UID, conversation_id, trigger='server_recovery', source='omi', collaborators=c)
        == 'closed'
    )


def test_a_late_sync_clip_rejoins_the_gap_closed_episode_and_reopens_it():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    _close_on_gap(store)
    # The pendant's WAL clip finalized moments after the close, its span inside the
    # closed episode: it rejoins and reopens the most recent episode.
    c = _collaborators(model, now=T0 + timedelta(minutes=21), store=store)
    assert (
        service.on_conversation_finalized(UID, 'c-wal', _wal_row(minutes=15), trigger='sync_update', collaborators=c)
        == 'rejoined'
    )
    reopened = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert reopened['status'] == 'live' and reopened['close_reason'] is None and reopened['closed_at'] is None
    assert reopened['conversation_ids'] == ['c-live', 'c-wal']
    assert episodes_db.get_current_episode(UID, firestore_client=store)['id'] == episode['id']
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store)['id'] == episode['id']
    # A parallel capture still feeds no text, spends nothing, and its speech is activity.
    assert len(model.calls) == 1 and reopened['applied'].keys() == {'c-live'}
    assert reopened['last_activity_at'] == _wal_row(minutes=15)['finished_at']
    # The recap no longer advertises the reopened episode as the last closed one.
    assert episodes_db.get_last_closed_episode(UID, firestore_client=store) is None


def test_a_late_sync_clip_starting_within_the_continue_gap_of_the_close_rejoins():
    store = StrictFirestore()
    service.record_moment(
        UID, _moment('c-live'), _collaborators(FakeModel(), now=T0 + timedelta(minutes=1), store=store)
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    _close_on_gap(store)
    c = _collaborators(FakeModel(), now=T0 + timedelta(minutes=21), store=store)
    # Started a minute after the closed episode's end, inside CONTINUE_GAP_SECONDS.
    assert (
        service.on_conversation_finalized(
            UID, 'c-next', _wal_row('c-next', minutes=21), trigger='sync_update', collaborators=c
        )
        == 'rejoined'
    )
    reopened = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert reopened['status'] == 'live' and 'c-next' in reopened['conversation_ids']
    # The pause beyond the continue gap is a different occasion: the clip stands alone.
    assert (
        service.on_conversation_finalized(
            UID, 'c-after', _wal_row('c-after', minutes=24), trigger='sync_update', collaborators=c
        )
        == 'no_episode'
    )
    assert episodes_db.get_episode_for_conversation(UID, 'c-after', firestore_client=store) is None
    assert episodes_db.get_current_episode(UID, firestore_client=store)['id'] == episode['id']


def test_a_late_sync_clip_attaches_to_the_gap_closed_episode_without_reopening_when_newer_speech_exists():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    first = episodes_db.get_current_episode(UID, firestore_client=store)
    _close_on_gap(store)
    # New live words open the next episode; the occasion moved on.
    _attach(store, 'c-new', minutes=45)
    newer = episodes_db.get_current_episode(UID, firestore_client=store)
    assert newer['id'] != first['id']
    # The WAL clip belongs to the closed occasion: a member of it, never a reopen.
    c = _collaborators(model, now=T0 + timedelta(minutes=46), store=store)
    assert (
        service.on_conversation_finalized(UID, 'c-wal', _wal_row(minutes=15), trigger='sync_update', collaborators=c)
        == 'rejoined_member'
    )
    closed = episodes_db.get_episode(UID, first['id'], firestore_client=store)
    assert closed['status'] == 'closed' and closed['close_reason'] == 'gap'
    assert closed['conversation_ids'] == ['c-live', 'c-wal']
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store)['id'] == first['id']
    assert episodes_db.get_current_episode(UID, firestore_client=store)['id'] == newer['id']
    assert 'c-wal' not in episodes_db.get_current_episode(UID, firestore_client=store)['conversation_ids']


def test_a_user_wrap_up_or_boundary_close_is_never_rejoined_by_a_late_sync_clip():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    c = _collaborators(model, now=T0 + timedelta(minutes=3), store=store)
    assert service.wrap_up(UID, episode['id'], conversation_id='c-live', collaborators=c)['status'] == 'closed'
    assert (
        service.on_conversation_finalized(UID, 'c-wal', _wal_row(minutes=0.5), trigger='sync_update', collaborators=c)
        == 'no_episode'
    )
    assert episodes_db.get_episode_for_conversation(UID, 'c-wal', firestore_client=store) is None
    assert episodes_db.get_episode(UID, episode['id'], firestore_client=store)['conversation_ids'] == ['c-live']

    # A hard boundary (a meeting window edge) is just as final.
    service.record_moment(UID, _moment('c-live2'), _collaborators(model, now=T0 + timedelta(minutes=10), store=store))
    bounded = episodes_db.get_current_episode(UID, firestore_client=store)
    episodes_db.close_episode(
        UID, bounded['id'], 'boundary', closed_at=T0 + timedelta(minutes=11), firestore_client=store
    )
    assert (
        service.on_conversation_finalized(
            UID, 'c-wal2', _wal_row('c-wal2', minutes=10.5), trigger='sync_update', collaborators=c
        )
        == 'no_episode'
    )
    assert episodes_db.get_episode(UID, bounded['id'], firestore_client=store)['conversation_ids'] == ['c-live2']


def test_sync_speech_extends_the_live_episodes_activity_and_defers_the_idle_close():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    # A pendant clip joins at intake nine minutes after the live stream's last moment.
    clip = _wal_row(minutes=0.5)
    clip['finished_at'] = clip['started_at'] + timedelta(minutes=9)
    c = _collaborators(model, now=T0 + timedelta(minutes=10), store=store)
    assert service.attach_synced_intake(UID, 'c-wal', clip, collaborators=c) == 'joined'
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    assert episode['last_activity_at'] == clip['finished_at']
    # Thirty minutes past the live moment, the idle close does not fire: the
    # occasion's latest speech is the sync clip's end, twenty-one minutes back.
    later = _collaborators(model, now=T0 + timedelta(minutes=31), store=store)
    still_live = service.live_episode(UID, collaborators=later)
    assert still_live is not None and still_live['id'] == episode['id']
    # The close measures from the sync activity too: at thirty minutes past it, idle fires.
    idle = _collaborators(model, now=T0 + timedelta(minutes=40), store=store)
    closed = service.live_episode(UID, collaborators=idle)
    assert closed is None
    finished = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert finished['close_reason'] == 'idle' and finished['conversation_ids'] == ['c-live', 'c-wal']


def test_a_backfilled_sync_clip_attaches_to_the_closed_episode_without_reopening_it():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    _close_on_gap(store)
    # The same clip, delivered hours later: its speech is older than the close gap,
    # so it joins as a member and the episode stays closed (no "Listening now" flash).
    c = _collaborators(model, now=T0 + timedelta(hours=3), store=store)
    service.on_conversation_finalized(UID, 'c-wal', _wal_row(minutes=15), trigger='sync_update', collaborators=c)
    after = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert after['status'] == 'closed' and 'c-wal' in after['conversation_ids']
    assert episodes_db.get_current_episode(UID, firestore_client=store) is None


def test_a_pendant_clock_running_ahead_never_pins_the_episode_open():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(UID, _moment('c-live'), _collaborators(model, now=T0 + timedelta(minutes=1), store=store))
    clip = _wal_row(minutes=0.5)
    clip['finished_at'] = T0 + timedelta(minutes=22)  # pendant clock ~20 min ahead
    now = T0 + timedelta(minutes=2)
    assert (
        service.attach_synced_intake(UID, 'c-wal', clip, collaborators=_collaborators(model, now=now, store=store))
        == 'joined'
    )
    assert episodes_db.get_current_episode(UID, firestore_client=store)['last_activity_at'] == now


def test_late_sync_audio_from_before_the_closed_episode_stays_out():
    store = StrictFirestore()
    model = FakeModel({'title': 'Lunch', 'bullets': ['A']})
    service.record_moment(
        UID, _moment('c-live', minutes=8), _collaborators(model, now=T0 + timedelta(minutes=10), store=store)
    )
    episode = episodes_db.get_current_episode(UID, firestore_client=store)
    _close_on_gap(store, at_minutes=30)
    c = _collaborators(model, now=T0 + timedelta(minutes=31), store=store)
    # The clip's span ended long before the episode's first recorded words.
    old = _wal_row(minutes=5)
    old['finished_at'] = old['started_at'] + timedelta(seconds=30)
    assert service.on_conversation_finalized(UID, 'c-old', old, trigger='sync_update', collaborators=c) == 'no_episode'
    assert episodes_db.get_episode_for_conversation(UID, 'c-old', firestore_client=store) is None
    closed = episodes_db.get_episode(UID, episode['id'], firestore_client=store)
    assert closed['conversation_ids'] == ['c-live'] and closed['status'] == 'closed'
