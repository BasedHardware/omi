"""The end-of-recording marker: shape, proof rule, store, admission and ledger end fields."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from database import capture_end as store
from database import pipeline_ledger as ledger
from tests.unit.test_pipeline_ledger import _FakeClient, _FakeTransaction
from models.message_event import MessageServiceStatusEvent
from utils.conversations import lifecycle
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.sync import capture_end
from utils.sync import processing_hold as hold


def marker(**changes):
    base = dict(end_type='user_initiated', last_speech_at=1000.0, end_decided_at=1002.0, sent_at=1010.0, pending_wals=0)
    return capture_end.normalize(**{**base, **changes}, received_at=5000.0)


def test_normalize_keeps_device_clocks_and_maps_the_end_to_server_time():
    stored = marker()
    assert stored['last_speech_at'] == 1000.0 and stored['end_decided_at'] == 1002.0
    # The phone decided 8 s before it sent; the server received at 5000.
    assert stored['end_at'] == 4992.0 and stored['end_observed_at'] == 5000.0
    assert stored['end_type'] == 'user_initiated'


def test_a_disconnect_is_not_user_intent():
    assert marker(end_type='disconnect')['end_type'] == 'unknown'


def test_a_fast_phone_clock_cannot_place_the_end_in_the_future():
    assert marker(sent_at=1001.0, end_decided_at=1002.0)['end_at'] == 5000.0


@pytest.mark.parametrize(
    'changes',
    [
        {'end_type': 'jev_initiated'},
        {'last_speech_at': 2000.0},
        {'end_decided_at': 3000.0},
        {'last_speech_at': float('nan')},
        {'pending_wals': -1},
        {'pending_wals': True},
        {'last_speech_at': 1.0, 'end_decided_at': 1002.0, 'sent_at': 900000.0},
    ],
)
def test_malformed_markers_are_refused(changes):
    with pytest.raises(ValueError):
        marker(**changes)


def test_proof_needs_no_pending_files_content_through_last_speech_and_nothing_after_the_end():
    stored = marker()
    assert capture_end.proof({'finished_at': 999.0}, stored) == 'proven'
    assert capture_end.proof({'finished_at': 1006.9}, stored) == 'proven'
    assert capture_end.proof({'finished_at': 990.0}, stored) == 'content_behind'
    assert capture_end.proof({'finished_at': 1100.0}, stored) == 'resumed'
    assert capture_end.proof({'finished_at': 999.0}, {**stored, 'pending_wals': 2}) == 'pending'
    assert capture_end.proof({'finished_at': 999.0}, None) == 'absent'
    assert capture_end.proof({}, stored) == 'absent'


def _shifted(finished, *, shift=171.0, recorded_end=None):
    """A row as the sync writer stores it for a phone running ``shift`` seconds ahead."""
    state = {'content_clock_offset': shift, 'content_clock_end': finished if recorded_end is None else recorded_end}
    return {'finished_at': finished, hold.FIELD: state}


def test_a_phone_clock_171_seconds_ahead_still_proves_a_complete_recording():
    # Phone times are 171 s ahead; the stored row end was shifted back by the same 171 s.
    stored = marker(last_speech_at=1171.0, end_decided_at=1173.0, sent_at=1181.0)
    assert capture_end.proof(_shifted(999.0), stored) == 'proven'
    assert capture_end.proof(_shifted(1006.9), stored) == 'proven'
    # Same skew, content still short of the last speech, or later than the declared end.
    assert capture_end.proof(_shifted(990.0), stored) == 'content_behind'
    assert capture_end.proof(_shifted(1100.0), stored) == 'resumed'
    # Without the recorded shift the comparison is not reliable and the quiet wait stays.
    assert capture_end.proof({'finished_at': 999.0}, stored) == 'content_behind'
    # The row's end moved after the shift was recorded: the shift no longer describes it.
    assert capture_end.proof(_shifted(999.0, recorded_end=950.0), stored) == 'clock_unknown'
    assert capture_end.HOLD_FIELD == hold.FIELD


def test_the_hold_keeps_the_shift_only_for_the_arrival_that_sets_the_row_end():
    shifted = hold.activity_patch({'finished_at': 999.0}, 2000, clock_offset=171.0, owns_end=True)
    assert (shifted[hold.CLOCK_OFFSET_FIELD], shifted[hold.CLOCK_END_FIELD]) == (171.0, 999.0)
    row = {'finished_at': 999.0, hold.FIELD: shifted}
    # An earlier file arriving late does not set the end and leaves the shift alone.
    kept = hold.activity_patch(row, 2100, clock_offset=0.0, owns_end=False)
    assert kept[hold.CLOCK_OFFSET_FIELD] == 171.0
    # A later, unshifted arrival sets the end: the old shift no longer applies.
    cleared = hold.activity_patch({**row, 'finished_at': 1500.0}, 2200, clock_offset=0.0, owns_end=True)
    assert hold.CLOCK_OFFSET_FIELD not in cleared and hold.CLOCK_END_FIELD not in cleared
    # A row that was never shifted carries neither field.
    assert hold.CLOCK_OFFSET_FIELD not in hold.activity_patch({'finished_at': 999.0}, 2000, owns_end=True)


def test_a_stop_with_no_detected_speech_is_stored_honestly_and_never_proves_the_end():
    stored = marker(last_speech_at=None)
    assert stored['last_speech_at'] is None and stored['end_type'] == 'user_initiated'
    assert stored['end_at'] == 4992.0
    # An accepted upload is not yet a transcript: with no speech time nothing shows the content landed.
    assert capture_end.proof({'finished_at': 999.0}, stored) == 'no_speech_clock'
    assert capture_end.proof({}, stored) == 'no_speech_clock'
    assert capture_end.proof({'finished_at': 999.0}, {**stored, 'pending_wals': 1}) == 'pending'
    with pytest.raises(ValueError):
        marker(last_speech_at=None, end_decided_at=1.0, sent_at=900000.0)


def test_trace_header_is_parsed_with_a_closed_gate_and_never_raises():
    assert capture_end.parse_trace('sealed=100;first=110;gate=background;attempts=3', received_at=400) == (
        'background',
        300,
    )
    assert capture_end.parse_trace('sealed=100;gate=made_up', received_at=90) == ('other', 0.0)
    for bad in (None, '', 'gate=none', 'sealed=abc', 'sealed=-4', 'x' * 500):
        assert capture_end.parse_trace(bad, received_at=400) is None
    capture_end.observe_trace('sealed=100;gate=none', received_at=400)
    capture_end.observe_trace('nonsense', received_at=400)


class _UpdatingTransaction(_FakeTransaction):
    def update(self, ref, patch):
        self.store[ref.path] = {**self.store[ref.path], **patch}


class _Client(_FakeClient):
    def transaction(self):
        return _UpdatingTransaction(self.store)


SESSION = 'users/u/recording_sessions/s'


def test_store_writes_only_onto_an_existing_session_of_this_owner():
    client = _Client()
    assert store.store('u', 's', marker(), firestore_client=client) == ('unbound', None)
    client.store[SESSION] = {'uid': 'other', 'conversation_id': 'c'}
    assert store.store('u', 's', marker(), firestore_client=client) == ('unbound', None)
    client.store[SESSION] = {'uid': 'u', 'conversation_id': 'c', 'recording_session_id': 's'}
    assert store.store('u', 's', marker(pending_wals=2), firestore_client=client) == ('stored', 'c')
    assert client.store[SESSION]['conversation_id'] == 'c'
    assert store.load('u', 's', firestore_client=client)['pending_wals'] == 2
    assert store.load('other', 's', firestore_client=client) is None


def test_a_resend_lowers_the_pending_count_and_keeps_the_first_observed_end():
    client = _Client()
    client.store[SESSION] = {'uid': 'u', 'conversation_id': 'c'}
    first = marker(pending_wals=2)
    store.store('u', 's', first, firestore_client=client)
    later = capture_end.normalize(
        end_type='user_initiated',
        last_speech_at=1000.0,
        end_decided_at=1002.0,
        sent_at=1300.0,
        pending_wals=0,
        received_at=5300.0,
    )
    assert store.store('u', 's', later, firestore_client=client) == ('stored', 'c')
    saved = client.store[SESSION]['capture_end']
    assert saved['pending_wals'] == 0 and saved['end_observed_at'] == first['end_observed_at']
    assert store.store('u', 's', later, firestore_client=client) == ('duplicate', 'c')
    assert store.store('u', 's', marker(pending_wals=5), firestore_client=client) == ('duplicate', 'c')


def test_a_later_end_replaces_an_earlier_one_and_an_older_one_is_stale():
    client = _Client()
    client.store[SESSION] = {'uid': 'u', 'conversation_id': 'c'}
    store.store('u', 's', marker(), firestore_client=client)
    resumed = marker(last_speech_at=2000.0, end_decided_at=2002.0, sent_at=2010.0, end_type='silence_backstop')
    assert store.store('u', 's', resumed, firestore_client=client) == ('stored', 'c')
    assert client.store[SESSION]['capture_end']['end_type'] == 'silence_backstop'
    assert store.store('u', 's', marker(), firestore_client=client) == ('stale', 'c')


def row():
    return {
        'finished_at': 999.0,
        'transcript_segments': [{'text': 'word ' * 100, 'start': 0, 'end': 60}],
        hold.FIELD: {'pending_since': 100, 'last_content_at': 100, 'held': True},
    }


def test_admission_skips_the_quiet_wait_only_on_end_proof():
    asked = Mock(return_value=True)
    assert hold.admission(row(), {'first_pending_at': 100}, now=130, end_proven=asked) == ('end_proof', None)
    asked.assert_called_once()
    assert hold.admission(row(), {'first_pending_at': 100}, now=130, end_proven=lambda: False) == ('quiet_wait', 700)
    assert hold.admission(row(), {'first_pending_at': 100}, now=130) == ('quiet_wait', 700)


def test_admission_does_not_ask_for_proof_when_it_would_not_wait():
    asked = Mock(return_value=True)
    assert hold.admission(row(), {'first_pending_at': 100}, now=700, end_proven=asked) == ('ready', None)
    assert hold.admission(row(), {'first_pending_at': 100}, now=3700, end_proven=asked) == ('max_hold', None)
    asked.assert_not_called()


def test_end_proof_still_honours_unchanged_and_the_late_run_cap():
    conversation = row()
    conversation[hold.FIELD] = {
        **hold.completion_patch(conversation, hold.content_snapshot(conversation)),
        'pending_since': 100,
        'last_content_at': 100,
    }
    assert hold.admission(conversation, {'first_pending_at': 100}, now=130, end_proven=lambda: True) == (
        'unchanged',
        None,
    )
    conversation['transcript_segments'].append({'text': 'more ' * 200, 'start': 60, 'end': 200})
    conversation[hold.FIELD]['late_runs'] = hold.MAX_LATE_RUNS
    assert hold.admission(conversation, {'first_pending_at': 100}, now=130, end_proven=lambda: True) == (
        'late_cap',
        None,
    )


def test_ledger_end_fields_are_set_without_moving_the_stage():
    doc = ledger.plan_advance(None, ledger.SEALED, now=100).doc
    plan = ledger.plan_end(doc, end_type='silence_backstop', end_at=90, end_observed_at=95, last_speech_at=60, now=101)
    assert plan.outcome == 'written'
    assert plan.doc['stage'] == ledger.SEALED and plan.doc['deadline_at'] == doc['deadline_at']
    assert (plan.doc['end_type'], plan.doc['end_at'], plan.doc['end_observed_at'], plan.doc['last_speech_at']) == (
        'silence_backstop',
        90,
        95,
        60,
    )
    # The end fields survive the next stage transition.
    after = ledger.plan_advance(plan.doc, ledger.TRANSCRIBED, now=200).doc
    assert (after['end_type'], after['end_at'], after['end_observed_at']) == ('silence_backstop', 90, 95)


def test_a_known_end_is_not_replaced_by_a_weaker_one_but_a_later_end_supersedes():
    doc = ledger.plan_advance(None, ledger.SEALED, now=100).doc
    user = ledger.plan_end(doc, end_type='user_initiated', end_at=90, now=101).doc
    assert ledger.plan_end(user, end_type='unknown', end_at=90).outcome == 'stale'
    assert ledger.plan_end(user, end_type='user_initiated', end_at=90.4).outcome == 'duplicate'
    resumed = ledger.plan_end(user, end_type='silence_backstop', end_at=500, now=501)
    assert resumed.outcome == 'written' and resumed.doc['end_type'] == 'silence_backstop'
    assert ledger.plan_end(None, end_type='unknown', end_at=1).outcome == 'missing'
    assert ledger.plan_end(doc, end_type='unknown', end_at=None).outcome == 'illegal'


def test_record_end_is_fail_open_and_never_creates_a_row(monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    client = _FakeClient()
    assert ledger.record_end('uid', 'capture', end_type='user_initiated', end_at=90, firestore_client=client) is False
    assert not client.store
    ledger.advance('uid', 'capture', ledger.SEALED, now=100, firestore_client=client)
    assert ledger.record_end('uid', 'capture', end_type='user_initiated', end_at=90, firestore_client=client) is True
    assert client.store['users/uid/pipeline_ledger/capture']['end_type'] == 'user_initiated'

    class Boom:
        def collection(self, *_a, **_k):
            raise RuntimeError('synthetic')

    assert ledger.record_end('uid', 'capture', end_type='user_initiated', end_at=90, firestore_client=Boom()) is False
    monkeypatch.setenv('PIPELINE_LEDGER', 'off')
    assert ledger.record_end('uid', 'capture', end_type='user_initiated', end_at=90, firestore_client=client) is False


def test_only_real_ends_are_typed_from_finalization_triggers(monkeypatch):
    spy = Mock(return_value=True)
    monkeypatch.setattr(lifecycle.pipeline_ledger, 'record_end', spy)
    lifecycle._record_ledger_end('u', 'c', ProcessingTrigger.CLIENT_FINALIZE, None)
    lifecycle._record_ledger_end('u', 'c', ProcessingTrigger.SERVER_RECOVERY, None)
    lifecycle._record_ledger_end('u', 'c', ProcessingTrigger.CAPTURE_END, None)
    lifecycle._record_ledger_end('u', 'c', ProcessingTrigger.USER_REPROCESS, None)
    lifecycle._record_ledger_end('u', 'c', ProcessingTrigger.SYNC_UPDATE, None)
    assert [call.kwargs['end_type'] for call in spy.call_args_list] == ['user_initiated', 'silence_backstop', 'unknown']
    assert all(call.kwargs['end_at'] == call.kwargs['end_observed_at'] for call in spy.call_args_list)


def test_kill_switch_disables_the_feature(monkeypatch):
    monkeypatch.setenv('SYNC_UPLOAD_WATERMARK_ENABLED', 'false')
    assert not capture_end.enabled()
    monkeypatch.delenv('SYNC_UPLOAD_WATERMARK_ENABLED')
    assert capture_end.enabled()


def test_the_marker_is_read_only_for_a_row_with_a_recording_session(monkeypatch):
    load = Mock(return_value=marker())
    monkeypatch.setattr(store, 'load', load)
    assert store.proven('u', {'finished_at': 999.0}) is False
    load.assert_not_called()
    conversation = {'finished_at': 999.0, 'external_data': {'recording_session_id': 's'}}
    assert store.proven('u', conversation) is True
    load.assert_called_once_with('u', 's', firestore_client=None)
    assert store.proven('u', {**conversation, 'finished_at': 5000.0}) is False
    monkeypatch.setattr(store, 'load', Mock(side_effect=OSError('synthetic')))
    assert store.proven('u', conversation) is False
    monkeypatch.setenv('SYNC_UPLOAD_WATERMARK_ENABLED', 'off')
    monkeypatch.setattr(store, 'load', load)
    load.reset_mock()
    assert store.proven('u', conversation) is False
    load.assert_not_called()


@pytest.mark.parametrize(
    'raw, expected', [(None, 120), ('90', 90), ('5', 60), ('99999', 1800), ('0', None), ('-3', None), ('soon', None)]
)
def test_phone_silence_timer_is_bounded_and_can_be_withdrawn(monkeypatch, raw, expected):
    monkeypatch.delenv('SYNC_UPLOAD_WATERMARK_ENABLED', raising=False)
    if raw is None:
        monkeypatch.delenv('SYNC_CAPTURE_END_SILENCE_SECONDS', raising=False)
    else:
        monkeypatch.setenv('SYNC_CAPTURE_END_SILENCE_SECONDS', raw)
    assert capture_end.silence_seconds() == expected
    monkeypatch.setenv('SYNC_UPLOAD_WATERMARK_ENABLED', 'false')
    assert capture_end.silence_seconds() is None


def test_status_event_carries_the_silence_timer_only_when_set():
    assert 'end_silence_seconds' not in MessageServiceStatusEvent(status='mobile_batch_admission').to_json()
    sent = MessageServiceStatusEvent(status='mobile_batch_admission', end_silence_seconds=120).to_json()
    assert sent['end_silence_seconds'] == 120


def test_the_store_names_the_same_collection_as_the_session_authority():
    from database import recording_sessions

    assert store.RECORDING_SESSIONS_COLLECTION == recording_sessions.RECORDING_SESSIONS_COLLECTION
    assert store.PIPELINE_LEDGER_COLLECTION == ledger.COLLECTION
    assert capture_end.LEDGER_TRANSCRIBED == ledger.TRANSCRIBED


SEALED_AT = 900.0


def sealed_live(**changes):
    """A batch-owned live record the server sealed, with a phone copy that landed after."""
    base = {
        'id': 'c',
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'record_audio_closed': True,
        'record_sealed_at': SEALED_AT,
        'record_projection_revision': 1,
        'sync_live_target': True,
        'external_data': {'server_batch_only': True},
        **row(),
    }
    return {**base, **changes}


def ledger_doc(*stages):
    """``(stage, at)`` transitions as ``database.pipeline_ledger`` stores them."""
    return {
        'stage': stages[-1][0],
        'transitions': [{'stage': stage, 'at': at, 'revision': i + 1} for i, (stage, at) in enumerate(stages)],
    }


# Every unit projected: the record's whole projection completed after its seal.
ALL_UNITS = ledger_doc((ledger.SEALED, SEALED_AT), (ledger.TRANSCRIBED, SEALED_AT + 90))
# Unit 1 of 2 projected (revision 1 on the row), its sibling still transcribing.
SIBLING_PENDING = ledger_doc((ledger.SEALED, SEALED_AT))


@pytest.mark.parametrize(
    'changes, expected',
    [
        ({}, 'proven'),
        ({'record_lane_owner': None}, 'absent'),
        ({'record_lane_owner': 'batch_sync_v1'}, 'absent'),
        ({'status': 'in_progress'}, 'record_open'),
        ({'record_audio_closed': False}, 'record_open'),
        ({'record_audio_partial': True}, 'record_open'),
        ({'record_upload_sessions': {'s': {}}}, 'record_open'),
        ({'record_upload_failed': True}, 'record_open'),
        ({'record_projection_revision': None}, 'transcript_pending'),
        ({'summary_completed_at': 900.0}, 'notes_written'),
        ({'summary_output_present': True}, 'notes_written'),
        (
            {hold.FIELD: {'pending_since': 100, 'last_content_at': 100, 'full_snapshot': {'digest': 'd'}}},
            'notes_written',
        ),
        ({'record_sealed_at': None}, 'units_pending'),
    ],
)
def test_the_seal_proves_only_a_closed_transcribed_live_record_before_its_first_notes(changes, expected):
    assert capture_end.seal_proof(sealed_live(**changes), ALL_UNITS) == expected


def test_one_projected_unit_with_a_sibling_pending_is_not_proof_until_every_unit_lands():
    conversation = sealed_live(record_projection_revision=1)
    assert capture_end.seal_barrier(conversation) is None
    assert capture_end.seal_proof(conversation, SIBLING_PENDING) == 'units_pending'
    assert capture_end.seal_proof(conversation, None) == 'units_pending'
    assert capture_end.seal_proof(conversation, ALL_UNITS) == 'proven'


def test_a_transcript_from_before_a_reseal_does_not_prove_the_resealed_record():
    # Reopened and sealed again at 1000; the ledger never moves back, so its
    # transcribed stage still describes the first seal's units.
    resealed = sealed_live(record_sealed_at=1000.0, record_projection_revision=2)
    assert capture_end.seal_proof(resealed, ALL_UNITS) == 'units_pending'


def test_a_sealed_live_record_reads_only_its_ledger_and_counts_as_sealed(monkeypatch):
    load = Mock(side_effect=AssertionError('the seal needs no session read'))
    monkeypatch.setattr(store, 'load', load)
    ledgers = Mock(return_value=ALL_UNITS)
    monkeypatch.setattr(store, 'load_ledger', ledgers)
    counted = Mock()
    monkeypatch.setattr(capture_end, 'record_proof', counted)
    assert store.proven('u', sealed_live()) is True
    ledgers.assert_called_once_with('u', 'c', firestore_client=None)
    counted.assert_called_once_with('sealed')
    # A row that fails the barrier never reads the ledger.
    ledgers.reset_mock()
    assert store.proven('u', sealed_live(record_audio_closed=False)) is False
    ledgers.assert_not_called()
    # A sibling still pending, or an unreadable ledger, is "not proven".
    monkeypatch.setattr(store, 'load_ledger', Mock(return_value=SIBLING_PENDING))
    assert store.proven('u', sealed_live()) is False
    monkeypatch.setattr(store, 'load_ledger', Mock(side_effect=OSError('synthetic')))
    assert store.proven('u', sealed_live()) is False
    # Without the seal, a recording-session row still asks the phone's marker.
    monkeypatch.setattr(store, 'load', Mock(return_value=None))
    unsealed = sealed_live(record_audio_closed=False, external_data={'recording_session_id': 's'})
    assert store.proven('u', unsealed) is False
    monkeypatch.setattr(store, 'load_ledger', ledgers)
    monkeypatch.setenv('SYNC_UPLOAD_WATERMARK_ENABLED', 'false')
    ledgers.reset_mock()
    assert store.proven('u', sealed_live()) is False
    ledgers.assert_not_called()
    assert [c for c in counted.call_args_list if c.args == ('sealed',)] == [(('sealed',),)]


def test_the_ledger_read_names_the_capture_document():
    client = _FakeClient()
    assert store.load_ledger('u', 'c', firestore_client=client) is None
    client.store['users/u/pipeline_ledger/c'] = ALL_UNITS
    assert store.load_ledger('u', 'c', firestore_client=client) == ALL_UNITS


def test_a_sealed_live_record_gets_notes_now_while_a_sync_only_row_still_waits_quiet(monkeypatch):
    monkeypatch.setattr(store, 'load_ledger', Mock(return_value=ALL_UNITS))
    proven = lambda conversation: lambda: store.proven('u', conversation)  # noqa: E731
    sealed = sealed_live()
    assert hold.admission(sealed, {'first_pending_at': 100}, now=130, end_proven=proven(sealed)) == ('end_proof', None)
    sync_only = row()
    assert hold.admission(sync_only, {'first_pending_at': 100}, now=130, end_proven=proven(sync_only)) == (
        'quiet_wait',
        100 + hold.quiet_seconds(),
    )
    # The same sealed row with a sibling unit still transcribing keeps the quiet wait.
    monkeypatch.setattr(store, 'load_ledger', Mock(return_value=SIBLING_PENDING))
    assert hold.admission(sealed, {'first_pending_at': 100}, now=130, end_proven=proven(sealed)) == (
        'quiet_wait',
        100 + hold.quiet_seconds(),
    )


def test_a_pendant_copy_after_sealed_notes_waits_quiet_then_buys_exactly_one_late_run(monkeypatch):
    monkeypatch.setattr(store, 'load_ledger', Mock(return_value=ALL_UNITS))
    conversation = sealed_live()
    asked = lambda: store.proven('u', conversation)  # noqa: E731
    assert hold.admission(conversation, {'first_pending_at': 100}, now=130, end_proven=asked)[0] == 'end_proof'
    # First notes settle the epoch and record what they saw.
    conversation[hold.FIELD] = hold.completion_patch(conversation, hold.content_snapshot(conversation))
    conversation['summary_completed_at'] = 131.0
    # The pendant's stored copy lands later and adds material speech.
    conversation['transcript_segments'].append({'text': 'pendant ' * 120, 'start': 60, 'end': 120})
    conversation[hold.FIELD] = hold.activity_patch(conversation, 1000)
    pending = {'first_pending_at': 1000}
    assert hold.admission(conversation, pending, now=1030, end_proven=asked) == (
        'quiet_wait',
        1000 + hold.quiet_seconds(),
    )
    assert hold.admission(conversation, pending, now=1000 + hold.quiet_seconds(), end_proven=asked) == ('ready', None)
    conversation[hold.FIELD] = hold.completion_patch(conversation, hold.content_snapshot(conversation))
    assert conversation[hold.FIELD]['late_runs'] == 1
    # A further copy cannot buy a second automatic run.
    conversation['transcript_segments'].append({'text': 'later ' * 120, 'start': 120, 'end': 180})
    conversation[hold.FIELD] = hold.activity_patch(conversation, 2000)
    assert hold.admission(
        conversation, {'first_pending_at': 2000}, now=2000 + hold.quiet_seconds(), end_proven=asked
    ) == ('late_cap', None)
