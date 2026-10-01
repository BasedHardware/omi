"""Smart merge end to end over the real transaction code and a strict in-memory Firestore.

Jev, conversation processing, retraction/audio seams and the search index are
faked at their module seams; the absorb/claim/complete transactions, the
conversation codec (encryption on), the redirect resolver and the decision
logic run for real. All text is synthetic.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import conversation_smart_merge as config
from database import conversations as conversations_db
from database import smart_merge as smart_merge_db
from database import sync_bridges
from database.firestore_index_registry import CONVERSATIONS_SMART_MERGE_PRECEDING_QUERY, INDEX_ONLY_REQUIREMENTS
from database.legal_holds import DestructiveOperationInProgress
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import smart_merge
from utils.conversations.processing_trigger import ProcessingTrigger
from utils import metrics

UID = 'user-1'
T0 = datetime(2026, 9, 28, 23, 0, tzinfo=timezone.utc)
WORDS = ' '.join(['synthetic'] * 30)


def _path(cid):
    return ('users', UID, 'conversations', cid)


def _segments(cid, minutes):
    seconds = minutes * 60.0
    return [
        {
            'id': f'{cid}-s{i}',
            'text': f'{WORDS} {cid} {i}',
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': i == 0,
            'start': start,
            'end': start + 5.0,
        }
        for i, start in enumerate((0.0, seconds - 5.0))
    ]


class World:
    """Strict Firestore plus recorders for every faked seam."""

    def __init__(self, monkeypatch):
        self.store = StrictFirestore()
        self.monkeypatch = monkeypatch
        self.jev_answers = []
        self.jev_calls = []
        self.processed = []
        self.retracted = []
        self.copied = []
        self.vectors = []
        self.vector_error = None
        self.process_error = None
        self.process_persisted = True
        self.process_disposition = smart_merge.DerivedEffectsDisposition.RUN
        self.retract_error = None
        self.on_ask = None
        for module in (smart_merge_db, sync_bridges, conversations_db):
            monkeypatch.setattr(module, 'get_firestore_client', lambda: self.store)
        # The unmerge follow-up acquires the account-wide destructive gate;
        # run its real transactional logic against the strict store.
        from database import legal_holds as legal_holds_db

        monkeypatch.setattr(
            legal_holds_db, 'account_deletion_firestore_client', lambda firestore_client=None: self.store
        )
        monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda uid, cid: None)
        monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda uid, cid: None)
        monkeypatch.setattr(conversations_db, 'get_conversation', self.get)
        # StrictFirestore stores DELETE_FIELD sentinels literally; record the projection clear instead.
        self.invalidated = []
        monkeypatch.setattr(
            conversations_db,
            '_invalidate_client_processing',
            lambda payload: self.invalidated.append('transcript_segments' in payload),
        )
        monkeypatch.setattr(smart_merge_db, 'find_preceding_conversations', self.preceding)
        monkeypatch.setattr(smart_merge.notification_db, 'get_user_time_zone', lambda uid: 'America/New_York')
        monkeypatch.setattr(smart_merge, 'ask_jev', self.ask)
        monkeypatch.setattr(smart_merge, 'process_conversation', self.process)
        monkeypatch.setattr(smart_merge, 'save_structured_vector', self.save_vector)
        monkeypatch.setattr(smart_merge, 'retract_sync_bridge_source', self.retract)
        monkeypatch.setattr(smart_merge, 'copy_sync_bridge_audio', lambda uid, s, t: self.copied.append((s, t)))
        monkeypatch.setattr(smart_merge, 'is_audio_merge_dispatch_enabled', lambda: False)
        monkeypatch.setattr(conversations_db, 'create_audio_files_from_chunks', lambda uid, cid: [])

    # -- store helpers
    def add(self, cid, start_min, minutes, **extra):
        row = {
            'id': cid,
            'source': 'omi',
            'client_device_id': 'pendant-1',
            'status': 'completed',
            'discarded': False,
            'language': 'en',
            'created_at': T0 + timedelta(minutes=start_min),
            'started_at': T0 + timedelta(minutes=start_min),
            'finished_at': T0 + timedelta(minutes=start_min + minutes),
            'structured': {'title': f'title {cid}', 'overview': f'overview {cid}'},
            'data_protection_level': 'enhanced',
        }
        row.update(extra)
        row['transcript_segments'] = _segments(cid, minutes)
        self.store.rows[_path(cid)] = conversations_db.encode_conversation_for_write(UID, row, 'enhanced')
        return row

    def raw(self, cid):
        return self.store.rows.get(_path(cid))

    def get(self, uid, cid, **_):
        raw = self.raw(cid)
        if raw is None:
            return None
        row = dict(raw, id=cid)
        row['transcript_segments'] = conversations_db._decode_transcript_segments_strict(
            uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
        )
        return row

    def preceding(self, uid, *, source, created_before, limit, firestore_client=None):
        rows = [
            dict(value, id=key[-1])
            for key, value in self.store.rows.items()
            if key[:3] == ('users', uid, 'conversations')
            and value.get('discarded') is False
            and value.get('source') == source
            and value['created_at'] < created_before
        ]
        rows.sort(key=lambda row: row['created_at'], reverse=True)
        return [{k: v for k, v in row.items() if k != 'transcript_segments'} for row in rows[:limit]]

    # -- fakes
    def ask(self, state, questions, *, lane, timeout_seconds, max_attempts):
        self.jev_calls.append({'state': state, 'lane': lane, 'timeout': timeout_seconds, 'attempts': max_attempts})
        if self.on_ask:
            self.on_ask()
        answer = self.jev_answers.pop(0) if self.jev_answers else 0.5
        if answer is None:
            return None
        return SimpleNamespace(noul=lambda name: answer)

    def process(self, uid, language, conversation, *, trigger, persistence_observer, smart_merge_refresh):
        if self.process_error:
            raise self.process_error
        if not self.process_persisted:
            persistence_observer(False)
            return conversation
        assert trigger is ProcessingTrigger.SMART_MERGE
        assert smart_merge_refresh[0] == self.raw(conversation.id)['smart_merge']['revision']
        self.processed.append((conversation.id, len(conversation.transcript_segments)))
        raw = self.raw(conversation.id)
        raw['structured'] = dict(raw['structured'], title=f'refreshed {len(self.processed)}')
        persistence_observer(True)
        return conversation

    def retract(self, uid, cid):
        if self.retract_error:
            raise self.retract_error
        self.retracted.append(cid)

    def save_vector(self, uid, conversation):
        if self.vector_error:
            raise self.vector_error
        self.vectors.append(conversation.id)

    # -- driving
    def finish(self, cid, *, mode='merge', owner='job'):
        self.monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, mode)
        return smart_merge.decide_and_apply(
            UID, cid, mode=config.smart_merge_mode(), trigger=ProcessingTrigger.CAPTURE_END, owner=owner
        )

    def transcript(self, cid):
        return self.get(UID, cid)['transcript_segments']


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'off')
    monkeypatch.delenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, raising=False)
    return World(monkeypatch)


# --------------------------------------------------------------------------- flag


@pytest.mark.parametrize(
    'raw, mode',
    [
        ('', 'merge'),
        ('   ', 'merge'),
        ('merge', 'merge'),
        (' MERGE ', 'merge'),
        ('SHADOW', 'shadow'),
        ('off', 'off'),
        (' Off ', 'off'),
        # The variable is the kill switch: a typo must stop merging, not keep it on.
        ('of', 'off'),
        ('disabled', 'off'),
        ('bogus', 'off'),
        ('false', 'off'),
    ],
)
def test_mode_parsing(monkeypatch, raw, mode):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, raw)
    assert config.smart_merge_mode().value == mode


def test_unset_mode_is_merge_by_default(monkeypatch):
    monkeypatch.delenv(config.SMART_MERGE_MODE_ENV, raising=False)
    assert config.smart_merge_mode() is config.SmartMergeMode.MERGE
    assert config.DEFAULT_SMART_MERGE_MODE is config.SmartMergeMode.MERGE


def test_uid_allowlist(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, 'a, b')
    assert config.smart_merge_uid_allowed('a') and not config.smart_merge_uid_allowed('c')
    monkeypatch.setenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, '')
    assert config.smart_merge_uid_allowed('c')


def test_metric_reason_is_bounded_to_known_values(monkeypatch):
    seen = []
    monkeypatch.setattr(
        metrics.CONVERSATION_SMART_MERGE_DECISION_TOTAL,
        'labels',
        lambda **labels: SimpleNamespace(inc=lambda: seen.append(labels)),
    )
    metrics.record_conversation_smart_merge(mode='merge', decision='keep', reason='arbitrary_per_user_reason')
    assert seen[0]['reason'] == 'other'


@pytest.mark.asyncio
async def test_flag_off_step_is_a_no_op_without_any_io(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'off')

    async def forbidden(*args, **kwargs):
        raise AssertionError('flag off must not schedule work')

    monkeypatch.setattr(smart_merge, 'run_blocking', forbidden)
    assert (
        await smart_merge.smart_merge_step(
            UID, 'n', {'id': 'n', 'status': 'completed'}, trigger=ProcessingTrigger.CAPTURE_END, owner='job'
        )
        is False
    )


@pytest.mark.asyncio
async def test_a_donor_resumes_even_when_the_flag_is_off(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'off')
    calls = []

    async def run_blocking(_executor, function, *args, **kwargs):
        calls.append((function, args, kwargs))

    monkeypatch.setattr(smart_merge, 'run_blocking', run_blocking)
    donor = {'id': 'n', 'smart_merge': {'role': 'donor', 'survivor_id': 'p'}}
    assert await smart_merge.smart_merge_step(UID, 'n', donor, trigger=ProcessingTrigger.CAPTURE_END, owner='job')
    assert calls == [(smart_merge.finish_absorb, (UID, 'n'), {'owner': 'job'})]


# --------------------------------------------------------------------------- shadow


@pytest.mark.parametrize(
    'answer, decision, reason', [(0.35, 'shadow_would_merge', 'jev_same'), (0.34, 'shadow_keep', 'jev_different')]
)
def test_shadow_records_the_decision_and_never_merges(world, answer, decision, reason):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.jev_answers = [answer]
    before = dict(world.raw('p'))

    assert world.finish('n', mode='shadow') is False

    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == decision and record['reason'] == reason and record['mode'] == 'shadow'
    assert record['p_same'] == answer and record['threshold'] == 0.35 and record['candidate_id'] == 'p'
    assert record['gap_seconds'] == 300.0 and record['decided_by'] == 'jev'
    assert len(record['state_sha256']) == 64
    assert world.raw('p') == before and not world.raw('n').get('deleted')
    call = world.jev_calls[0]
    assert call['lane'] == 'conversation_smart_merge' and call['timeout'] == 3.0 and call['attempts'] == 1
    assert 'title p' in call['state'] and 'title n' in call['state']
    # No transcript text or state leaves through the record.
    assert 'synthetic' not in repr(record)


def test_jev_unavailable_fails_open_to_keep(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.jev_answers = [None]
    assert world.finish('n', mode='merge') is False
    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == 'kept' and record['reason'] == 'jev_unavailable' and record['p_same'] is None
    assert not world.raw('n').get('deleted')


@pytest.mark.parametrize('answer', [float('nan'), float('inf'), -0.1, 1.1, '0.9'])
def test_invalid_jev_score_fails_open_without_merging(world, answer):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.jev_answers = [answer]
    assert world.finish('n') is False
    assert not world.raw('n').get('deleted')
    assert world.raw('n')['smart_merge_decision']['p_same'] is None


def test_merge_decision_is_durable_before_absorb(world, monkeypatch):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    real = smart_merge_db.absorb_conversation
    calls = []

    def inspect_record(*args, **kwargs):
        calls.append(world.raw('n').get('smart_merge_decision'))
        return real(*args, **kwargs)

    monkeypatch.setattr(smart_merge_db, 'absorb_conversation', inspect_record)
    assert world.finish('n') is True
    assert calls[0]['decision'] == 'merged'


def test_any_decision_error_fails_open_without_a_record(world, monkeypatch):
    world.add('p', 0, 10)
    world.add('n', 15, 10)

    def broken(*args, **kwargs):
        raise TimeoutError('slow')

    monkeypatch.setattr(smart_merge, 'ask_jev', broken)
    assert world.finish('n') is False
    assert 'smart_merge_decision' not in world.raw('n') and not world.raw('n').get('deleted')


def test_gap_outside_window_never_calls_jev(world):
    world.add('p', 0, 10)
    world.add('n', 71, 10)  # 61-minute gap
    assert world.finish('n') is False
    assert world.jev_calls == [] and 'smart_merge_decision' not in world.raw('n')


def test_busy_immediate_predecessor_blocks_instead_of_skipping_to_an_older_row(world):
    world.add('old', -30, 10)
    world.add('p', 0, 10, status='processing')
    world.add('n', 15, 10)
    assert world.finish('n') is False
    assert world.jev_calls == []


def test_other_device_rows_are_skipped_to_the_same_partition(world):
    world.add('p', 0, 10)
    world.add('other', 11, 2, client_device_id='pendant-2')
    world.add('n', 15, 10)
    world.jev_answers = [0.2]
    world.finish('n', mode='shadow')
    assert world.raw('n')['smart_merge_decision']['candidate_id'] == 'p'


# --------------------------------------------------------------------------- merge


def test_merge_at_threshold_absorbs_redirects_and_refreshes_once(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10, private_cloud_sync_enabled=True)
    world.jev_answers = [0.35]

    assert world.finish('n') is True

    donor = world.raw('n')
    assert donor['deleted'] is True and donor['discarded'] is True and donor['sync_merged_into'] == 'p'
    assert donor['smart_merge']['role'] == 'donor' and donor['smart_merge_decision']['decision'] == 'merged'
    survivor = world.get(UID, 'p')
    assert [s['id'] for s in survivor['transcript_segments']] == ['p-s0', 'p-s1', 'n-s0', 'n-s1']
    assert survivor['transcript_segments'][2]['start'] == pytest.approx(15 * 60.0)
    assert survivor['sync_merged_from'] == ['n'] and survivor['finished_at'] == T0 + timedelta(minutes=25)
    assert survivor['smart_merge']['revision'] == 1 and survivor['smart_merge']['refreshed_revision'] == 1
    assert survivor['sync_content_revision'] == 1
    assert 'refresh_lease' not in survivor['smart_merge']
    assert world.processed == [('p', 4)] and world.vectors == ['p'] and world.invalidated == [True]
    assert world.retracted == ['n'] and world.copied == [('n', 'p')]
    assert donor['sync_bridge_cleaned_revision'] == donor['sync_content_revision'] == 1
    assert donor['sync_bridge_audio_target'] == 'p'
    # Owner detail reads follow the existing redirect contract to the survivor.
    assert conversations_db.resolve_sync_conversation_redirect(UID, 'n') == 'p'


def test_merge_below_threshold_keeps_both(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.jev_answers = [0.34]
    assert world.finish('n') is False
    assert world.raw('n')['smart_merge_decision']['decision'] == 'kept'
    assert not world.raw('n').get('deleted') and 'smart_merge' not in world.raw('p')


def test_replay_reuses_the_sticky_decision_without_asking_again(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.jev_answers = [0.2]
    world.finish('n')
    world.finish('n')
    assert len(world.jev_calls) == 1


def test_user_edit_between_decision_and_transaction_keeps_both(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.on_ask = lambda: world.raw('p').update(starred=True)
    assert world.finish('n') is False
    record = world.raw('n')['smart_merge_decision']
    assert record['decision'] == 'kept' and record['reason'] == 'user_managed'
    assert not world.raw('n').get('deleted') and world.processed == []


def test_processor_snapshot_from_before_absorb_cannot_overwrite_survivor(world, monkeypatch):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    stale = world.get(UID, 'p')
    assert world.finish('n') is True
    monkeypatch.setattr(conversations_db, 'db', world.store)
    assert conversations_db.persist_processing_result_with_lifecycle(UID, stale) is False
    assert len(world.transcript('p')) == 4


def test_user_deleting_the_new_conversation_mid_merge_wins(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.on_ask = lambda: world.raw('n').update(deleted=True)
    assert world.finish('n') is False
    assert 'sync_merged_into' not in world.raw('n') and 'smart_merge' not in world.raw('p')


def test_two_neighbours_racing_for_the_same_row_leave_the_loser_separate(world):
    world.add('p', 0, 10)
    world.add('n1', 15, 10)
    world.add('n2', 30, 10)
    world.monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'merge')
    plan = smart_merge._decide(
        UID, 'n2', mode=config.SmartMergeMode.MERGE, trigger=ProcessingTrigger.CAPTURE_END, owner='job-2'
    )
    assert plan.survivor_id == 'n1'
    assert world.finish('n1', owner='job-1') is True  # n1 folds into p first
    assert smart_merge._absorb(UID, 'n2', plan, mode=config.SmartMergeMode.MERGE, owner='job-2') is False
    assert world.raw('n2')['smart_merge_decision']['reason'] == 'survivor_changed'
    assert not world.raw('n2').get('deleted')


def test_second_absorb_into_a_survivor_that_owes_a_refresh_pays_it_first(world):
    world.add('p', 0, 10)
    world.add('n1', 15, 10)
    world.add('n2', 30, 10)
    world.process_error = RuntimeError('provider down')
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        world.finish('n1', owner='job-1')
    assert world.raw('p')['smart_merge']['revision'] == 1
    assert world.raw('p')['smart_merge']['refreshed_revision'] == 0
    # The lease of the failed attempt is still live; age it out like a crashed worker.
    world.raw('p')['smart_merge']['refresh_lease']['until'] = T0
    world.process_error = None
    assert world.finish('n2', owner='job-2') is True
    assert [cid for cid, _ in world.processed] == ['p', 'p']
    assert world.raw('p')['smart_merge']['refreshed_revision'] == 2


def test_retry_after_partial_failure_finishes_cleanup_and_refresh_exactly_once(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.retract_error = RuntimeError('memory service unavailable')
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        world.finish('n')
    assert world.raw('n')['deleted'] is True and world.processed == []
    world.retract_error = None
    smart_merge.finish_absorb(UID, 'n', owner='job')
    smart_merge.finish_absorb(UID, 'n', owner='job')  # duplicate delivery
    assert world.retracted == ['n'] and world.processed == [('p', 4)]


def test_refresh_that_did_not_persist_keeps_donor_job_retryable(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.process_persisted = False
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        world.finish('n')
    assert world.raw('p')['smart_merge']['refreshed_revision'] == 0
    world.process_persisted = True
    smart_merge.finish_absorb(UID, 'n', owner='job')
    assert world.raw('p')['smart_merge']['refreshed_revision'] == 1


def test_failed_survivor_vector_write_keeps_refresh_retryable(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.vector_error = RuntimeError('vector unavailable')
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        world.finish('n')
    assert world.raw('p')['smart_merge']['refreshed_revision'] == 0
    world.vector_error = None
    smart_merge.finish_absorb(UID, 'n', owner='job')
    assert world.vectors == ['p']
    assert world.raw('p')['smart_merge']['refreshed_revision'] == 1


def test_destructive_gate_defers_retraction_but_not_the_refresh(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.retract_error = DestructiveOperationInProgress(UID)
    assert world.finish('n') is True
    assert 'sync_bridge_cleaned_revision' not in world.raw('n') and world.processed == [('p', 4)]
    world.retract_error = None
    smart_merge.finish_absorb(UID, 'n', owner='job')
    assert world.retracted == ['n'] and world.raw('n')['sync_bridge_cleaned_revision'] == 1


def test_survivor_deleted_after_the_merge_ends_the_resume_quietly(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.process_error = RuntimeError('provider down')
    with pytest.raises(smart_merge.SmartMergeIncomplete):
        world.finish('n')
    world.raw('p')['deleted'] = True
    world.process_error = None
    smart_merge.finish_absorb(UID, 'n', owner='job')
    assert world.processed == []


def test_already_absorbed_donor_is_idempotent_in_the_transaction(world):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    world.finish('n')
    result = smart_merge_db.absorb_conversation(
        UID, 'p', 'n', expected_revision=0, plan=lambda *a: (_ for _ in ()).throw(AssertionError('no replan'))
    )
    assert result.outcome == 'already_absorbed'
    assert [s['id'] for s in world.transcript('p')].count('n-s0') == 1


def test_ambiguous_commit_is_settled_by_the_donor_marker(world, monkeypatch):
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    real = smart_merge_db.absorb_conversation

    def commit_then_fail(*args, **kwargs):
        real(*args, **kwargs)
        raise ConnectionError('commit response lost')

    monkeypatch.setattr(smart_merge_db, 'absorb_conversation', commit_then_fail)
    assert world.finish('n') is True
    assert world.processed == [('p', 4)]


# --------------------------------------------------------------------------- replay


def test_seven_fragment_evening_becomes_one_survivor_with_six_redirects(world):
    """A synthetic evening: seven pendant fragments split by 2-10 minute lulls."""
    starts, lengths = [0, 14, 31, 43, 62, 75, 93], [12, 15, 9, 16, 8, 14, 11]
    ids = [f'f{i}' for i in range(7)]
    for cid, start, length in zip(ids, starts, lengths):
        world.add(cid, start, length)
    for index, cid in enumerate(ids[1:], start=1):
        assert world.finish(cid, owner=f'job-{index}') is True

    survivor = world.get(UID, 'f0')
    assert not survivor.get('deleted')
    for cid in ids[1:]:
        assert world.raw(cid)['sync_merged_into'] == 'f0' and world.raw(cid)['deleted'] is True
        assert conversations_db.resolve_sync_conversation_redirect(UID, cid) == 'f0'
    assert [entry['id'] for entry in survivor['smart_merge']['fragments']] == ids
    assert survivor['smart_merge']['revision'] == survivor['smart_merge']['refreshed_revision'] == 6
    segments = survivor['transcript_segments']
    assert [s['id'] for s in segments] == [f'{cid}-s{i}' for cid in ids for i in (0, 1)]
    assert [s['start'] for s in segments] == sorted(s['start'] for s in segments)
    assert survivor['finished_at'] == T0 + timedelta(minutes=104)
    # One refresh per absorb (no debounce; see the module docstring), on a growing transcript.
    assert world.processed == [('f0', 2 * n) for n in range(2, 8)]
    assert len(world.jev_calls) == 6
    # Later decisions saw the stretch: the last state lists the four fragments before A.
    last_state = world.jev_calls[-1]['state']
    assert last_state.count('\n- ') == 4 and 'Title: title f5' in last_state and 'Title: title f6' in last_state
    visible = [
        key[-1]
        for key, row in world.store.rows.items()
        if key[:3] == ('users', UID, 'conversations') and not row.get('deleted')
    ]
    assert visible == ['f0']


# --------------------------------------------------------------------------- storage


def test_preceding_query_uses_the_registered_spec_and_an_existing_index():
    signature = CONVERSATIONS_SMART_MERGE_PRECEDING_QUERY.index_requirement.signature
    assert signature in {requirement.signature for requirement in INDEX_ONLY_REQUIREMENTS}

    class Query:
        def __init__(self, log):
            self.log = log

        def __getattr__(self, name):
            def step(*args, **kwargs):
                self.log.append((name, args, kwargs))
                return self

            return step

        def stream(self):
            return iter([SimpleNamespace(id='p', to_dict=lambda: {'status': 'completed'})])

    log = []
    client = SimpleNamespace(collection=lambda name: Query(log))
    rows = smart_merge_db.find_preceding_conversations(
        UID, source='omi', created_before=T0, limit=6, firestore_client=client
    )
    assert rows == [{'status': 'completed', 'id': 'p'}]
    filters = [kwargs['filter'] for name, _, kwargs in log if name == 'where']
    assert [(f.field_path, f.op_string) for f in filters] == [
        ('discarded', '=='),
        ('source', '=='),
        ('status', 'in'),
        ('created_at', '<'),
    ]
    assert ('limit', (6,), {}) in log
    selected = next(args[0] for name, args, _ in log if name == 'select')
    assert 'transcript_segments' not in selected


def test_absorb_fenced_while_account_wipe_runs(world):
    """The sibling audit created by absorb is user-scoped data the account wipe
    owns; a live wipe gate must reject the absorb instead of recreating it."""
    from database.legal_holds import LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION

    world.store.rows[('legal_hold_deletion_gates', UID)] = {
        'schema_version': LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
        'uid': UID,
        'kind': 'account_data_wipe',
        'token': 'live-wipe',
        'state': 'running',
        'started_at': datetime.now(timezone.utc),
        'finished_at': None,
    }
    world.add('p', 0, 10)
    world.add('n', 15, 10)
    assert world.finish('n') is False
    # Rejection still records the keep decision, but must not absorb: no donor
    # tombstone, no survivor transcript change, and above all no audit sibling.
    assert ('users', UID, 'smart_merge_audit', 'n') not in world.store.rows
    assert not world.raw('n').get('deleted')
    assert len(world.transcript('p')) == 2
    world.store.rows.pop(('legal_hold_deletion_gates', UID))
    assert world.finish('n') is True  # gate released: absorb proceeds
    assert ('users', UID, 'smart_merge_audit', 'n') in world.store.rows
    assert len(world.transcript('p')) == 4
