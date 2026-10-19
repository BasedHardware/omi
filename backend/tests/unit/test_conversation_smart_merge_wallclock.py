"""Smart merge wall-clock gap behavior, end to end over the strict in-memory Firestore.

Live rollover generations share ``external_data.recording_origin_id`` while each
carries its own ``recording_session_id``. A legacy-gate skip is rescued only
when the server wall clock and recording lineage prove both fragments came
from the same recording.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import conversation_smart_merge as config
from database import conversations as conversations_db
from tests.unit.test_conversation_smart_merge import T0, UID, World
from utils import metrics
from utils.conversations import smart_merge
from utils.conversations import smart_merge_policy as policy
from utils.conversations.processing_trigger import ProcessingTrigger

ORIGIN = 'recording-1'
SESSION = 'session-1'


def _stamps(origin=ORIGIN, session=SESSION):
    return {'recording_session_id': session, 'recording_origin_id': origin}


def _add(world, cid, created_s, started_s, finished_s, *, origin=ORIGIN, stamps=True, **extra):
    if stamps:
        extra.setdefault('external_data', _stamps(origin))
    extra['created_at'] = T0 + timedelta(seconds=created_s)
    return world.add(cid, started_s / 60.0, (finished_s - started_s) / 60.0, **extra)


def _drifted_pair(world, *, origin=ORIGIN, new_origin=None):
    """Survivor finished T0+600s; new created T0+720s, started T0+400s, finished T0+1020s.

    Legacy recorded gap is -200 s (out of window); the wall gap is +120 s.
    """
    _add(world, 'p', 0, 0, 600, origin=origin)
    _add(world, 'n', 720, 400, 1020, origin=origin if new_origin is None else new_origin)


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'merge')
    return World(monkeypatch)


def test_default_wallclock_path_merges_a_drifted_same_recording_pair(world, caplog):
    _drifted_pair(world)
    world.jev_answers = [0.35]
    caplog.set_level('INFO', logger=smart_merge.logger.name)

    assert world.finish('n') is True

    donor = world.raw('n')
    assert donor['deleted'] is True and donor['sync_merged_into'] == 'p'
    assert donor['smart_merge']['role'] == 'donor'
    assert donor['smart_merge_decision']['decision'] == 'merged'
    assert donor['smart_merge_decision']['gap_seconds'] == 120.0
    assert donor['smart_merge_decision']['speech_gap_seconds'] is None
    survivor = world.get(UID, 'p')
    assert sorted(s['id'] for s in survivor['transcript_segments']) == ['n-s0', 'n-s1', 'p-s0', 'p-s1']
    assert len(world.jev_calls) == 1
    assert '2 min after A ended' in world.jev_calls[0]['state']
    merged = [r.getMessage() for r in caplog.records if 'decision=merged' in r.getMessage()]
    assert len(merged) == 1 and 'gap_path=wallclock' in merged[0]
    fragments = survivor['smart_merge']['fragments']
    assert [f['id'] for f in fragments] == ['p', 'n']
    assert fragments[1]['started_at'] == T0 + timedelta(seconds=400)


@pytest.mark.parametrize('created_s', [599, 1600])
def test_legacy_accepted_pair_keeps_its_legacy_path(world, caplog, created_s):
    """A pair the legacy gate accepts keeps its exact legacy verdict under the unconditional policy,
    even when its wall times are negative (599) or invalid (1600 > finished)."""
    _add(world, 'p', 0, 0, 600)
    _add(world, 'n', created_s, 900, 1500)
    world.jev_answers = [0.35]
    seen = []
    world.monkeypatch.setattr(
        metrics.CONVERSATION_SMART_MERGE_DECISION_TOTAL,
        'labels',
        lambda **labels: SimpleNamespace(inc=lambda: seen.append(labels)),
    )
    caplog.set_level('INFO', logger=smart_merge.logger.name)

    assert world.finish('n') is True

    donor = world.raw('n')
    assert donor['deleted'] is True and donor['sync_merged_into'] == 'p'
    assert donor['smart_merge']['role'] == 'donor'
    record = donor['smart_merge_decision']
    assert record['decision'] == 'merged' and record['reason'] == 'jev_same'
    assert record['gap_seconds'] == 300.0 and record['speech_gap_seconds'] == 300.0
    assert len(world.jev_calls) == 1
    assert '5 min after A ended' in world.jev_calls[0]['state']
    assert seen == [{'mode': 'merge', 'decision': 'merge', 'reason': 'absorbed', 'gap_bucket': '5_15m'}]
    merged = [r.getMessage() for r in caplog.records if 'decision=merged' in r.getMessage()]
    assert len(merged) == 1
    assert 'gap_path=legacy' in merged[0]


@pytest.mark.parametrize('gap_s', [0, 60, 3600])
def test_wallclock_gap_edges_are_asked(world, gap_s):
    _drifted_pair(world)
    world.raw('n')['created_at'] = T0 + timedelta(seconds=600 + gap_s)
    world.raw('n')['finished_at'] = world.raw('n')['created_at'] + timedelta(seconds=300)
    world.jev_answers = [0.9]
    world.finish('n')
    assert len(world.jev_calls) == 1


@pytest.mark.parametrize('gap_s, reason', [(3601, 'gap_out_of_window'), (-1, 'wallclock_gap_negative')])
def test_wallclock_gap_bounds_skip_without_jev(world, caplog, gap_s, reason):
    _drifted_pair(world)
    world.raw('n')['created_at'] = T0 + timedelta(seconds=600 + gap_s)
    world.raw('n')['finished_at'] = world.raw('n')['created_at'] + timedelta(seconds=300)
    world.jev_answers = [0.9]
    caplog.set_level('INFO', logger=smart_merge.logger.name)
    assert world.finish('n') is False
    assert world.jev_calls == []
    assert any(f'reason={reason}' in r.getMessage() for r in caplog.records)
    assert not world.raw('n').get('deleted')


@pytest.mark.parametrize(
    'survivor_stamps, new_stamps',
    [
        (None, _stamps()),
        (_stamps(), None),
        (None, None),
        (_stamps('other'), _stamps()),
        ({'recording_origin_id': ORIGIN}, _stamps()),
        (_stamps(), {'recording_session_id': SESSION}),
    ],
)
def test_without_matching_live_lineage_the_legacy_result_runs(world, survivor_stamps, new_stamps):
    _drifted_pair(world)
    world.raw('p')['external_data'] = survivor_stamps
    world.raw('n')['external_data'] = new_stamps
    world.jev_answers = [0.9]
    assert world.finish('n') is False
    assert world.jev_calls == []
    assert not world.raw('n').get('deleted') and 'smart_merge' not in world.raw('p')


def test_sync_pair_without_stamps_is_unchanged(world):
    """No live stamps at all: legacy behavior without recording lineage."""
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.jev_answers = [0.2]
    assert world.finish('n') is False
    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == 'kept' and record['reason'] == 'jev_different'
    assert record['gap_seconds'] == 300.0 and record['speech_gap_seconds'] is not None
    assert len(world.jev_calls) == 1


def test_last_fragment_donor_row_proves_lineage_for_a_third_generation(world):
    """f2 drifts to start before f1 but finishes last; f3's proof comes from the f2 row."""
    _add(world, 'f1', 0, 0, 600)
    _add(world, 'f2', 700, -120, 1200)
    world.jev_answers = [0.9, 0.9]
    assert world.finish('f2') is True

    del world.raw('f1')['external_data']
    _add(world, 'f3', 1300, 900, 1700)
    assert world.finish('f3') is True
    survivor = world.get(UID, 'f1')
    assert [f['id'] for f in survivor['smart_merge']['fragments']] == ['f2', 'f1', 'f3']
    assert world.raw('f3')['smart_merge_decision']['gap_seconds'] == 100.0


