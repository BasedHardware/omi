"""Closed-episode composer: one whole-episode summary once every member is done."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from config import episodes as config
from utils.episodes import composer, service

UID = 'composer-uid'
T0 = datetime(2026, 10, 30, 7, 56, tzinfo=timezone.utc)  # 14:56 in Asia/Bangkok


def _row(cid, start, minutes, *, status='completed', title='T', overview='O', lines=None):
    lines = lines if lines is not None else [(0, 'We planned the launch.'), (60 * minutes - 30, 'Done.')]
    return {
        'id': cid,
        'status': status,
        'started_at': start,
        'finished_at': start + timedelta(minutes=minutes),
        'recorded_start': start,
        'recorded_end': start + timedelta(minutes=minutes),
        'structured': {'title': title, 'overview': overview, 'action_items': [{'description': 'Ship it'}]},
        'transcript_segments': [
            {'start': s, 'end': s + 5, 'text': t, 'is_user': i % 2 == 0, 'speaker': 'SPEAKER_01'}
            for i, (s, t) in enumerate(lines)
        ],
    }


class Store:
    def __init__(self, episode, rows):
        self.episode = dict(episode)
        self.rows = {r['id']: r for r in rows}
        self.writes = []

    def get_episode(self, uid, episode_id, firestore_client=None):
        return dict(self.episode)

    def update_episode(self, uid, episode_id, *, expected_version, updates, firestore_client=None, **_):
        assert expected_version == self.episode['state_version']
        self.writes.append(dict(updates))
        self.episode.update(updates)
        self.episode['state_version'] += 1
        return self.episode

    def get_conversation(self, uid, cid, firestore_client=None, **_):
        row = self.rows.get(cid)
        return dict(row) if row else None


def _episode(**over):
    base = {
        'id': 'ep1',
        'status': 'closed',
        'started_at': T0,
        'closed_at': T0 + timedelta(hours=3, minutes=10),
        'conversation_ids': ['c1', 'c2'],
        'discarded_conversation_ids': [],
        'state_version': 5,
        'title': 'old',
        'bullets': ['David: Yeah.'],
        'moments': [],
        'usage': {'calls': 132},
    }
    base.update(over)
    return base


def _reply(**over):
    data = {
        'title': 'Omi app bugs and labeling tool',
        'emoji': '🛠️',
        'overview': 'David found two app regressions.\n\nHe explained the labeling tool.',
        'chapters': [
            {'start': '15:38', 'end': '15:39', 'title': 'Labeling tool', 'summary': 'Tool explained.'},
            {'start': '15:00', 'end': '15:01', 'title': 'App regressions', 'summary': 'Two bugs.'},
            {'start': '15:10', 'end': '15:11', 'title': 'New moment detected', 'summary': 'noise'},
            {'start': '03:00', 'end': '03:05', 'title': 'Far outside', 'summary': 'x'},
            {'start': '17:58', 'end': '18:01', 'title': 'Working at Muji', 'summary': 'Calm.'},
        ],
        'people': ['Arjan'],
    }
    data.update(over)
    return SimpleNamespace(content=json.dumps(data), usage_metadata={'input_tokens': 8000, 'output_tokens': 500})


@pytest.fixture
def store(monkeypatch):
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    rows = [_row('c1', T0, 180), _row('c2', T0 + timedelta(minutes=181), 8)]
    s = Store(_episode(), rows)
    monkeypatch.setattr(composer.episodes_db, 'get_episode', s.get_episode)
    monkeypatch.setattr(composer.episodes_db, 'update_episode', s.update_episode)
    monkeypatch.setattr(composer.conversations_db, 'get_conversation', s.get_conversation)
    return s


def _c(invoke=None, calls=None):
    def default(uid, messages):
        if calls is not None:
            calls.append(messages)
        return _reply()

    return service.Collaborators(
        tz_name='Asia/Bangkok',
        owner_name=lambda uid: 'David',
        people_names=lambda uid, ids: {},
        extras={'compose_invoke': invoke or default},
    )


def test_composes_a_closed_episode_into_summary_and_real_chapters(store):
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    written = store.writes[-1]
    assert written['title'] == 'Omi app bugs and labeling tool'
    assert written['bullets'] == ['David found two app regressions.', 'He explained the labeling tool.']
    headings = [m['heading'] for m in written['moments']]
    # Placeholder and out-of-span chapters are dropped; the rest are in time order.
    assert headings == ['App regressions', 'Labeling tool', 'Working at Muji']
    first = written['moments'][0]
    assert first['started_at'] == datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)
    assert first['conversation_id'] == 'c1'
    assert written['moments'][-1]['conversation_id'] == 'c2'
    assert written['summary_needs_regeneration'] is False
    assert written['composed_fingerprint']
    assert written['usage']['calls'] == 132 and written['usage']['composer_calls'] == 1
    # The late member's end moves the episode's activity forward (the 1h46m lunch bug).
    assert written['member_activity']['c2'] == T0 + timedelta(minutes=189)
    system, human = calls[0]
    assert 'David' in system[1] and 'Existing summary: O' in human[1] and '[14:56] David: We planned' in human[1]


def test_waits_for_members_still_processing(store):
    store.rows['c2']['status'] = 'processing'
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    assert store.writes == []


def test_live_episode_is_left_to_the_live_notes(store):
    store.episode['status'] = 'live'
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'live'


def test_unchanged_evidence_does_not_spend_a_second_call(store):
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'unchanged'
    assert len(calls) == 1
    # A sync upgrade of a member transcript changes the fingerprint and recomposes.
    store.rows['c2']['transcript_segments'].append({'start': 600, 'end': 610, 'text': 'More words.', 'is_user': True})
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 2


def test_a_later_per_moment_write_over_composed_notes_is_recomposed(store):
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    store.episode['bullets'] = ['David: Yeah.']  # a closing tail or sync replay after the compose
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 2 and store.episode['bullets'][0].startswith('David found')


def test_discarded_and_hidden_members_are_excluded(store):
    store.episode['discarded_conversation_ids'] = ['c2']
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert 'Recording 2' not in calls[0][1][1]
    store.episode['discarded_conversation_ids'] = []
    store.rows['c2']['deleted'] = True
    calls.clear()
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls), force=True) == 'composed'
    assert 'Recording 2' not in calls[0][1][1]


def test_kill_switch_off_does_nothing(store, monkeypatch):
    monkeypatch.setenv(config.EPISODE_COMPOSER_ENV, 'false')
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'disabled'
    assert composer.schedule(UID, 'ep1') is False
    assert store.writes == []


def test_model_failure_never_raises_and_backs_off_on_the_same_evidence(store):
    calls = []

    def boom(uid, messages):
        calls.append(1)
        raise TimeoutError('slow')

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=boom)) == 'error'
    # The same evidence is not retried inside the backoff, from any trigger.
    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=boom)) == 'backoff'
    assert calls == [1]
    assert not any('bullets' in w for w in store.writes)
    assert store.episode['compose_failures'] == 1 and store.episode['compose_lease'] is None
    assert composer.needs_compose(store.episode) is False
    # After the cap, the same evidence stops for good.
    store.episode.update(compose_failures=4, compose_failed_at=T0)
    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=boom)) == 'backoff'
    # New evidence (a sync upgrade) is a fresh attempt, and succeeds.
    store.rows['c1']['transcript_segments'].append({'start': 900, 'end': 905, 'text': 'More.', 'is_user': True})
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed'
    assert store.episode['compose_failures'] == 0


def test_a_visible_change_after_capped_failures_still_recomposes(store):
    done = {
        'status': 'closed',
        'started_at': T0,
        'composed_fingerprint': 'x',
        'composed_member_ids': ['c1', 'c2'],
        'title': 'T',
        'bullets': ['b'],
        'compose_failures': 4,
        'compose_failed_at': datetime.now(timezone.utc),
    }
    done['composed_notes'] = composer.notes_hash(done)
    assert composer.needs_compose(done, visible_member_ids=['c1', 'c2']) is False
    # A member discarded directly on its conversation must not stay in the summary.
    assert composer.needs_compose(done, visible_member_ids=['c1']) is True


def test_empty_after_a_discard_clears_the_old_notes(store):
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed'
    store.rows['c1']['discarded'] = True
    store.rows['c2']['transcript_segments'] = []
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'empty'
    assert store.episode['title'] == '' and store.episode['bullets'] == [] and store.episode['moments'] == []
    assert composer.needs_compose(store.episode, visible_member_ids=['c2']) is False


def test_a_superseded_run_keeps_a_newer_lease(store):
    newer = {'fingerprint': 'newer-evidence', 'until': datetime.now(timezone.utc) + timedelta(minutes=2)}

    def invoke(uid, messages):
        store.rows['c2']['transcript_segments'].append({'start': 700, 'end': 705, 'text': 'Late.', 'is_user': True})
        store.episode['compose_lease'] = newer  # another replica claimed the new evidence
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'superseded'
    assert store.episode['compose_lease'] == newer


def test_person_rename_recomposes(store):
    calls = []
    names = {'p1': 'Arjan'}
    store.rows['c1']['transcript_segments'][1]['person_id'] = 'p1'

    def c():
        col = _c(calls=calls)
        col.people_names = lambda uid, ids: {i: names[i] for i in ids if i in names}
        return col

    assert composer.compose(UID, 'ep1', collaborators=c()) == 'composed'
    assert composer.compose(UID, 'ep1', collaborators=c()) == 'unchanged'
    names['p1'] = 'Arjan V.'
    assert composer.compose(UID, 'ep1', collaborators=c()) == 'composed'
    assert len(calls) == 2


def test_speaker_correction_recomposes(store):
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    store.rows['c1']['transcript_segments'][1]['person_id'] = 'person-arjan'
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 2


def test_a_trigger_during_a_run_composes_again(store, monkeypatch):
    outcomes = iter(['composed', 'unchanged'])
    seen = []

    def fake_compose(uid, episode_id, collaborators=None, force=False):
        seen.append(episode_id)
        if len(seen) == 1:
            # A member finalize arrives while this run is in flight.
            assert composer.schedule(uid, episode_id) is False
        return next(outcomes)

    monkeypatch.setattr(composer, 'compose', fake_compose)
    monkeypatch.setattr(composer._executor, 'submit', lambda fn: fn())
    assert composer.schedule(UID, 'ep1') is True
    assert seen == ['ep1', 'ep1']


def test_membership_change_during_the_call_is_not_overwritten(store):
    def invoke(uid, messages):
        store.episode['conversation_ids'] = ['c1', 'c2', 'c3']
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'superseded'
    assert not any("bullets" in w for w in store.writes) and store.episode["compose_lease"] is None


def test_long_transcripts_keep_the_densest_windows_in_order():
    tz = ZoneInfo('UTC')
    lines = []
    for minute in range(0, 240, 2):
        text = ('busy ' * 40) if 60 <= minute < 80 else 'hm'
        lines.append((T0 + timedelta(minutes=minute), f'[{minute}] {text}'))
    kept = composer._fit(lines, budget=3000)
    assert any('quieter minutes left out' in line for line in kept)
    busy = [line for line in kept if 'busy' in line]
    assert busy and busy == sorted(busy, key=lambda l: int(l[1:].split(']')[0]))
    assert sum(len(l) + 1 for l in kept if 'left out' not in l) <= 3000


def test_needs_compose_read_check(monkeypatch):
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    assert composer.needs_compose({'status': 'closed', 'started_at': T0}) is True
    done = {'status': 'closed', 'started_at': T0, 'composed_fingerprint': 'x', 'title': 'T', 'bullets': ['b']}
    done['composed_notes'] = composer.notes_hash(done)
    assert composer.needs_compose(done) is False
    assert composer.needs_compose({**done, 'summary_needs_regeneration': True}) is True
    # A later per-moment write over composed notes is drift: compose again.
    assert composer.needs_compose({**done, 'bullets': ['David: Yeah.']}) is True
    assert composer.needs_compose({'status': 'live', 'started_at': T0}) is False


def test_home_read_safety_net_schedules_uncomposed_and_changed_episodes(monkeypatch):
    from utils.episodes import home_read

    queued = []
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    monkeypatch.setattr(composer, 'schedule', lambda uid, eid, **_: queued.append(eid) or True)
    now = datetime.now(timezone.utc)
    old = now - timedelta(minutes=5)
    done = {'status': 'closed', 'started_at': now, 'closed_at': old, 'composed_fingerprint': 'x'}
    done['composed_notes'] = composer.notes_hash(done)
    rows = [
        {'id': 'fresh', 'status': 'closed', 'started_at': now, 'closed_at': now},
        {'id': 'old1', 'status': 'closed', 'started_at': now, 'closed_at': old},
        {**done, 'id': 'done', 'composed_member_ids': ['a']},
        # A member discarded directly on its conversation after the compose.
        {**done, 'id': 'shrunk', 'composed_member_ids': ['a', 'b']},
        {'id': 'old3', 'status': 'closed', 'started_at': now, 'closed_at': old},
        {'id': 'live', 'status': 'live', 'started_at': now},
    ]
    wires = [{'id': r['id'], 'members': [{'id': 'a'}]} for r in rows]
    home_read.schedule_missed_composes(UID, rows, wires)
    assert queued == ['old1', 'shrunk']


def test_per_conversation_lookup_carries_the_safety_net(monkeypatch):
    # Home reads episodes through /by-conversation, not only the window list: the lookup schedules too.
    from utils.episodes import home_read

    queued = []
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    monkeypatch.setattr(home_read, '_lookup_spend', {})
    monkeypatch.setattr(composer, 'schedule', lambda uid, eid, **_: queued.append(eid) or True)
    old = datetime.now(timezone.utc) - timedelta(minutes=5)
    visible = {'e1', 'e2', 'e3', 'e4', 'e5', 'e6'}
    monkeypatch.setattr(
        home_read,
        'project_episode',
        lambda uid, ep: ep and ep['id'] in visible and {'id': ep['id'], 'members': [{'id': 'a'}]} or None,
    )

    def ep(eid):
        return {'id': eid, 'status': 'closed', 'started_at': old, 'closed_at': old}

    assert home_read.project_lookup(UID, ep('e1')) == {'id': 'e1', 'members': [{'id': 'a'}]}
    assert home_read.project_lookup(UID, None) is None
    # A fully hidden episode projects to nothing but is still checked, so stale notes get cleared.
    assert home_read.project_lookup(UID, ep('hidden')) is None
    assert queued == ['e1', 'hidden']
    # Lookups arrive once per Home row: distinct episodes queued across them are capped per user.
    for eid in ['e2', 'e3', 'e4', 'e5', 'e6']:
        home_read.project_lookup(UID, ep(eid))
    assert queued == ['e1', 'hidden', 'e2', 'e3']
    home_read.project_lookup('someone-else', ep('e6'))
    assert queued[-1] == 'e6'


def test_a_second_replica_does_not_pay_for_the_same_evidence(store):
    calls = []

    def invoke(uid, messages):
        calls.append(1)
        # Another replica starts while this call is in flight: the lease stops it before any spend.
        assert (
            composer.compose(UID, 'ep1', collaborators=_c(invoke=lambda u, m: calls.append(2) or _reply())) == 'leased'
        )
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'composed'
    assert calls == [1] and store.episode['compose_lease'] is None


def test_discard_during_the_call_is_superseded_not_written(store):
    def invoke(uid, messages):
        store.rows['c2']['discarded'] = True
        return _reply()

    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=invoke)) == 'superseded'
    assert not any('bullets' in w for w in store.writes)
    assert store.episode['compose_lease'] is None


def test_same_shape_transcript_edit_recomposes(store):
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    store.rows['c1']['transcript_segments'][0]['text'] = 'We cancelled the launch.'
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 2


def test_chapters_just_outside_the_episode_are_dropped(store):
    reply = _reply(
        chapters=[
            {'start': '14:20', 'end': '14:30', 'title': 'Before it began', 'summary': 'x'},
            {'start': '15:00', 'end': '15:05', 'title': 'Inside', 'summary': 'y'},
        ]
    )
    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=lambda u, m: reply)) == 'composed'
    assert [m['heading'] for m in store.writes[-1]['moments']] == ['Inside']


def test_episode_with_no_speech_is_stamped_once(store):
    for row in store.rows.values():
        row['transcript_segments'] = []
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'empty'
    assert calls == [] and store.episode['composed_fingerprint']
    assert composer.needs_compose(store.episode, visible_member_ids=['c1', 'c2']) is False


def test_long_paragraphs_survive_the_wire():
    from utils.episodes import service as svc

    paragraph = 'word ' * 200
    updates = composer.to_updates(
        {'title': 't', 'overview': paragraph, 'chapters': []},
        [_row('c1', T0, 10)],
        ZoneInfo('UTC'),
    )
    wire = svc.to_wire({'id': 'e', 'status': 'closed', 'started_at': T0, 'last_activity_at': T0, **updates})
    assert wire['bullets'][0] == paragraph.strip()
