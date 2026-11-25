"""Manual-finish first transcript: gating, audio layout, provisional write and failure containment."""

import asyncio
import itertools
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from config import rollout_cohorts
from database import _client as db_client
from database import batch_pipeline_privacy
from database import conversations as conversations_db
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database import conversations_v3
from utils import stt_cap_dispatch

# Imported at module load: record admission is a heavy import, and one made inside a test is
# charged to that test's CPU budget.
from utils.batch_pipeline import live
from utils.conversations.v3 import fast_finish, triggers
from utils.observability.stt_cap_dispatch import DispatchPath
from utils.stt import pre_recorded

UID = 'owner-uid-0000000000000000000'
START = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)


def row(**changes):
    return {
        'recording': True,
        'v3_manual_end_requested': True,
        'status': 'completed',
        'private_cloud_sync_enabled': True,
        'data_protection_level': 'enhanced',
        'started_at': START,
        'language': 'en',
        'transcript_segments': [],
        **changes,
    }


def ref(path, start_frame, offset_frame, frames):
    return {
        'bucket': 'b',
        'path': path,
        'generation': 1,
        'start_frame': start_frame,
        'offset_frame': offset_frame,
        'frames': frames,
    }


@pytest.mark.parametrize(
    'value,member,expected',
    [
        (None, True, True),
        (None, False, False),
        ('cohort', True, True),
        ('on', False, True),
        ('off', True, False),
        ('25', True, False),
    ],
)
def test_rollout_gate(monkeypatch, value, member, expected):
    if value is None:
        monkeypatch.delenv('CONVERSATIONS_V3_FAST_FINISH', raising=False)
    else:
        monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', value)
    asked = []

    def membership(uid, name):
        asked.append((uid, name))
        return member

    monkeypatch.setattr(fast_finish, 'in_rollout_cohort', membership)
    assert fast_finish.enabled(UID) is expected
    assert all(call == (UID, 'v3-fast-finish') for call in asked)


def test_cohort_is_registered_and_empty_without_a_resolver():
    assert rollout_cohorts.COHORT_ENVS[fast_finish.COHORT]() == ''


@pytest.mark.parametrize(
    'change',
    [
        {'v3_manual_end_requested': None},
        {'recording': False},
        {'status': 'processing'},
        {'transcript_segments': [{'id': 'a'}]},
        {'record_projection_revision': 2},
        {'record_audio_partial': {'version': 1}},
        {'is_locked': True},
        {'uses_custom_stt': True},
        {'discarded': True},
        {'private_cloud_sync_enabled': False},
        {'data_protection_level': 'private'},
    ],
)
def test_only_a_sealed_manual_end_recording_without_transcript_is_eligible(change):
    assert fast_finish.eligible(row()) is True
    assert fast_finish.eligible(row(**change)) is False


def test_a_raw_row_is_screened_without_reading_its_stored_transcript():
    # Firestore stores segments compressed (and possibly encrypted) even when there are none, so a
    # raw row's transcript field is truthy for an empty capture. Only a decoded row can say.
    raw = row(transcript_segments=b'x\x9c\x8b\x8e\x05\x00\x01\x15\x00\xb9', transcript_segments_compressed=True)
    assert fast_finish.candidate(raw) is True
    assert fast_finish.candidate(row(deleted=True)) is False
    assert fast_finish.candidate(row(v3_manual_end_requested=None)) is False


def test_unit_pcm_places_references_and_leaves_gaps_silent():
    packs = {'p1': bytes(range(8)), 'p2': bytes(range(100, 108))}
    reads = []

    def read(reference):
        reads.append(reference['path'])
        return packs[reference['path']]

    # p1 frames 1..2 land at frame 0; frame 2 is a gap; p2 frames 0..1 land at frame 3.
    pcm = fast_finish.unit_pcm([ref('p1', 0, 1, 2), ref('p2', 3, 0, 2)], read)
    assert pcm == bytes([2, 3, 4, 5, 0, 0, 100, 101, 102, 103])
    assert reads == ['p1', 'p2']


def test_unit_pcm_refuses_a_short_source():
    with pytest.raises(ValueError):
        fast_finish.unit_pcm([ref('p1', 0, 0, 4)], lambda reference: b'\x00\x00')