def test_different_latest_origin_uses_legacy_even_if_survivor_matches(world):
    _add(world, 'f1', 0, 0, 600)
    _add(world, 'f2', 700, 720, 1200, origin='other-recording')
    assert world.finish('f2') is True

    _add(world, 'f3', 1300, 900, 1700)
    world.jev_answers = [0.9]
    jev_before = len(world.jev_calls)
    assert world.finish('f3') is False
    assert len(world.jev_calls) == jev_before


def test_following_wallclock_rescue_reads_latest_fragment_once(world):
    _add(world, 'f1', 0, 0, 600)
    _add(world, 'f2', 700, -120, 1200)
    world.jev_answers = [0.9]
    assert world.finish('f2') is True

    reads = []
    original = conversations_db.get_conversation

    def counting(uid, cid, **kwargs):
        reads.append(cid)
        return original(uid, cid, **kwargs)

    world.monkeypatch.setattr(conversations_db, 'get_conversation', counting)
    _add(world, 'f3', 1300, 900, 1700)
    assert world.finish('f3') is True
    assert reads.count('f2') == 1


def test_wallclock_path_reads_the_donor_fragment_at_most_once(world):
    _add(world, 'f1', 0, 0, 600)
    _add(world, 'f2', 700, -120, 1200)
    world.jev_answers = [0.9, 0.9]
    assert world.finish('f2') is True

    reads = []
    original = conversations_db.get_conversation

    def counting(uid, cid, **kwargs):
        reads.append(cid)
        return original(uid, cid, **kwargs)

    world.monkeypatch.setattr(conversations_db, 'get_conversation', counting)
    _add(world, 'f3', 1300, 900, 1700)
    assert world.finish('f3') is True
    assert reads.count('f2') == 1


