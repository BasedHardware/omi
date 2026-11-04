"""Closed-episode composer: one whole-episode summary once every member is done."""

from __future__ import annotations

import asyncio
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
from utils.episodes import composer, home_read, metrics, service

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
        'lede': 'David found two app regressions and explained the labeling tool.',
        'chapters': [
            {
                'start': '15:38:10',
                'title': 'Labeling tool',
                'points': [
                    {'text': 'Order is random by default.', 'details': ['Open source, so strategies can be added.']}
                ],
            },
            {
                'start': '15:00:00',
                'end': '15:04:30',
                'title': 'App regressions',
                'points': [
                    {'text': 'Ending an episode no longer shows the processing row.', 'details': []},
                    '• The live transcript is missing from the Home row.',
                    {'text': '   '},
                ],
            },
            {'start': '15:10', 'end': '15:11', 'title': 'New moment detected', 'summary': 'noise'},
            {'start': '03:00', 'end': '03:05', 'title': 'Far outside', 'summary': 'x'},
            {'start': '17:58', 'end': '18:01', 'title': 'Working at Muji', 'summary': 'Calm.'},
        ],
        'people': ['Arjan'],
        'follow_ups': ['Fix the processing row', ''],
    }
    data.update(over)
    return SimpleNamespace(content=json.dumps(data), usage_metadata={'input_tokens': 8000, 'output_tokens': 500})


@pytest.fixture
def store(monkeypatch):
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    monkeypatch.delenv(config.EPISODE_COMPOSE_SETTLE_ENABLED_ENV, raising=False)
    monkeypatch.setattr(composer, '_deferred', {})
    monkeypatch.setattr(composer, '_foreground', set())
    monkeypatch.setattr(composer, '_recent', {})
    monkeypatch.setattr(composer, '_inflight', set())
    monkeypatch.setattr(composer, '_rerun', set())
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
    lede = 'David found two app regressions and explained the labeling tool.'
    assert written['lede'] == lede and written['bullets'] == [lede]
    assert written['follow_ups'] == ['Fix the processing row']
    headings = [m['heading'] for m in written['moments']]
    # Placeholder and out-of-span chapters are dropped; the rest are in time order.
    assert headings == ['App regressions', 'Labeling tool', 'Working at Muji']
    first, tool, muji = written['moments']
    assert first['started_at'] == datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)
    assert first['conversation_id'] == 'c1'
    # Second-precision times: a chapter's length is real, not padded to a minute.
    assert first['ended_at'] - first['started_at'] == timedelta(minutes=4, seconds=30)
    assert (first['start_offset'], first['end_offset']) == (240.0, 510.0)
    assert first['points'] == [
        {'text': 'Ending an episode no longer shows the processing row.', 'details': []},
        {'text': 'The live transcript is missing from the Home row.', 'details': []},
    ]
    assert tool['points'][0]['details'] == ['Open source, so strategies can be added.']
    # No end from the model: the chapter runs to its recording's last line before the next chapter.
    assert tool['ended_at'] == T0 + timedelta(minutes=180) - timedelta(seconds=30)
    # The old one-sentence summary still becomes a point.
    assert muji['points'] == [{'text': 'Calm.', 'details': []}]
    assert written['moments'][-1]['conversation_id'] == 'c2'
    assert written['summary_needs_regeneration'] is False
    assert written['composed_fingerprint']
    assert written['usage']['calls'] == 132 and written['usage']['composer_calls'] == 1
    # The late member's end moves the episode's activity forward (the 1h46m lunch bug).
    assert written['member_activity']['c2'] == T0 + timedelta(minutes=189)
    system, human = calls[0]
    assert 'David' in system[1] and 'Existing summary: O' in human[1] and '[14:56:00] David: We planned' in human[1]


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


def test_a_refused_window_change_keeps_the_paid_notes_on_the_old_window(store, monkeypatch):
    calls = []
    update = store.update_episode

    def refuse_window(uid, episode_id, *, updates, **kw):
        if 'member_activity' in updates:
            raise composer.episodes_db.EpisodeConflict('recorded_window_overlap')
        return update(uid, episode_id, updates=updates, **kw)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', refuse_window)
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert store.episode['title'] == 'Omi app bugs and labeling tool' and 'member_activity' not in store.episode
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'unchanged'
    assert len(calls) == 1


def test_a_final_write_that_keeps_conflicting_backs_off_instead_of_paying_again(store, monkeypatch):
    calls = []
    update = store.update_episode

    def refuse_notes(uid, episode_id, *, updates, **kw):
        if 'bullets' in updates:
            raise composer.episodes_db.EpisodeConflict('conversation_already_owned')
        return update(uid, episode_id, updates=updates, **kw)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', refuse_notes)
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'conflict'
    assert store.episode['compose_failures'] == 1 and store.episode['compose_lease'] is None
    assert composer.needs_compose(store.episode) is False
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'backoff'
    assert len(calls) == 1