@pytest.fixture(autouse=True)
def admitted(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', 'on')
    monkeypatch.setattr(fast_finish, 'funded', lambda uid, seconds, language: True)


_real_run = fast_finish.run


@pytest.fixture(autouse=True)
def privacy_granted(monkeypatch):
    """Most cases exercise an authorized pass; the privacy cases pass their own answer."""

    def run(*args, **kwargs):
        kwargs.setdefault('privacy', lambda: True)
        kwargs.setdefault('fence', lambda transaction: None)
        return _real_run(*args, **kwargs)

    monkeypatch.setattr(fast_finish, 'run', run)


def seg(start, end, **more):
    return {
        'id': f's{start}',
        'text': 'hello',
        'start': start,
        'end': end,
        'speaker': 'SPEAKER_01',
        'speaker_id': 1,
        **more,
    }


def one_unit(duration=10.0):
    return [(START.timestamp(), duration, [ref('p1', 0, 0, 2)])]


def test_writes_segments_on_the_recording_clock_and_cuts_only_after_the_write():
    written, order = {}, []

    def write(uid, cid, segments):
        order.append('write')
        written.update(uid=uid, cid=cid, segments=segments)
        return True

    def transcribe(pcm, language):
        assert language == 'en' and len(pcm) == 4
        return [seg(3.0, 4.0), seg(1.0, 2.0)]

    units = [
        (START.timestamp() + 40.0, 10.0, [ref('p1', 0, 0, 2)]),
        (START.timestamp() + 5.0, 4.5, [ref('p1', 0, 0, 2)]),
    ]
    outcome = fast_finish.run(
        UID,
        'cid',
        row(),
        units,
        lambda reference: bytes(4),
        write=write,
        transcribe=transcribe,
        refresh=row,
        cut=lambda: order.append('cut'),
    )
    assert outcome == 'written'
    # Each unit's outer lines are padded by up to 2 s but never past that unit's own audio
    # (+5..9.5 and +40..50), so every midpoint stays inside the unit the batch projection replaces.
    assert [(s['start'], s['end']) for s in written['segments']] == [
        (5.0, 7.0),
        (8.0, 9.5),
        (40.0, 42.0),
        (43.0, 46.0),
    ]
    assert all(s['speaker_id'] is None and s['speaker'] == 'SPEAKER_01' for s in written['segments'])
    assert (written['uid'], written['cid']) == (UID, 'cid')
    # A cut without the whole-recording transcript would lock a partial window.
    assert order == ['write', 'cut']


@pytest.mark.parametrize('result', [False, 'raise'])
def test_no_cut_when_the_transcript_was_not_written(result):
    def write(uid, cid, segments):
        if result == 'raise':
            raise RuntimeError('down')
        return False

    never = lambda: pytest.fail('must not cut')
    outcome = fast_finish.run(
        UID,
        'cid',
        row(),
        one_unit(),
        lambda r: bytes(4),
        write=write,
        transcribe=lambda pcm, language: [seg(0.0, 1.0)],
        cut=never,
    )
    assert outcome == ('write_error' if result == 'raise' else 'superseded')


def test_a_failed_cut_is_counted_and_keeps_the_transcript():
    outcome = fast_finish.run(
        UID,
        'cid',
        row(),
        one_unit(),
        lambda r: bytes(4),
        write=lambda *a: True,
        transcribe=lambda pcm, language: [seg(0.0, 1.0)],
        cut=boom,
    )
    assert outcome == 'cut_error'


def test_real_transcription_restores_the_offset_of_the_first_word(monkeypatch):
    words = [
        {'timestamp': [12.5, 12.9], 'speaker': 'SPEAKER_00', 'text': 'hello'},
        {'timestamp': [13.0, 13.4], 'speaker': 'SPEAKER_00', 'text': 'there'},
        {'timestamp': [20.0, 20.5], 'speaker': 'SPEAKER_01', 'text': 'hi'},
    ]
    seen = {}

    def provider(pcm, **kwargs):
        seen.update(kwargs, size=len(pcm))
        return words

    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', provider)
    segments = fast_finish._transcribe(bytes(8), 'en')
    assert seen == {
        'sample_rate': 16000,
        'diarize': True,
        'attempts': 1,
        'encoding': 'linear16',
        'channels': 1,
        'language': 'en',
        'size': 8,
    }
    # postprocess_words starts its clock at the first word; the unit clock starts at its audio.
    assert segments[0]['start'] == pytest.approx(12.5, abs=0.02)
    assert segments[-1]['end'] == pytest.approx(20.5, abs=0.02)
    assert len({segment['id'] for segment in segments}) == len(segments) and all(
        segment['text'] for segment in segments
    )


def test_a_member_outside_the_rollout_reads_no_audio(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', 'off')
    never = lambda *args: pytest.fail('must not be called')
    assert fast_finish.run(UID, 'cid', row(), one_unit(), never, write=never, transcribe=never) == 'not_enabled'


@pytest.mark.parametrize('answer', [None, 'refuse', 'raise', 'truthy'])
def test_an_account_that_opted_out_after_capture_reads_no_audio(answer):
    # No check, a refusal, an unavailable authority and anything but an explicit True all fail closed.
    never = lambda *args: pytest.fail('must not read audio, transcribe, write or cut')
    privacy = {'refuse': lambda: False, 'raise': boom, 'truthy': lambda: 1}.get(answer)
    outcome = _real_run(UID, 'cid', row(), one_unit(), never, write=never, transcribe=never, cut=never, privacy=privacy)
    assert outcome == 'privacy_blocked'


def test_a_privacy_change_while_audio_was_read_sends_nothing_to_the_provider():
    never = lambda *args: pytest.fail('must not transcribe, write or cut')
    answers = iter([True, False])
    reads = []
    outcome = _real_run(
        UID,
        'cid',
        row(),
        one_unit(),
        lambda r: reads.append(r) or bytes(4),
        write=never,
        transcribe=never,
        cut=never,
        privacy=lambda: next(answers),
    )
    assert outcome == 'privacy_blocked' and len(reads) == 1


def test_an_authorized_account_is_asked_before_the_audio_and_before_the_provider():
    order = []

    def privacy():
        order.append('privacy')
        return True

    outcome = _real_run(
        UID,
        'cid',
        row(),
        one_unit(),
        lambda r: order.append('audio') or bytes(4),
        write=lambda *a: order.append('write') or True,
        transcribe=lambda pcm, language: order.append('provider') or [seg(0.0, 1.0)],
        privacy=privacy,
    )
    assert outcome == 'written'
    assert order == ['privacy', 'audio', 'privacy', 'provider', 'write']


def test_an_opt_out_during_the_first_unit_never_sends_the_second():
    granted, sent = [True], []

    def transcribe(pcm, language):
        sent.append(pcm)
        granted[0] = False  # the owner opts out while the first request is in flight
        return [seg(0.0, 1.0)]

    units = one_unit() + [(START.timestamp() + 10.0, 10.0, [ref('p2', 0, 0, 2)])]
    outcome = _real_run(
        UID,
        'cid',
        row(),
        units,
        lambda r: bytes(4),
        write=lambda *a: pytest.fail('must not write'),
        transcribe=transcribe,
        cut=lambda: pytest.fail('must not cut'),
        privacy=lambda: granted[0],
    )
    assert outcome == 'privacy_blocked' and len(sent) == 1


class _PrivacyStore:
    def __init__(self, blocked):
        self.blocked, self.checks, self.client = blocked, [], _Doc({})

    def run(self, body):
        store = self

        class Tx:
            def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
                store.checks.append((uid, tuple(conversation_ids), expected_generation))
                if store.blocked:
                    raise RuntimeError('privacy generation changed')
                return expected_generation

        return body(Tx())


@pytest.mark.parametrize('blocked', [False, True])
def test_admission_hands_the_pass_the_batch_privacy_fence_at_its_admitted_generation(monkeypatch, blocked):
    live._FAST_FINISH_STARTED.clear()
    store, outcomes = _PrivacyStore(blocked), []
    monkeypatch.setattr(fast_finish, 'enabled', lambda uid: True)
    monkeypatch.setattr(
        conversations_db, 'get_conversation', lambda uid, cid, **kwargs: row(_recovery_transcript_decoded=True)
    )

    fenced, transaction = [], object()

    def fence_read(client, tx, uid, **kwargs):
        fenced.append((tx, uid, kwargs))
        if blocked:
            raise BatchPrivacyBlocked('recording_privacy_changed')
        return kwargs['expected_generation']

    def run(uid, cid, row_, units_, read, *, privacy, fence, **kwargs):
        outcomes.append(fast_finish._privacy_allows(privacy))
        try:
            fence(transaction)
            outcomes.append('published')
        except BatchPrivacyBlocked:
            outcomes.append('refused')
        return 'privacy_blocked'

    monkeypatch.setattr(fast_finish, 'run', run)
    monkeypatch.setattr(batch_pipeline_privacy, 'assert_batch_write_allowed', fence_read)
    monkeypatch.setattr(db_client, 'get_firestore_client', lambda: object())

    async def admit():
        await live._manual_finish_admitted(store, UID, 'cid', row(), [UNIT, UNIT], object(), b'k', privacy_generation=7)
        await asyncio.gather(*list(live._FAST_FINISH_TASKS))
        await asyncio.sleep(0)

    asyncio.run(admit())
    assert outcomes == [not blocked, 'refused' if blocked else 'published']
    assert store.checks == [(UID, ('cid',), 7)]
    # The publication fence reads inside the writer's transaction, at the admitted generation, minting nothing.
    assert fenced == [
        (transaction, UID, {'conversation_ids': ('cid',), 'expected_generation': 7, 'allow_token_mint': False})
    ]


def test_nothing_is_sent_to_the_provider_without_consent_and_funding():
    never = lambda *args: pytest.fail('must not read audio, transcribe or write')
    asked = []

    def authorize(uid, seconds, language):
        asked.append((uid, seconds, language))
        return False

    units = one_unit(7.0) + one_unit(3.0)
    outcome = fast_finish.run(UID, 'cid', row(), units, never, write=never, transcribe=never, authorize=authorize)
    assert outcome == 'not_funded'
    assert asked == [(UID, 10.0, 'en')]


def test_the_funding_gate_is_the_shared_batch_admission(monkeypatch):
    monkeypatch.undo()
    seen = {}

    def admission(uid, seconds, provider, *, lane, path):
        seen.update(uid=uid, seconds=seconds, provider=provider, lane=lane, path=path)
        return False, 'consent_denied'

    monkeypatch.setattr(stt_cap_dispatch, 'sync_admission', admission)
    monkeypatch.setattr(pre_recorded, 'get_prerecorded_service', lambda language: ('parakeet', None, 'm'))
    assert fast_finish.funded(UID, 12.0, 'en') is False
    assert seen == {
        'uid': UID,
        'seconds': 12.0,
        'provider': 'parakeet',
        'lane': 'batch',
        'path': DispatchPath.BATCH_PROVIDER,
    }


def test_a_canonical_transcript_that_already_landed_wins():
    refused = lambda uid, cid, segments: False
    transcribe = lambda pcm, language: [seg(0.0, 1.0)]
    assert (
        fast_finish.run(UID, 'cid', row(), one_unit(), lambda r: bytes(4), write=refused, transcribe=transcribe)
        == 'superseded'
    )


CHANGES = [{'deleted': True}, {'discarded': True}, {'is_locked': True}, {'record_projection_revision': 1}]


@pytest.mark.parametrize('change', CHANGES + [{'data_protection_level': 'private'}])
def test_a_row_that_changed_since_admission_sends_nothing_to_the_provider(change):
    never = lambda *args: pytest.fail('must not read audio, transcribe, write or cut')
    outcome = fast_finish.run(
        UID, 'cid', row(), one_unit(), never, write=never, transcribe=never, refresh=lambda: row(**change), cut=never
    )
    assert outcome == 'ineligible'


@pytest.mark.parametrize('change', CHANGES)
def test_a_row_that_changed_during_the_provider_call_is_not_written(change):
    never = lambda *args: pytest.fail('must not write or cut')
    reads = iter([row(), row(**change)])
    outcome = fast_finish.run(
        UID,
        'cid',
        row(),
        one_unit(),
        lambda r: bytes(4),
        write=never,
        transcribe=lambda pcm, language: [seg(0.0, 1.0)],
        refresh=lambda: next(reads),
        cut=never,
    )
    assert outcome == 'superseded'


def boom(*args, **kwargs):
    raise RuntimeError('down')


@pytest.mark.parametrize(
    'read,transcribe,write,expected',
    [
        (boom, None, None, 'audio_error'),
        (lambda r: bytes(4), boom, None, 'provider_error'),
        (lambda r: bytes(4), lambda pcm, language: [], None, 'empty'),
        (lambda r: bytes(4), lambda pcm, language: [seg(0.0, 1.0)], boom, 'write_error'),
    ],
)
def test_failures_are_counted_and_never_raise(read, transcribe, write, expected):
    never = lambda *args: pytest.fail('must not write')
    outcome = fast_finish.run(UID, 'cid', row(), one_unit(), read, write=write or never, transcribe=transcribe or boom)
    assert outcome == expected


def test_an_unexpected_failure_is_its_own_outcome():
    assert (
        fast_finish.run(
            UID, 'cid', row(), one_unit(), lambda r: bytes(4), write=lambda *a: True, transcribe=boom, refresh=boom
        )
        == 'error'
    )


def test_ineligible_and_long_recordings_are_skipped_without_reading_audio():
    never = lambda *args: pytest.fail('must not be called')
    assert (
        fast_finish.run(UID, 'cid', row(v3_manual_end_requested=None), one_unit(), never, write=never, transcribe=never)
        == 'ineligible'
    )
    long_units = one_unit(fast_finish.MAX_SECONDS + 1)
    assert fast_finish.run(UID, 'cid', row(), long_units, never, write=never, transcribe=never) == 'too_long'
    assert fast_finish.run(UID, 'cid', row(), [], never, write=never, transcribe=never) == 'too_long'
    many = one_unit(1.0) * (fast_finish.MAX_UNITS + 1)
    assert fast_finish.run(UID, 'cid', row(), many, never, write=never, transcribe=never) == 'too_long'


class _Doc:
    def __init__(self, data):
        self.data = data

    def collection(self, *_):
        return self

    def document(self, *_):
        return self

    def get(self):
        return self

    def to_dict(self):
        return self.data


class _Store:
    def __init__(self, data):
        self.client = _Doc(data)


def _admit(monkeypatch, current, units, *, fast='written', promoted=True, member=True, decoded=None):
    live._FAST_FINISH_STARTED.clear()
    calls = {'fast': 0, 'promote': 0, 'cut': 0}
    decoded = current if decoded is None else decoded

    def run(uid, cid, row_, units_, read, *, refresh, cut, privacy, fence):
        calls['fast'] += 1
        # The pass is handed a decoded row, never admission's raw snapshot.
        expected = dict(decoded, _recovery_transcript_decoded=True)
        assert row_ == expected and refresh() == expected
        assert units_ is not units and units_[0][2] is not units[0][2]
        # A single unit is cut by admission before the pass; several units only by the pass itself.
        # A promoted single unit still gets the manual-end wake after a written pass.
        assert (cut is None) is (len(units) == 1 and not promoted)
        if cut is not None and fast == 'written':
            cut()
        return fast

    def promote(uid, cid, firestore_client=None):
        calls['promote'] += 1
        return promoted

    def changed(uid, cid, *, manual_end=False):
        assert manual_end is True
        calls['cut'] += 1

    monkeypatch.setattr(fast_finish, 'run', run)
    monkeypatch.setattr(fast_finish, 'enabled', lambda uid: member)
    monkeypatch.setattr(conversations_v3, 'promote_manual_end', promote)
    monkeypatch.setattr(
        conversations_db,
        'get_conversation',
        lambda uid, cid, **kwargs: dict(decoded, _recovery_transcript_decoded=True),
    )
    monkeypatch.setattr(triggers, 'changed', changed)

    async def admit():
        await live._manual_finish_admitted(_Store(current), UID, 'cid', current, units, object(), b'k')
        await asyncio.gather(*list(live._FAST_FINISH_TASKS))
        await asyncio.sleep(0)

    asyncio.run(admit())
    assert not live._FAST_FINISH_TASKS
    return calls


UNIT = (0.0, 1.0, [{'bucket': 'b', 'path': 'p', 'generation': 1}])


@pytest.mark.parametrize('fast,wakes', [('written', 1), ('provider_error', 0), ('not_funded', 0)])
def test_admission_cuts_a_single_unit_itself_before_the_pass(monkeypatch, fast, wakes):
    # The cut is stored before the pass; a written pass sends its own manual-end wake, since the
    # writer's plain wake can share an owner-minute task name with a reconcile that already ran.
    assert _admit(monkeypatch, row(), [UNIT], fast=fast) == {'fast': 1, 'promote': 1, 'cut': wakes}


def test_a_single_unit_that_was_not_promoted_gets_no_manual_end_wake(monkeypatch):
    assert _admit(monkeypatch, row(), [UNIT], promoted=False) == {'fast': 1, 'promote': 1, 'cut': 0}


@pytest.mark.parametrize('fast,cuts', [('written', 1), ('provider_error', 0), ('superseded', 0), ('not_funded', 0)])
def test_several_units_are_cut_only_by_a_pass_that_wrote_the_whole_transcript(monkeypatch, fast, cuts):
    # Several units project one at a time: cutting on the first would lock a partial window.
    assert _admit(monkeypatch, row(), [UNIT, UNIT], fast=fast) == {'fast': 1, 'promote': 0, 'cut': cuts}


@pytest.mark.parametrize('units,promotes', [([UNIT], 1), ([UNIT, UNIT], 0)])
def test_an_owner_outside_the_rollout_never_starts_a_pass(monkeypatch, units, promotes):
    assert _admit(monkeypatch, row(), units, member=False) == {'fast': 0, 'promote': promotes, 'cut': 0}


def test_the_pass_gets_the_decoded_row_for_a_raw_row_with_stored_bytes(monkeypatch):
    # The raw snapshot's transcript bytes are truthy for an empty capture; the pass must still start
    # and must be handed the decoded row, whose transcript is really empty.
    raw = row(transcript_segments=b'stored-bytes', transcript_segments_compressed=True)
    assert _admit(monkeypatch, raw, [UNIT, UNIT], decoded=row()) == {'fast': 1, 'promote': 0, 'cut': 1}


def test_an_undecodable_stored_transcript_is_not_treated_as_empty(monkeypatch):
    live._FAST_FINISH_STARTED.clear()
    seen = []
    monkeypatch.setattr(fast_finish, 'enabled', lambda uid: True)
    monkeypatch.setattr(
        fast_finish,
        'run',
        lambda uid, cid, row_, *a, **k: seen.append(row_)
        or fast_finish._run(
            uid,
            cid,
            row_,
            [],
            None,
            write=None,
            transcribe=None,
            refresh=k['refresh'],
            cut=None,
            authorize=None,
            privacy=None,
            fence=None,
        ),
    )
    monkeypatch.setattr(
        conversations_db, 'get_conversation', lambda uid, cid, **kwargs: row(_recovery_transcript_decoded=False)
    )

    async def admit():
        await live._manual_finish_admitted(_Store(row()), UID, 'cid', row(), [UNIT, UNIT], object(), b'k')
        await asyncio.gather(*list(live._FAST_FINISH_TASKS))
        await asyncio.sleep(0)

    asyncio.run(admit())
    # The pass is handed no row at all, which is ineligible before any audio is read.
    assert seen == [{}]


def test_the_default_writer_rechecks_the_stored_row_inside_its_transaction(monkeypatch):
    seen = {}

    fence = lambda transaction: None

    def writer(uid, cid, segments, *, require_row, guard):
        seen.update(uid=uid, cid=cid, count=len(segments), require_row=require_row, guard=guard)
        return False

    monkeypatch.setattr(conversations_db, 'update_conversation_segments', writer)
    outcome = fast_finish.run(
        UID,
        'cid',
        row(),
        one_unit(),
        lambda r: bytes(4),
        transcribe=lambda pcm, language: [seg(0.0, 1.0)],
        fence=fence,
    )
    assert outcome == 'superseded'
    assert seen['require_row'] is fast_finish.candidate and (seen['uid'], seen['cid'], seen['count']) == (UID, 'cid', 1)
    assert seen['guard'] is fence


def test_an_opt_out_during_the_only_provider_request_publishes_nothing(monkeypatch):
    # The publication transaction asks the batch privacy fence itself; it refuses after the owner
    # opted out while the last (here the only) unit was with the provider.
    def writer(uid, cid, segments, *, require_row, guard):
        guard(object())
        pytest.fail('must not write after the fence refused')

    def refused(transaction):
        raise BatchPrivacyBlocked('recording_privacy_changed')

    monkeypatch.setattr(conversations_db, 'update_conversation_segments', writer)
    outcome = _real_run(
        UID,
        'cid',
        row(),
        one_unit(),
        lambda r: bytes(4),
        transcribe=lambda pcm, language: [seg(0.0, 1.0)],
        cut=lambda: pytest.fail('must not cut'),
        privacy=lambda: True,
        fence=refused,
    )
    assert outcome == 'privacy_blocked'


def test_the_default_writer_never_publishes_without_the_fence():
    never = lambda *args: pytest.fail('must not read audio or transcribe')
    outcome = _real_run(UID, 'cid', row(), one_unit(), never, transcribe=never, privacy=lambda: True)
    assert outcome == 'privacy_blocked'


@pytest.mark.parametrize(
    'admitted,expected',
    [
        ({'outcome': 'batch', 'job_id': 'bp_x'}, True),
        ({'outcome': 'batch', 'job_id': 'bp_other'}, False),
        ({'outcome': 'busy'}, False),
        ({'outcome': 'completed', 'result': {}}, False),
        (None, False),
        (True, False),
    ],
)
def test_the_hook_runs_only_when_this_intake_owns_the_units(admitted, expected):
    assert live._admitted_these_units(admitted, 'bp_x') is expected


@pytest.mark.parametrize('current', [row(v3_manual_end_requested=None), row(recording=False)])
def test_a_natural_end_or_legacy_capture_is_untouched(monkeypatch, current):
    assert _admit(monkeypatch, current, [UNIT]) == {'fast': 0, 'promote': 0, 'cut': 0}


def test_the_kill_switch_stops_the_cut_and_the_fast_pass(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_BATCH_MANUAL_END', 'off')
    assert _admit(monkeypatch, row(), [UNIT]) == {'fast': 0, 'promote': 0, 'cut': 0}


def _admit_many(monkeypatch, ids, release):
    live._FAST_FINISH_STARTED.clear()
    started = []

    def run(uid, cid, *args, **kwargs):
        started.append(cid)
        release.wait(5)
        return 'written'

    monkeypatch.setattr(fast_finish, 'run', run)
    monkeypatch.setattr(fast_finish, 'enabled', lambda uid: True)
    monkeypatch.setattr(
        conversations_db, 'get_conversation', lambda uid, cid, **kwargs: row(_recovery_transcript_decoded=True)
    )

    async def admit():
        for cid in ids:
            await live._manual_finish_admitted(_Store(row()), UID, cid, row(), [UNIT, UNIT], object(), b'k')
        release.set()
        await asyncio.gather(*list(live._FAST_FINISH_TASKS))
        await asyncio.sleep(0)

    asyncio.run(admit())
    return started


def test_a_retried_admission_starts_one_fast_pass(monkeypatch):
    assert _admit_many(monkeypatch, ['cid', 'cid'], threading.Event()) == ['cid']


def test_at_most_two_passes_run_at_once(monkeypatch):
    # Both slots are taken: a third pass is counted busy and never reads audio.
    assert live._FAST_FINISH_SLOTS.acquire(blocking=False) and live._FAST_FINISH_SLOTS.acquire(blocking=False)
    try:
        assert _admit_many(monkeypatch, ['c'], threading.Event()) == []
    finally:
        live._FAST_FINISH_SLOTS.release()
        live._FAST_FINISH_SLOTS.release()
    assert _admit_many(monkeypatch, ['d'], threading.Event()) == ['d']


def test_admission_survives_a_broken_hook(monkeypatch):
    live._FAST_FINISH_STARTED.clear()
    monkeypatch.setattr(fast_finish, 'candidate', boom)
    monkeypatch.setattr(fast_finish, 'candidate_rejection', boom)
    asyncio.run(live._manual_finish_admitted(_Store(row()), UID, 'cid', row(), [UNIT, UNIT], object(), b'k'))


# --- Why a manual finish never started a fast pass -------------------------------------------------


def _reference_candidate(row_):
    """``candidate`` as it read before ``candidate_rejection``: the oracle for the equivalence test."""
    return bool(
        row_.get('recording') is True
        and (row_.get('v3_manual_end_requested') is True or row_.get('v3_manual_end') is True)
        and row_.get('status') == 'completed'
        and row_.get('private_cloud_sync_enabled')
        and row_.get('data_protection_level', 'enhanced') in {'standard', 'enhanced'}
        and not row_.get('record_projection_revision')
        and not row_.get('record_audio_partial')
        and not any(row_.get(key) for key in ('deleted', 'discarded', 'is_locked', 'uses_custom_stt'))
    )


@pytest.mark.parametrize(
    'change,reason',
    [
        ({}, None),
        ({'recording': False}, 'not_recording'),
        ({'recording': 'true'}, 'not_recording'),
        ({'v3_manual_end_requested': None}, 'no_manual_end'),
        ({'v3_manual_end_requested': None, 'v3_manual_end': True}, None),
        ({'status': 'in_progress'}, 'status_in_progress'),
        ({'status': 'processing'}, 'status_processing'),
        ({'status': 'merging'}, 'status_other'),
        ({'status': 'failed'}, 'status_other'),
        ({'status': None}, 'status_other'),
        ({'status': 'an-unbounded-value'}, 'status_other'),
        ({'private_cloud_sync_enabled': False}, 'no_private_cloud_sync'),
        ({'data_protection_level': 'private'}, 'protection_level'),
        ({'data_protection_level': 'standard'}, None),
        ({'record_projection_revision': 3}, 'projection_revision'),
        ({'record_audio_partial': True}, 'audio_partial'),
        ({'deleted': True}, 'deleted'),
        ({'discarded': True}, 'discarded'),
        ({'is_locked': True}, 'locked'),
        ({'uses_custom_stt': True}, 'custom_stt'),
        # The first failing predicate wins.
        ({'recording': False, 'deleted': True}, 'not_recording'),
        ({'status': 'processing', 'is_locked': True}, 'status_processing'),
        ({'deleted': True, 'uses_custom_stt': True}, 'deleted'),
    ],
)
def test_candidate_rejection_names_the_first_failing_predicate(change, reason):
    current = row(**change)
    assert fast_finish.candidate_rejection(current) == reason
    assert reason is None or reason in fast_finish.SKIP_REASONS
    assert fast_finish.candidate(current) is (reason is None)


def test_candidate_matches_its_previous_definition_on_every_field_combination():
    values = {
        'recording': (True, False, None),
        'v3_manual_end_requested': (True, None),
        'v3_manual_end': (True, None),
        'status': ('completed', 'in_progress', 'processing', 'failed', None),
        'private_cloud_sync_enabled': (True, False),
        'data_protection_level': ('enhanced', 'standard', 'private', None),
        'record_projection_revision': (None, 1),
        'record_audio_partial': (None, True),
        'deleted': (None, True),
        'discarded': (None, True),
        'is_locked': (None, True),
        'uses_custom_stt': (None, True),
    }
    keys = list(values)
    checked = 0
    for combination in itertools.product(*(values[key] for key in keys)):
        current = {key: value for key, value in zip(keys, combination) if value is not None}
        reason = fast_finish.candidate_rejection(current)
        assert fast_finish.candidate(current) is _reference_candidate(current) is (reason is None)
        assert reason is None or reason in fast_finish.SKIP_REASONS
        checked += 1
    assert checked == 3 * 2 * 2 * 5 * 2 * 4 * 2**6


def _skipped(reason):
    return fast_finish.SKIPPED.labels(reason)._value.get()


def _manual_end(reason):
    from utils.conversations.v3 import metrics as v3_metrics

    return v3_metrics.BATCH_MANUAL_END.labels(reason)._value.get()


@pytest.mark.parametrize(
    'mode,change,units,reason',
    [
        ('off', {}, [UNIT], 'mode_off'),
        ('off', {'deleted': True}, [UNIT, UNIT], 'mode_off'),
        ('cohort', {'status': 'processing'}, [UNIT, UNIT], 'status_processing'),
        ('on', {'uses_custom_stt': True}, [UNIT], 'custom_stt'),
        ('cohort', {'private_cloud_sync_enabled': False}, [UNIT, UNIT], 'no_private_cloud_sync'),
    ],
)
def test_an_early_return_counts_its_reason(monkeypatch, mode, change, units, reason):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', mode)
    before, deferred = _skipped(reason), _manual_end('multi_unit_deferred')
    # A skip never starts the pass; a single unit is still promoted, several are deferred as before.
    assert _admit(monkeypatch, row(**change), units) == {'fast': 0, 'promote': int(len(units) == 1), 'cut': 0}
    assert _skipped(reason) == before + 1
    assert _manual_end('multi_unit_deferred') == deferred + int(len(units) > 1)


def test_a_second_admission_counts_already_started(monkeypatch):
    before = _skipped('already_started')
    assert _admit_many(monkeypatch, ['cid', 'cid'], threading.Event()) == ['cid']
    assert _skipped('already_started') == before + 1


def test_a_started_pass_counts_no_skip(monkeypatch):
    before = {reason: _skipped(reason) for reason in fast_finish.SKIP_REASONS}
    assert _admit(monkeypatch, row(), [UNIT, UNIT]) == {'fast': 1, 'promote': 0, 'cut': 1}
    assert {reason: _skipped(reason) for reason in fast_finish.SKIP_REASONS} == before


def test_cloud_run_sync_scrapes_fast_finish_skips():
    # FC-metric-dropped-by-scrape-allowlist: a dropped counter reads as a healthy zero.
    profile = Path(__file__).resolve().parents[2] / 'deploy' / 'cloud_run_gmp_sync.yaml'
    rules = yaml.safe_load(profile.read_text())['spec']['endpoints'][0]['metricRelabeling']
    (rule,) = [r for r in rules if r['action'] == 'keep' and r['sourceLabels'] == ['__name__']]
    for counter in (fast_finish.SKIPPED, fast_finish.OUTCOMES):
        samples = [s for family in counter.collect() for s in family.samples if s.name.endswith('_total')]
        assert samples and all(re.fullmatch(rule['regex'], s.name) for s in samples)
    reasons = {s.labels['reason'] for f in fast_finish.SKIPPED.collect() for s in f.samples}
    assert reasons == set(fast_finish.SKIP_REASONS)