def test_fragment_origin_mutation_between_decide_and_commit_rejects(world):
    _add(world, 'f1', 0, 0, 600)
    _add(world, 'f2', 700, -120, 1200)
    world.jev_answers = [0.9, 0.9]
    assert world.finish('f2') is True

    _add(world, 'f3', 1300, 900, 1700)
    plan = smart_merge._decide(
        UID, 'f3', mode=config.SmartMergeMode.MERGE, trigger=ProcessingTrigger.CAPTURE_END, owner='job'
    )
    assert plan is not None
    world.raw('f2')['external_data']['recording_origin_id'] = 'tampered'
    assert smart_merge._absorb(UID, 'f3', plan, mode=config.SmartMergeMode.MERGE, owner='job') is False
    assert not world.raw('f3').get('deleted')
    assert world.raw('f3')['smart_merge_decision']['decision'] == 'kept'


def test_survivor_origin_mutation_between_decide_and_commit_rejects(world):
    _drifted_pair(world)
    world.jev_answers = [0.9]
    plan = smart_merge._decide(
        UID, 'n', mode=config.SmartMergeMode.MERGE, trigger=ProcessingTrigger.CAPTURE_END, owner='job'
    )
    assert plan is not None
    world.raw('p')['external_data']['recording_origin_id'] = 'tampered'
    assert smart_merge._absorb(UID, 'n', plan, mode=config.SmartMergeMode.MERGE, owner='job') is False
    assert not world.raw('n').get('deleted')


def test_last_fragment_finish_mutation_rejects_a_stale_wall_gap(world):
    _add(world, 'f1', 0, 0, 600)
    _add(world, 'f2', 700, -120, 1200)
    world.jev_answers = [0.9]
    assert world.finish('f2') is True

    _add(world, 'f3', 1300, 900, 1700)
    world.jev_answers = [0.9]
    plan = smart_merge._decide(
        UID, 'f3', mode=config.SmartMergeMode.MERGE, trigger=ProcessingTrigger.CAPTURE_END, owner='job'
    )
    assert plan is not None
    world.raw('f2')['finished_at'] = T0 + timedelta(seconds=1400)
    assert smart_merge._absorb(UID, 'f3', plan, mode=config.SmartMergeMode.MERGE, owner='job') is False
    assert not world.raw('f3').get('deleted')