def test_a_sustained_version_race_keeps_activity_and_backs_off(store, monkeypatch):
    calls = []
    update = store.update_episode

    def race(uid, episode_id, *, updates, **kw):
        if 'bullets' in updates:
            assert 'member_activity' in updates
            raise composer.episodes_db.EpisodeConflict('state_version_changed')
        return update(uid, episode_id, updates=updates, **kw)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', race)
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'conflict'
    assert store.episode['compose_failures'] == 1 and len(calls) == 1


def test_a_visible_change_after_capped_failures_still_recomposes(store):
    done = {
        'status': 'closed',
        'started_at': T0,
        'composed_fingerprint': 'x',
        'composer_version': config.COMPOSER_VERSION,
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


def test_unresolved_speaker_id_drift_does_not_recompose(store):
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    store.rows['c1']['transcript_segments'][1]['person_id'] = 'person-arjan'
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'unchanged'
    assert len(calls) == 1


def test_a_trigger_during_a_run_composes_again(store, monkeypatch):
    outcomes = iter(['composed', 'unchanged'])
    seen = []

    def fake_compose(uid, episode_id, collaborators=None, force=False, background=False):
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
    done = {
        'status': 'closed',
        'started_at': T0,
        'composed_fingerprint': 'x',
        'composer_version': config.COMPOSER_VERSION,
        'title': 'T',
        'bullets': ['b'],
    }
    done['composed_notes'] = composer.notes_hash(done)
    assert composer.needs_compose(done) is False
    assert composer.needs_compose({**done, 'summary_needs_regeneration': True}) is True
    # A later per-moment write over composed notes is drift: compose again.
    assert composer.needs_compose({**done, 'bullets': ['David: Yeah.']}) is True
    assert composer.needs_compose({'status': 'live', 'started_at': T0}) is False
    # A new composer recomposes episodes the old one wrote, once.
    assert composer.needs_compose({**done, 'composer_version': 'episode_composer_v1'}) is True


def test_home_read_safety_net_schedules_uncomposed_and_changed_episodes(monkeypatch):

    queued = []
    monkeypatch.delenv(config.EPISODE_COMPOSER_ENV, raising=False)
    monkeypatch.setattr(composer, 'schedule', lambda uid, eid, **_: queued.append(eid) or True)
    now = datetime.now(timezone.utc)
    old = now - timedelta(minutes=5)
    done = {
        'status': 'closed',
        'started_at': now,
        'closed_at': old,
        'composed_fingerprint': 'x',
        'composer_version': config.COMPOSER_VERSION,
    }
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
    assert wire['bullets'][0] == paragraph.strip() and wire['lede'] == paragraph.strip()


def test_composed_sections_reach_the_wire_and_validate():
    from models.episode import Episode
    from utils.episodes import service as svc

    chapter = {
        'start': '00:01:00',
        'end': '00:04:00',
        'title': 'Plan',
        'points': [{'text': 'Ship Friday', 'details': ['QA first']}],
    }
    updates = composer.to_updates(
        {'title': 't', 'lede': 'A plan.', 'chapters': [chapter], 'follow_ups': ['Book QA']},
        [_row('c1', T0.replace(hour=0, minute=0), 10)],
        ZoneInfo('UTC'),
    )
    stored = {'id': 'e', 'status': 'closed', 'started_at': T0, 'last_activity_at': T0, **updates}
    stored['moments'][0]['points'].append({'text': '', 'details': ['dropped']})
    wire = svc.to_wire(stored)
    assert wire['lede'] == 'A plan.' and wire['follow_ups'] == ['Book QA']
    assert wire['moments'][0]['points'] == [{'text': 'Ship Friday', 'details': ['QA first']}]
    assert wire['moments'][0]['start_offset'] == 60.0
    assert Episode.model_validate(wire).moments[0].points[0].details == ['QA first']


@pytest.mark.parametrize(
    'reply',
    [
        {'chapters': 'not a list'},
        {'chapters': [{'start': '15:00:00', 'title': 'x', 'points': 'oops'}, 'junk'], 'follow_ups': 'none'},
        {'chapters': []},
    ],
)
def test_malformed_or_sectionless_output_is_a_backed_off_failure(store, reply):
    assert composer.compose(UID, 'ep1', collaborators=_c(invoke=lambda u, m: _reply(**reply))) == 'error'
    assert store.episode['compose_failures'] == 1 and store.episode['compose_lease'] is None
    assert not any('lede' in w for w in store.writes)


def test_a_chapter_running_into_the_next_recording_stays_inside_its_own():
    a, b = _row('c1', T0, 10), _row('c2', T0 + timedelta(minutes=10), 10)
    chapter = {'start': '14:56:00', 'end': '15:15:00', 'title': 'Long', 'points': ['p']}
    moment = composer.to_updates({'title': 't', 'lede': 'l', 'chapters': [chapter]}, [a, b], ZoneInfo('Asia/Bangkok'))[
        'moments'
    ][0]
    assert moment['conversation_id'] == 'c1'
    # Ends where c1's last segment ends (570 s + 5 s), so the transcript offset stays inside c1.
    assert moment['end_offset'] == 575.0

    def offsets(start, end):
        near = {**chapter, 'start': start, 'end': end}
        m = composer.to_updates({'title': 't', 'lede': 'l', 'chapters': [near]}, [a], ZoneInfo('Asia/Bangkok'))
        return m['moments'][0]['start_offset'], m['moments'][0]['end_offset']

    # Past the last segment, start and end are both held to it, never pushed beyond.
    assert offsets('14:56:00', '15:06:00') == (0.0, 575.0)
    assert offsets('15:05:40', '15:05:45') == (575.0, 575.0)


def test_a_failed_version_recompose_backs_off():
    stale = {
        'status': 'closed',
        'started_at': T0,
        'composed_fingerprint': 'x',
        'composer_version': 'episode_composer_v1',
        'compose_failures': 4,
        'compose_failed_at': datetime.now(timezone.utc),
    }
    assert composer.needs_compose(stale) is False


def test_discarding_a_member_clears_the_composed_lede_and_follow_ups():
    from database import episodes as episodes_db

    raw = {
        'started_at': T0,
        'conversation_ids': ['c1', 'c2'],
        'discarded_conversation_ids': [],
        'lede': 'L',
        'follow_ups': ['F'],
    }
    merged = episodes_db._merge_state(raw, {'discarded_conversation_ids': ['c2']})
    assert merged['lede'] == '' and merged['follow_ups'] == [] and merged['summary_needs_regeneration'] is True
    # Both discard paths share one cleared set, so a new note field cannot be missed again.
    cleared = episodes_db._cleared_notes()
    assert set(cleared) == set(episodes_db.CONTENT_FIELDS) - {'moments', 'provisional_items'} | {
        'summary_needs_regeneration'
    }


def _turn_row(*segments):
    started = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    return {
        'started_at': started,
        'transcript_segments': [
            {'start': start, 'end': end, 'text': text, 'speaker': speaker, 'is_user': False}
            for start, end, speaker, text in segments
        ],
    }


def test_transcript_lines_join_fragments_of_one_turn():
    row = _turn_row(
        (0, 5, 'SPEAKER_00', 'one'),
        (5, 10, 'SPEAKER_00', 'two'),
        (10, 15, 'SPEAKER_01', 'three'),
        (15, 20, 'SPEAKER_00', 'four'),
    )
    lines = composer.transcript_lines(row, 'Me', ZoneInfo('UTC'))
    assert [text for _, text in lines] == [
        '[12:00:00] Speaker 00: one two',
        '[12:00:10] Speaker 01: three',
        '[12:00:15] Speaker 00: four',
    ]


def test_transcript_lines_restart_after_a_pause_and_inside_a_monologue():
    row = _turn_row(
        *[(i * 10, i * 10 + 10, 'SPEAKER_00', f'w{i}') for i in range(8)], (200, 205, 'SPEAKER_00', 'later')
    )
    lines = composer.transcript_lines(row, 'Me', ZoneInfo('UTC'))
    assert [text.split(': ')[0] for _, text in lines] == [
        '[12:00:00] Speaker 00',
        '[12:01:00] Speaker 00',
        '[12:03:20] Speaker 00',
    ]


def test_a_moment_ends_on_the_last_speech_of_a_merged_turn():
    row = {'id': 'c1', **_turn_row(*[(i * 10, i * 10 + 10, 'SPEAKER_00', f'w{i}') for i in range(5)])}
    tz = ZoneInfo('UTC')
    assert len(composer.transcript_lines(row, 'Me', tz)) == 1
    data = {'chapters': [{'title': 'Plans', 'start': '12:00:00', 'points': ['Point']}]}
    moment = composer.to_updates(data, [row], tz)['moments'][0]
    assert moment['end_offset'] >= 40


def test_a_section_seconds_long_ends_on_the_last_line_it_owns():
    row = {'id': 'c1', **_turn_row(*[(i * 60, i * 60 + 60, 'SPEAKER_00', f'w{i}') for i in range(30)])}
    data = {
        'chapters': [
            {'title': 'Second', 'start': '12:10:00', 'end': '12:10:08', 'points': ['Point']},
            {'title': 'First', 'start': '12:00:00', 'end': '12:00:22', 'points': ['Point']},
        ]
    }
    first, second = composer.to_updates(data, [row], ZoneInfo('UTC'))['moments']
    assert (first['heading'], second['heading']) == ('First', 'Second')
    assert (first['ended_at'] - first['started_at']).total_seconds() == 9 * 60
    assert (second['ended_at'] - second['started_at']).total_seconds() >= 19 * 60


def test_the_wire_reads_moments_in_time_order_and_drops_placeholder_headings():
    from utils.episodes import service as svc

    moment = lambda mid, minutes, heading, **extra: {  # noqa: E731
        'id': mid,
        'conversation_id': 'c1',
        'started_at': T0 + timedelta(minutes=minutes),
        'ended_at': T0 + timedelta(minutes=minutes, seconds=8),
        'heading': heading,
        **extra,
    }
    points = [{'text': 'Point', 'details': []}]
    wire = svc.to_wire(
        {
            'id': 'e',
            'status': 'closed',
            'started_at': T0,
            'last_activity_at': T0,
            'moments': [moment('b', 34, 'New moment', points=points), moment('a', 0, 'Checklist', points=points)],
        }
    )
    assert [m['id'] for m in wire['moments']] == ['a', 'b']
    assert wire['moments'][1]['heading'] == ''
    assert wire['moments'][0]['ended_at'] == T0 + timedelta(minutes=34)
    assert wire['moments'][1]['ended_at'] == T0 + timedelta(minutes=34, seconds=8)


@pytest.mark.parametrize('drift', ['title', 'overview', 'action_items', 'speaker', 'is_user', 'person_id', 'timing'])
def test_label_summary_and_timing_drift_do_not_pay(store, drift):
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    stamp = store.episode['composed_fingerprint']
    row = store.rows['c1']
    if drift in {'title', 'overview', 'action_items'}:
        row['structured'][drift] = [{'description': 'New wording'}] if drift == 'action_items' else 'New wording'
    else:
        row['transcript_segments'][0][{'timing': 'start'}.get(drift, drift)] = {
            'speaker': 'SPEAKER_99',
            'is_user': False,
            'person_id': 'unknown',
            'timing': 2,
        }[drift]
    assert composer.fingerprint(list(store.rows.values())) != stamp
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'unchanged'
    assert store.episode['composed_fingerprint'] == stamp and len(calls) == 1


def _schedule_seam(store, monkeypatch):
    monkeypatch.setattr(composer.episodes_db, 'get_episode_for_conversation', store.get_episode)
    monkeypatch.setattr(composer._executor, 'submit', lambda fn: fn())


def test_sync_update_summary_drift_skips_before_member_reads(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    store.rows['c1']['structured']['overview'] = 'Reprocessed summary'
    store.rows['c1']['transcript_segments'][0]['speaker'] = 'SPEAKER_77'
    _schedule_seam(store, monkeypatch)
    monkeypatch.setattr(composer.conversations_db, 'get_conversation', lambda *a, **kw: pytest.fail('redundant read'))
    reasons = []
    monkeypatch.setattr(composer.metrics, 'record_compose_trigger_skipped', reasons.append)
    assert composer.after_finalized(UID, 'c1', 'finalized', c, row=store.rows['c1']) == 'finalized'
    assert len(calls) == 1 and reasons == ['evidence_unchanged']
    assert not composer._deferred


@pytest.mark.parametrize('change', ['speech', 'name', 'late_member', 'membership', 'discard', 'delete'])
def test_real_finalized_evidence_is_deferred_then_recomposed(store, monkeypatch, change):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    cid = 'c1'
    if change == 'speech':
        store.rows[cid]['transcript_segments'][0]['text'] += ' We decided to ship.'
    elif change == 'name':
        store.rows[cid]['transcript_segments'][1]['person_name'] = 'Arjan'
    elif change == 'late_member':
        cid = 'c3'
        store.rows[cid] = _row(cid, T0 + timedelta(minutes=184), 4)
        store.episode['conversation_ids'].append(cid)
    elif change == 'membership':
        store.episode['conversation_ids'] = ['c1']
    else:
        store.rows[cid][{'discard': 'discarded', 'delete': 'deleted'}[change]] = True
    _schedule_seam(store, monkeypatch)
    composer.schedule_for_conversation(UID, cid, collaborators=c, row=store.rows[cid])
    assert len(calls) == 1
    assert (UID, 'ep1') in composer._deferred
    assert store.episode['compose_pending_since']
    # Simulate the due tick after a full quiet window, without sleeping or changing recorded boundaries.
    store.episode['compose_pending_since'] -= timedelta(minutes=11)
    store.episode['compose_activity_at'] -= timedelta(minutes=11)
    composer._deferred[(UID, 'ep1')] = (0, c)
    composer._schedule_due()
    assert len(calls) == 2
    assert store.episode['compose_pending_since'] is None
    assert not composer._deferred
    if change in {'membership', 'discard', 'delete'}:
        assert store.episode['composed_member_ids'] == (['c1'] if change == 'membership' else ['c2'])


def test_background_settles_without_claiming_lease_or_holding_worker(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    _schedule_seam(store, monkeypatch)
    assert composer.schedule(UID, 'ep1', collaborators=c)
    assert not calls and not composer._inflight
    assert 'compose_lease' not in store.episode
    assert 590 < composer._deferred[(UID, 'ep1')][0] - composer.time.monotonic() <= 600
    assert store.episode['compose_activity_at'] >= store.episode['compose_pending_since']


@pytest.mark.parametrize('previously_composed', [False, True])
def test_full_settle_queue_composes_immediately_without_losing_pending_evidence(
    store, monkeypatch, previously_composed
):
    calls = []
    c = _c(calls=calls)
    if previously_composed:
        assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
        store.rows['c1']['transcript_segments'][0]['text'] += ' New speech.'
    _schedule_seam(store, monkeypatch)
    queued = {(UID, f'other-{i}'): (float('inf'), c) for i in range(10_000)}
    composer._deferred.update(queued)
    fallbacks = []
    outcomes = []
    monkeypatch.setattr(composer, 'record_fallback', lambda **kw: fallbacks.append(kw))
    monkeypatch.setattr(composer.metrics, 'record_compose', lambda outcome, seconds: outcomes.append(outcome))

    assert composer.schedule(UID, 'ep1', collaborators=c)

    assert outcomes == ['composed']
    assert len(calls) == (2 if previously_composed else 1)
    assert store.writes[-3]['compose_pending_since']
    assert store.writes[-2]['compose_lease']['fingerprint'] == store.episode['composed_fingerprint']
    assert store.episode['compose_pending_since'] is None
    assert store.episode['composed_evidence'] == composer._evidence(list(store.rows.values()))
    assert composer._deferred == queued and not composer._inflight
    assert len(fallbacks) == 1
    assert fallbacks[0] == {
        'component': 'conversation_notes',
        'from_mode': 'episode_compose_settling',
        'to_mode': 'episode_compose_immediate',
        'reason': 'capacity_full',
        'outcome': 'degraded',
        'log': composer.logger,
    }
    # Saturation does not bypass the normal fingerprint deduplication on the next attempt.
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'unchanged'
    assert len(calls) == (2 if previously_composed else 1) and len(fallbacks) == 1


@pytest.mark.parametrize('change', ['speech', 'name'])
@pytest.mark.parametrize('failure', ['cas_exhausted', 'storage_error', 'gate_only'])
def test_failed_pending_write_still_schedules_and_eventually_composes(store, monkeypatch, change, failure):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    old_stamp = store.episode['composed_fingerprint']
    segment = store.rows['c1']['transcript_segments'][1]
    segment['text' if change == 'speech' else 'person_name'] = 'New speech' if change == 'speech' else 'Arjan'
    _schedule_seam(store, monkeypatch)
    write = store.update_episode
    attempts = []
    fallbacks = []
    monkeypatch.setattr(composer, 'record_fallback', lambda **kw: fallbacks.append(kw))

    def fail_pending(*args, **kw):
        if kw['updates'].get('compose_pending_since'):
            attempts.append(kw['updates'])
            if failure != 'gate_only' or len(attempts) <= 3:
                if failure == 'storage_error':
                    raise RuntimeError('storage unavailable')
                raise composer.episodes_db.EpisodeConflict('state_version_changed')
        return write(*args, **kw)

    monkeypatch.setattr(composer.episodes_db, 'update_episode', fail_pending)
    assert composer.after_finalized(UID, 'c1', 'finalized', c, row=store.rows['c1']) == 'finalized'
    if failure == 'gate_only':
        # Once metadata writes recover, the scheduled worker durably retains its retry.
        assert len(calls) == 1 and composer._deferred and store.episode['compose_pending_since']
        store.episode['compose_pending_since'] -= timedelta(minutes=11)
        store.episode['compose_activity_at'] -= timedelta(minutes=11)
        composer._deferred[(UID, 'ep1')] = (0, c)
        composer._schedule_due()
    else:
        # Even persistent metadata failure must pay now rather than lose this last finalize.
        assert len(attempts) == (6 if failure == 'cas_exhausted' else 2)
    assert len(calls) == 2 and store.episode['composed_fingerprint'] != old_stamp
    assert not composer._deferred and store.episode['compose_pending_since'] is None
    assert fallbacks and all(f['reason'] == 'enqueue_failed' and f['outcome'] == 'degraded' for f in fallbacks)
    # The immediate fallback still stamps and deduplicates the paid evidence normally.
    assert composer.compose(UID, 'ep1', collaborators=c) == 'unchanged'
    assert len(calls) == 2


def test_identical_finalizes_do_not_extend_quiet_window(store, monkeypatch):
    c = _c()
    _schedule_seam(store, monkeypatch)
    assert composer.schedule(UID, 'ep1', collaborators=c)
    first, activity = store.episode['compose_pending_since'], store.episode['compose_activity_at']
    writes = len(store.writes)
    store.rows['c1']['structured']['overview'] = 'Drift'
    composer.schedule_for_conversation(UID, 'c1', collaborators=c, row=store.rows['c1'])
    assert store.episode['compose_pending_since'] == first
    assert store.episode['compose_activity_at'] == activity
    assert len(store.writes) == writes


def test_new_speech_extends_quiet_window_but_preserves_first_pending_time(store, monkeypatch):
    c = _c()
    _schedule_seam(store, monkeypatch)
    composer.schedule(UID, 'ep1', collaborators=c)
    store.episode['compose_pending_since'] -= timedelta(minutes=20)
    store.episode['compose_activity_at'] -= timedelta(minutes=2)
    first = store.episode['compose_pending_since']
    store.rows['c1']['transcript_segments'][0]['text'] += ' Late words.'
    composer.schedule_for_conversation(UID, 'c1', collaborators=c, row=store.rows['c1'])
    assert store.episode['compose_pending_since'] == first
    assert 299 < composer.settle_delay(store.episode) <= 300


def test_continuous_upload_pays_at_max_latency_cap(store):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'settling'
    store.episode['compose_pending_since'] -= timedelta(minutes=26)
    store.rows['c1']['transcript_segments'][0]['text'] += ' Still uploading.'
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'composed'
    assert len(calls) == 1


def test_pending_window_survives_process_local_queue_loss(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'settling'
    store.episode['compose_pending_since'] -= timedelta(minutes=26)
    composer._deferred.clear()  # A new process has no local queue.
    _schedule_seam(store, monkeypatch)
    composer.schedule_for_conversation(UID, 'c1', collaborators=c, row=store.rows['c1'])
    assert len(calls) == 1 and store.episode['compose_pending_since'] is None


@pytest.mark.parametrize('enabled', ['on', 'off'])
@pytest.mark.parametrize('change', ['speech', 'name'])
def test_read_recovers_persisted_pending_evidence_after_restart(store, monkeypatch, enabled, change):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    old_stamp = store.episode['composed_fingerprint']
    segment = store.rows['c1']['transcript_segments'][1]
    segment['text' if change == 'speech' else 'person_name'] = 'Late speech' if change == 'speech' else 'Arjan'
    _schedule_seam(store, monkeypatch)
    composer.schedule_for_conversation(UID, 'c1', collaborators=c, row=store.rows['c1'])
    assert len(calls) == 1 and store.episode['compose_pending_since']
    # Keep only persisted state, as after an instance restart and optional rollback.
    for state in (composer._deferred, composer._recent, composer._inflight, composer._rerun, composer._foreground):
        state.clear()
    monkeypatch.setenv(config.EPISODE_COMPOSE_SETTLE_ENABLED_ENV, enabled)
    assert composer.needs_compose(store.episode)
    schedule = composer.schedule
    monkeypatch.setattr(composer, 'schedule', lambda uid, eid, **kw: schedule(uid, eid, collaborators=c, **kw))
    assert (
        home_read.schedule_missed_composes(
            UID, [store.episode], [{'id': 'ep1', 'members': [{'id': 'c1'}, {'id': 'c2'}]}]
        )
        == 1
    )
    assert len(calls) == 2 and store.episode['composed_fingerprint'] != old_stamp
    assert store.episode['compose_pending_since'] is None and not composer._deferred


def test_later_trigger_after_restart_preserves_pending_cap_despite_new_speech(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    store.rows['c1']['transcript_segments'][0]['text'] += ' Late speech.'
    _schedule_seam(store, monkeypatch)
    composer.schedule_for_conversation(UID, 'c1', collaborators=c, row=store.rows['c1'])
    store.episode['compose_pending_since'] -= timedelta(minutes=20)
    store.episode['compose_activity_at'] -= timedelta(minutes=2)
    first = store.episode['compose_pending_since']
    for state in (composer._deferred, composer._recent, composer._inflight, composer._rerun, composer._foreground):
        state.clear()
    store.rows['c1']['transcript_segments'][0]['text'] += ' Still uploading.'
    composer.schedule_for_conversation(UID, 'c1', collaborators=c, row=store.rows['c1'])
    assert len(calls) == 1 and store.episode['compose_pending_since'] == first
    assert 299 < composer._deferred[(UID, 'ep1')][0] - composer.time.monotonic() <= 300
    # The recovered worker pays at the persisted cap even if activity is still recent.
    store.episode['compose_pending_since'] -= timedelta(minutes=6)
    composer._deferred[(UID, 'ep1')] = (0, c)
    composer._schedule_due()
    assert len(calls) == 2 and store.episode['compose_pending_since'] is None and not composer._deferred


def test_rollback_drains_pending_marker_without_paying_if_speech_was_reverted(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    old_text = store.rows['c1']['transcript_segments'][0]['text']
    store.rows['c1']['transcript_segments'][0]['text'] += ' Late speech.'
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'settling'
    store.rows['c1']['transcript_segments'][0]['text'] = old_text
    composer._deferred.clear()
    monkeypatch.setenv(config.EPISODE_COMPOSE_SETTLE_ENABLED_ENV, 'off')
    assert composer.needs_compose(store.episode)
    _schedule_seam(store, monkeypatch)
    assert composer.schedule(UID, 'ep1', collaborators=c, throttle=True)
    assert len(calls) == 1 and store.episode['compose_pending_since'] is None
    assert not composer.needs_compose(store.episode)


def test_read_promotes_deferred_compose_even_inside_throttle_window(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    _schedule_seam(store, monkeypatch)
    assert composer.schedule(UID, 'ep1', collaborators=c)
    assert not calls
    assert composer.schedule(UID, 'ep1', collaborators=c, throttle=True)
    assert len(calls) == 1 and not composer._deferred


def test_read_promotes_inflight_background_that_is_entering_settle(store, monkeypatch):
    c = _c()
    _schedule_seam(store, monkeypatch)
    real_compose = composer.compose
    modes = []

    def compose(uid, eid, **kw):
        modes.append(kw['background'])
        result = real_compose(uid, eid, **kw)
        if len(modes) == 1:
            assert not composer.schedule(uid, eid, collaborators=c, throttle=True)
        return result

    monkeypatch.setattr(composer, 'compose', compose)
    assert composer.schedule(UID, 'ep1', collaborators=c)
    assert modes == [True, False]
    assert store.episode.get('composed_fingerprint') and not composer._deferred


def test_force_and_direct_page_compose_bypass_settle(store):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'settling'
    assert composer.compose(UID, 'ep1', collaborators=c, background=True, force=True) == 'composed'
    store.rows['c1']['transcript_segments'][0]['text'] += ' New evidence.'
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    assert len(calls) == 2


@pytest.mark.parametrize('outcome', ['superseded', 'stale'])
def test_racing_paid_background_call_waits_before_retry(store, monkeypatch, outcome):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'settling'
    store.episode['compose_pending_since'] -= timedelta(minutes=11)
    store.episode['compose_activity_at'] -= timedelta(minutes=11)
    composer._deferred.clear()
    _schedule_seam(store, monkeypatch)
    if outcome == 'superseded':

        def invoke(uid, messages):
            calls.append(messages)
            store.rows['c1']['transcript_segments'][0]['text'] += ' Arrived during the call.'
            return _reply()

        c = _c(invoke=invoke)
    else:
        update = store.update_episode

        def write(*args, **kw):
            result = update(*args, **kw)
            if 'composed_fingerprint' in kw['updates']:
                store.rows['c1']['transcript_segments'][0]['text'] += ' Arrived during the final write.'
            return result

        monkeypatch.setattr(composer.episodes_db, 'update_episode', write)
    outcomes = []
    monkeypatch.setattr(composer.metrics, 'record_compose', lambda result, seconds: outcomes.append(result))
    assert composer.schedule(UID, 'ep1', collaborators=c)
    assert outcomes == [outcome, 'settling']
    assert len(calls) == 1 and composer._deferred and not composer._inflight


def test_off_restores_label_drift_payment_and_immediate_background(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    monkeypatch.setenv(config.EPISODE_COMPOSE_SETTLE_ENABLED_ENV, 'off')
    _schedule_seam(store, monkeypatch)
    assert composer.schedule(UID, 'ep1', collaborators=c)
    store.rows['c1']['structured']['overview'] = 'Drift'
    composer.schedule_for_conversation(UID, 'c1', collaborators=c, row=store.rows['c1'])
    assert len(calls) == 2 and not composer._deferred


def test_settling_and_skipped_trigger_metrics_have_no_user_labels():
    before = metrics.EPISODE_COMPOSE_TOTAL.labels(outcome='settling')._value.get()
    skips = metrics.EPISODE_COMPOSE_TRIGGER_SKIPPED_TOTAL.labels(reason='evidence_unchanged')._value.get()
    metrics.record_compose('settling', 0.01)
    metrics.record_compose_trigger_skipped('evidence_unchanged')
    assert metrics.EPISODE_COMPOSE_TOTAL.labels(outcome='settling')._value.get() == before + 1
    assert metrics.EPISODE_COMPOSE_TRIGGER_SKIPPED_TOTAL.labels(reason='evidence_unchanged')._value.get() == skips + 1
    assert metrics.EPISODE_COMPOSE_TOTAL._labelnames == ('outcome',)
    assert metrics.EPISODE_COMPOSE_TRIGGER_SKIPPED_TOTAL._labelnames == ('reason',)


def test_settle_retry_task_cancels_and_clears_its_queue(monkeypatch):
    async def run():
        task = asyncio.create_task(composer.retry_settled_composes())
        await asyncio.sleep(0)
        composer._deferred[(UID, 'ep1')] = (float('inf'), None)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not composer._deferred

    asyncio.run(run())


def test_home_read_safety_net_bypasses_pending_quiet_window(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    _schedule_seam(store, monkeypatch)
    assert composer.schedule(UID, 'ep1', collaborators=c)
    schedule = composer.schedule
    monkeypatch.setattr(composer, 'schedule', lambda uid, eid, **kw: schedule(uid, eid, collaborators=c, **kw))
    assert (
        home_read.schedule_missed_composes(
            UID,
            [store.episode],
            [{'id': 'ep1', 'members': [{'id': 'c1'}, {'id': 'c2'}]}],
        )
        == 1
    )
    assert len(calls) == 1 and not composer._deferred


def test_same_full_fingerprint_backfills_trigger_stamp_without_paying(store):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    del store.episode['composed_evidence']
    del store.episode['composed_membership']
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'unchanged'
    assert store.episode['composed_evidence'] and len(calls) == 1


def test_superseded_at_latency_cap_still_waits_before_next_paid_attempt(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'settling'
    store.episode['compose_pending_since'] -= timedelta(minutes=26)
    composer._deferred.clear()
    _schedule_seam(store, monkeypatch)

    def invoke(uid, messages):
        calls.append(messages)
        store.rows['c1']['transcript_segments'][0]['text'] += ' Continually arriving.'
        return _reply()

    assert composer.schedule(UID, 'ep1', collaborators=_c(invoke=invoke))
    assert len(calls) == 1 and composer._deferred
    assert 590 < composer.settle_delay(store.episode) <= 600


def test_off_restores_immediate_superseded_retry(store, monkeypatch):
    monkeypatch.setenv(config.EPISODE_COMPOSE_SETTLE_ENABLED_ENV, 'off')
    calls = []
    _schedule_seam(store, monkeypatch)

    def invoke(uid, messages):
        calls.append(messages)
        if len(calls) == 1:
            store.rows['c1']['transcript_segments'][0]['text'] += ' New words.'
        return _reply()

    assert composer.schedule(UID, 'ep1', collaborators=_c(invoke=invoke))
    assert len(calls) == 2 and not composer._deferred
    assert store.episode['composed_fingerprint']


def test_read_arriving_as_background_worker_exits_is_not_lost(store, monkeypatch):
    calls = []
    c = _c(calls=calls)
    _schedule_seam(store, monkeypatch)
    lock = composer.threading.Lock()

    class ExitRace:
        exits = 0

        def __enter__(self):
            lock.acquire()

        def __exit__(self, *_):
            lock.release()
            self.exits += 1
            if self.exits == 3:
                # After the outcome decision, before inflight ownership is released.
                assert not composer.schedule(UID, 'ep1', collaborators=c, throttle=True)

    monkeypatch.setattr(composer, '_inflight_lock', ExitRace())
    assert composer.schedule(UID, 'ep1', collaborators=c)
    assert len(calls) == 1 and not composer._deferred and not composer._inflight


@pytest.mark.parametrize('change', ['speech', 'summary'])
def test_legacy_changed_fingerprint_composes_once_then_uses_narrow_gate(store, change):
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    del store.episode['composed_evidence']
    del store.episode['composed_membership']
    if change == 'speech':
        store.rows['c1']['transcript_segments'][0]['text'] += ' Real late speech.'
    else:
        store.rows['c1']['structured']['overview'] = 'Label-only legacy drift'
    # The legacy full hash cannot distinguish these two cases: never drop real late speech.
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'settling'
    assert len(calls) == 1
    store.episode['compose_pending_since'] -= timedelta(minutes=11)
    store.episode['compose_activity_at'] -= timedelta(minutes=11)
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'composed'
    assert len(calls) == 2 and store.episode['composed_evidence']
    store.rows['c1']['structured']['overview'] = 'Another label-only reprocess'
    assert composer.compose(UID, 'ep1', collaborators=c, background=True) == 'unchanged'
    assert len(calls) == 2