@pytest.mark.parametrize('post_plan_created_s', [None, 1600])
def test_union_recheck_lets_a_legacy_plan_survive_a_bad_wall_clock(world, post_plan_created_s):
    """A legacy-admitted plan rechecks the union rule: a negative (599) or
    invalid (1600 > finished) wall clock cannot reject what legacy admits."""
    _add(world, 'p', 0, 0, 600)
    _add(world, 'n', 599, 900, 1500)
    world.jev_answers = [0.35]
    plan = smart_merge._decide(
        UID, 'n', mode=config.SmartMergeMode.MERGE, trigger=ProcessingTrigger.CAPTURE_END, owner='job'
    )
    assert plan is not None
    assert plan.wallclock_gap is True and plan.same_recording is False
    assert plan.admission_path == 'legacy'
    if post_plan_created_s is not None:
        world.raw('n')['created_at'] = T0 + timedelta(seconds=post_plan_created_s)
    assert smart_merge._absorb(UID, 'n', plan, mode=config.SmartMergeMode.MERGE, owner='job') is True
    assert world.raw('n')['deleted'] is True and world.raw('n')['sync_merged_into'] == 'p'


def test_union_recheck_lets_a_wall_plan_survive_a_fresh_legacy_pass(world, caplog):
    """A wall-clock-admitted plan still commits when fresh rows would pass legacy,
    even though the same fresh rows make the wall gap negative."""
    _drifted_pair(world)
    world.jev_answers = [0.9]
    plan = smart_merge._decide(
        UID, 'n', mode=config.SmartMergeMode.MERGE, trigger=ProcessingTrigger.CAPTURE_END, owner='job'
    )
    assert plan is not None
    assert plan.wallclock_gap is True and plan.same_recording is True
    assert plan.admission_path == 'wallclock'
    world.raw('n')['started_at'] = T0 + timedelta(seconds=900)
    world.raw('n')['created_at'] = T0 + timedelta(seconds=599)
    caplog.set_level('INFO', logger=smart_merge.logger.name)
    caplog.clear()
    assert smart_merge._absorb(UID, 'n', plan, mode=config.SmartMergeMode.MERGE, owner='job') is True
    assert world.raw('n')['deleted'] is True
    merged = [r.getMessage() for r in caplog.records if 'decision=merged' in r.getMessage()]
    assert len(merged) == 1 and 'gap_path=legacy' in merged[0]


def test_union_recheck_rescues_a_legacy_plan_on_fresh_data(world, caplog):
    """A legacy-admitted plan whose fresh rows now skip legacy is rescued
    by the wall-clock proof re-evaluated inside the transaction."""
    _add(world, 'p', 0, 0, 600)
    _add(world, 'n', 720, 900, 1500)
    world.jev_answers = [0.9]
    plan = smart_merge._decide(
        UID, 'n', mode=config.SmartMergeMode.MERGE, trigger=ProcessingTrigger.CAPTURE_END, owner='job'
    )
    assert plan is not None
    assert plan.wallclock_gap is True and plan.same_recording is False
    world.raw('n')['started_at'] = T0 + timedelta(seconds=400)
    caplog.set_level('INFO', logger=smart_merge.logger.name)
    caplog.clear()
    assert smart_merge._absorb(UID, 'n', plan, mode=config.SmartMergeMode.MERGE, owner='job') is True
    assert world.raw('n')['deleted'] is True and world.raw('n')['sync_merged_into'] == 'p'
    merged = [r.getMessage() for r in caplog.records if 'decision=merged' in r.getMessage()]
    assert len(merged) == 1 and 'gap_path=wallclock' in merged[0]


def test_wallclock_path_does_not_reuse_a_legacy_cached_decision(world):
    """A legacy record (nonnull speech gap, different gap) must be re-asked under the wall-clock policy."""
    _add(world, 'p', 0, 0, 600)
    _add(world, 'n', 700, 900, 1500)
    world.jev_answers = [0.2]
    assert world.finish('n') is False
    assert world.raw('n')['smart_merge_decision']['speech_gap_seconds'] is not None

    world.raw('n')['started_at'] = T0 + timedelta(seconds=400)
    world.jev_answers = [0.9]
    assert world.finish('n') is True
    assert len(world.jev_calls) == 2


def test_reuses_a_legacy_cached_decision_when_legacy_still_admits(world):
    """A sticky legacy keep is honored on the same candidate and path without re-asking."""
    _add(world, 'p', 0, 0, 600)
    _add(world, 'n', 700, 900, 1500)
    world.jev_answers = [0.2]
    assert world.finish('n') is False

    assert world.finish('n') is False
    assert len(world.jev_calls) == 1
    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == 'kept' and record['reason'] == 'jev_different'
    assert record['gap_seconds'] == 300.0 and record['speech_gap_seconds'] == 300.0


def test_reuses_a_wall_record_for_the_same_pair(world):
    _drifted_pair(world)
    world.jev_answers = [0.2, 0.9]
    assert world.finish('n') is False
    assert world.finish('n') is False
    assert len(world.jev_calls) == 1


def test_donor_row_finish_at_decision_time_drives_gap_and_state(world):
    _add(world, 'f1', 0, 0, 600)
    _add(world, 'f2', 700, -120, 1200)
    world.jev_answers = [0.9]
    assert world.finish('f2') is True
    world.raw('f2')['finished_at'] = T0 + timedelta(seconds=1250)
    _add(world, 'f3', 1370, 900, 1700)
    world.jev_answers = [0.9]
    assert world.finish('f3') is True
    assert world.raw('f3')['smart_merge_decision']['gap_seconds'] == 120.0
    assert '2 min after A ended' in world.jev_calls[-1]['state']


def test_merge_keeps_the_existing_decision_record_shape(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.jev_answers = [0.4]
    reads = []
    original = conversations_db.get_conversation

    def counting(uid, cid, **kwargs):
        reads.append(cid)
        return original(uid, cid, **kwargs)

    world.monkeypatch.setattr(conversations_db, 'get_conversation', counting)
    assert world.finish('n') is True
    assert reads[:2] == ['n', 'p'] and sorted(set(reads)) == ['n', 'p']
    donor = world.raw('n')
    record = dict(donor['smart_merge_decision'])
    decided_at = record.pop('decided_at')
    assert isinstance(decided_at, datetime)
    assert record == {
        'version': 1,
        'mode': 'merge',
        'decision': 'merged',
        'reason': 'jev_same',
        'decided_by': 'jev',
        'p_same': 0.4,
        'threshold': 0.35,
        'model': record['model'],
        'question_version': smart_merge.QUESTION_VERSION,
        'candidate_id': 'p',
        'gap_seconds': 300.0,
        'speech_gap_seconds': 300.0,
        'stretch_count': 0,
        'state_sha256': record['state_sha256'],
    }
    assert donor['deleted'] is True and donor['discarded'] is True
    assert donor['sync_merged_into'] == 'p'
    assert donor['smart_merge']['role'] == 'donor' and donor['smart_merge']['survivor_id'] == 'p'
    survivor = world.get(UID, 'p')
    assert [f['id'] for f in survivor['smart_merge']['fragments']] == ['p', 'n']


def test_thirteen_fragment_ledger_rejects_and_never_reads_extra_rows(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    fragments = [
        policy.Fragment(
            f'f{i}', T0 - timedelta(minutes=200 - i), T0 - timedelta(minutes=199 - i), 't', 'o'
        ).as_ledger_entry()
        for i in range(13)
    ]
    world.raw('p')['smart_merge'] = {
        'role': 'survivor',
        'revision': 12,
        'refreshed_revision': 12,
        'fragments': fragments,
    }
    reads = []
    original = conversations_db.get_conversation

    def counting(uid, cid, **kwargs):
        reads.append(cid)
        return original(uid, cid, **kwargs)

    world.monkeypatch.setattr(conversations_db, 'get_conversation', counting)
    assert world.finish('n') is False
    assert reads == ['n', 'p']
    assert world.jev_calls == []


@pytest.mark.parametrize(
    'mutate, reason',
    [
        ({'source': 'other'}, 'not_eligible_source'),
        ({'discarded': True}, 'conversation_not_eligible'),
        ({'starred': True}, 'user_managed'),
        ({'is_locked': True}, 'user_managed'),
        ({'status': 'processing'}, 'conversation_not_eligible'),
        ({'uses_custom_stt': True}, 'refresh_unavailable'),
    ],
)
def test_wallclock_path_keeps_the_new_row_gates(world, mutate, reason, caplog):
    _drifted_pair(world)
    world.raw('n').update(mutate)
    caplog.set_level('INFO', logger=smart_merge.logger.name)
    assert world.finish('n') is False
    assert world.jev_calls == []
    assert any(f'reason={reason}' in r.getMessage() for r in caplog.records)
