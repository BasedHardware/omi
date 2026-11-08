"""Dark scheduling policy, durable deadlines and source clocks, no services."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import fakeredis
import pytest

from config import pipeline_attention as policy
from utils.conversations import pipeline_attention as runtime
from utils.conversations import summary_delivery
from utils.episodes import pipeline_settlement


def sealed(**updates):
    return {
        'id': 'c',
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'record_audio_closed': True,
        'record_upload_revision': 3,
        'sync_content_revision': 7,
        'record_projection_revision': 1,
        'finished_at': 100,
        'recorded_end': 90,
        'transcript_segments': [{'text': 'Synthetic captured evidence', 'start': 0, 'end': 90}],
        **updates,
    }


def decision(*args, **kwargs):
    kwargs.setdefault('projected', True)
    return runtime.hold_decision(*args, **kwargs)


@pytest.fixture
def serving(monkeypatch):
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'serve')
    monkeypatch.setenv('PIPELINE_SEAL_FAST_ENABLED', 'true')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(runtime, 'client', lambda: redis)
    monkeypatch.setattr(runtime.omi_flags, 'resolve', lambda key, uid: SimpleNamespace(enabled=uid == 'u'))
    return redis


@pytest.mark.parametrize(
    'updates',
    [
        {'record_audio_closed': False},
        {'record_audio_partial': {'barrier': True}},
        {'record_upload_failed': True},
        {'record_upload_sessions': {'producer': True}},
        {'finished_at': None},
        {'status': 'processing'},
        {'deleted': True},
        {'discarded': True},
        {'record_lane_owner': 'legacy'},
        {'record_upload_revision': None},
        {'record_upload_revision': True},
        {'sync_content_revision': None},
        {'sync_content_revision': True},
    ],
)
def test_every_incomplete_seal_refuses_hold_bypass(serving, updates):
    row = sealed(**updates)
    before = deepcopy(row)
    assert policy.seal_snapshot(row) is None
    assert decision('u', row, {}, now=120) == (False, None, None)
    assert row == before


def test_remote_owner_gate_runtime_kill_and_invalid_fail_closed(serving, monkeypatch):
    assert runtime.serving('u') and not runtime.serving('other')
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'invalid')
    assert not runtime.serving('u')
    assert decision('u', sealed(), {}, now=120) == (False, None, None)
    assert not policy.close_on_seal_enabled() and not policy.skip_silence_enabled()


def test_home_live_foreground_multisession_and_expiry(serving):
    runtime.observe_surface('u', 'one', {'foreground': True, 'home_visible': True}, now=100)
    runtime.observe_surface('u', 'two', {'foreground': True, 'transcript_visible': True}, now=110)
    runtime.observe_surface('u', 'one', {'foreground': False, 'home_visible': True}, now=120)
    assert runtime.attention('u', now=150) == 'watched'
    assert runtime.attention('u', now=201) == 'unwatched'


def test_generic_app_open_promotes_but_cannot_sustain_watch(serving):
    runtime.observe_surface('u', 'one', {'foreground': True, 'surface_open': True}, now=100)
    assert runtime.attention('u', now=101) == 'unwatched'
    assert runtime.begin_promotion('u', trigger='app_open', now=100)
    assert not runtime.begin_promotion('u', trigger='api_read', now=101)
    assert decision('u', sealed(), {}, now=101)[0]


def test_mcp_promotion_does_not_require_a_mobile_presence_lease(serving):
    assert runtime.attention('u', now=100) == 'unknown'
    assert runtime.begin_promotion('u', trigger='mcp_read', now=100)
    assert decision('u', sealed(), {}, now=101)[0]


def test_unknown_presence_keeps_legacy_policy_without_explicit_demand(serving):
    assert decision('u', sealed(), {}, now=100) == (False, None, None)


def test_accepted_deadline_dispatch_does_not_need_redis(serving, monkeypatch):
    monkeypatch.setattr(runtime, 'attention', lambda *_a, **_k: pytest.fail('deadline must be durable'))
    assert decision('u', sealed(), {'pipeline_dispatch_at': 1770}, now=1770)[0]


def test_ready_patient_notes_beat_absolute_ceiling_without_sliding_it(serving):
    row = sealed()
    obligation = {'pipeline_dispatch_at': 1770}
    runtime.observe_surface('u', 'background', {'foreground': False}, now=1700)
    assert policy.dispatch_at(sealed(recorded_end=1000), obligation) == 1770
    assert decision('u', row, obligation, now=1700) == (True, None, policy.seal_snapshot(row))
    assert decision('u', row, obligation, now=1770)[0]
    assert policy.dispatch_at(sealed(recorded_end=None), {}) is None


def test_shadow_does_not_change_due_times_or_paid_work(serving, monkeypatch):
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'shadow')
    assert decision('u', sealed(), {}, now=2000) == (False, None, None)


def test_mode_off_restores_legacy_for_accepted_obligations(serving, monkeypatch):
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'off')
    obligation = {'pipeline_dispatch_at': 1770}
    assert decision('u', sealed(), obligation, now=1770) == (False, None, None)
    assert decision('u', sealed(), obligation, projected=False, now=100) == (False, None, None)


def test_late_producer_fences_the_real_persistence_predicate(serving):
    row = sealed()
    token = summary_delivery.PROCESS_CONTEXT.set({'pipeline_seal': policy.seal_snapshot(row)})
    try:
        assert not summary_delivery.processing_fenced(row)
        for changed in ({'record_upload_revision': 4}, {'sync_content_revision': 8}, {'record_audio_closed': False}):
            assert summary_delivery.processing_fenced({**row, **changed})
    finally:
        summary_delivery.PROCESS_CONTEXT.reset(token)


def test_note_version_receipt_is_replay_idempotent_and_durable(serving):
    row = sealed()
    context = {
        'pipeline_seal': policy.seal_snapshot(row),
        'pipeline_fingerprint': runtime.notes_fingerprint(row),
        'pipeline_attention': 'unwatched',
        'pipeline_capture_end': 90,
    }
    write = {'summary_output_present': True}
    receipt = runtime.prepare_notes_receipt(row, write, 'u', now=2000, context=context)
    assert receipt['rewrites'] == 0 and receipt['capture_latency'] == 1910
    row.update(write)
    assert runtime.prepare_notes_receipt(row, {}, 'u', now=2100, context=context) is None
    assert runtime.prepare_notes_receipt(row, {'summary_output_present': True}, 'u', now=2100, context=context) is None
    row['sync_content_revision'] = 8
    context.update(pipeline_seal=policy.seal_snapshot(row), pipeline_fingerprint=runtime.notes_fingerprint(row))
    second = {'summary_output_present': True}
    receipt = runtime.prepare_notes_receipt(row, second, 'u', now=2200, context=context)
    assert receipt['rewrites'] == 1 and second[policy.FIELD]['notes_versions'] == 2


def test_pipeline_receipts_do_not_depend_on_legacy_summary_rollout(serving, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false')
    row = sealed()
    context = {
        'pipeline_seal': policy.seal_snapshot(row),
        'pipeline_fingerprint': runtime.notes_fingerprint(row),
        'pipeline_attention': 'unwatched',
    }
    token = summary_delivery.PROCESS_CONTEXT.set(context)
    try:
        write = {'status': 'completed', 'structured': {'title': 'Synthetic', 'overview': 'Durable generated notes'}}
        receipt = summary_delivery.merge_result(row, write, 'u', now=2000)
        assert receipt['pipeline']['first'] and write[policy.FIELD]['notes_versions'] == 1
        banked = {**row, **write}
        minimum = {'status': 'completed', 'structured': {'title': 'Pending'}}
        assert summary_delivery.merge_result(banked, minimum, 'u', now=2100) is None
        assert minimum['structured'] == banked['structured'] and not minimum['summary_output_present']
    finally:
        summary_delivery.PROCESS_CONTEXT.reset(token)


def test_pending_episode_deadline_preserved_and_unresolved_sibling_never_sealed(serving, monkeypatch):
    episode = {
        'id': 'e',
        'status': 'live',
        'state_version': 3,
        'conversation_ids': ['c', 'other'],
        'pipeline_dispatch_at': 1770,
    }
    monkeypatch.setattr(pipeline_settlement.episodes, 'get_episode_for_conversation', lambda *_: episode)
    monkeypatch.setattr(
        pipeline_settlement.conversations, 'get_conversation_raw_snapshot', lambda *_: sealed(record_audio_closed=False)
    )
    close = []
    monkeypatch.setattr(
        pipeline_settlement.service, 'close_pipeline_snapshot', lambda *a, **k: close.append(a) or episode
    )
    assert not pipeline_settlement.settle('u', 'c', sealed(), 3000, now=1700)
    assert not pipeline_settlement.settle('u', 'c', sealed(), 3000, now=1770)
    assert close == []
    monkeypatch.setattr(
        pipeline_settlement.conversations, 'get_conversation_raw_snapshot', lambda *_: sealed(id='other')
    )
    assert pipeline_settlement.settle('u', 'c', sealed(), 3000, now=1770)
    assert close[0][2] == 1770


def test_non_clock_objects_cannot_mint_an_accepted_deadline(serving):
    class Floatable:
        def __float__(self):
            raise AssertionError('unknown clock objects must not be coerced')

    value = Floatable()
    assert policy.seconds(value) is None
    assert decision('other', sealed(), {'pipeline_dispatch_at': value}, now=2000) == (False, None, None)


def test_naive_clock_is_utc_and_missing_seal_proof_cannot_compare_equal():
    at = datetime(2026, 11, 7, 12)
    assert policy.seconds(at) == at.replace(tzinfo=timezone.utc).timestamp()
    assert not policy.snapshot_matches(sealed(record_audio_closed=False), None)
    assert not policy.snapshot_matches(sealed(), {})
    assert policy.DISPATCH_AFTER_SECONDS + policy.PROCESSING_RESERVE_SECONDS == policy.NOTES_TARGET_SECONDS


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
def test_seal_flag_kill_restores_legacy_for_accepted_deadline(serving, monkeypatch, mode):
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', mode)
    monkeypatch.setenv('PIPELINE_SEAL_FAST_ENABLED', 'false')
    assert decision('u', sealed(), {'pipeline_dispatch_at': 1770}, now=100) == (False, None, None)


def test_no_episode_does_not_invent_early_patient_settlement(serving, monkeypatch):
    monkeypatch.setattr(pipeline_settlement.episodes, 'get_episode_for_conversation', lambda *_: None)
    row = sealed(sync_processing_hold={'last_content_at': 100})
    assert not pipeline_settlement.settle('u', 'c', row, 1770, now=1000)


def test_episode_deadline_conflict_keeps_existing_hold_path(serving, monkeypatch):
    monkeypatch.setattr(
        pipeline_settlement.episodes,
        'get_episode_for_conversation',
        lambda *_: {
            'id': 'e',
            'status': 'live',
            'state_version': 2,
            'conversation_ids': ['c'],
        },
    )

    def conflict(*_a, **_k):
        raise pipeline_settlement.episodes.EpisodeConflict('changed')

    monkeypatch.setattr(pipeline_settlement.episodes, 'update_episode', conflict)
    assert not pipeline_settlement.settle('u', 'c', sealed(), 1770, now=1000)


def test_ready_notes_beat_deadline_after_expired_presence(serving, monkeypatch):
    monkeypatch.setattr(runtime, 'attention', lambda *_a, **_k: 'unknown')
    monkeypatch.setattr(runtime, 'promoted', lambda *_a, **_k: False)
    assert decision('u', sealed(), {'pipeline_dispatch_at': 1770}, now=1000) == (
        True,
        None,
        policy.seal_snapshot(sealed()),
    )


def test_unresolved_producer_wait_is_bounded_before_legacy_fallback(serving):
    assert decision('u', sealed(record_audio_closed=False), {'pipeline_dispatch_at': 1770}, now=1770) == (
        False,
        1830,
        None,
    )
    assert decision('u', sealed(record_audio_closed=False), {'pipeline_dispatch_at': 1770}, now=3690) == (
        False,
        None,
        None,
    )


@pytest.mark.parametrize('projected', [False, None])
def test_new_policy_deadline_cannot_bypass_unfinished_projection(serving, projected):
    runtime.begin_promotion('u', trigger='api_read', now=1770)
    assert decision('u', sealed(), {'pipeline_dispatch_at': 1770}, projected=projected, now=1770) == (False, 1830, None)
    assert decision('u', sealed(), {'pipeline_dispatch_at': 1770}, projected=projected, now=3690) == (False, None, None)


def test_pre_policy_intake_keeps_legacy_timing(serving):
    runtime.begin_promotion('u', trigger='api_read', now=100)
    assert decision('u', sealed(), {}, projected=None, now=101) == (False, None, None)


def test_all_sibling_projection_ledger_and_pinned_upload_are_required():
    from config.record_audio import record_identity
    from utils.batch_pipeline import record_attention
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore

    store = MemoryStore()
    store.namespace = 'batch_pipeline_prod'
    content, _ = record_identity('u', 'c')
    job = 'bp_' + content
    row = sealed()
    assert record_attention.receipt('u', 'c', row, store=store).admitted is None
    intake = {
        'owner_id': 'u',
        'conversation_id': 'c',
        'content_id': content,
        'segment_ids': ['first', 'second'],
        'pipeline_record_barrier': {
            'record_lane_owner': 'batch_live_v1',
            'status': 'completed',
            'record_upload_revision': 3,
            'finished_at': 100,
        },
    }
    store.rows[('intakes', job)] = intake
    assert record_attention.receipt('u', 'c', row, store=store, require_projection=False).admitted is True
    ledger = {
        'status': 'processing',
        'job_id': job,
        'dispatch_protocol': 'batch_v1',
        'batch_pipeline': {'namespace': store.namespace, 'segment_ids': ['first', 'second']},
    }
    store.rows[('content', 'u/' + content)] = ledger
    assert record_attention.receipt('u', 'c', row, store=store).projected is False
    store.rows[('content', 'u/' + content)]['status'] = 'completed'
    assert record_attention.receipt('u', 'c', row, store=store).projected is True
    # Projection may extend finished_at; original upload revision stays immutable.
    assert record_attention.receipt('u', 'c', sealed(finished_at=110), store=store).projected is True
    for changes in ({'record_upload_revision': 4}, {'record_projection_revision': 0}, {'record_audio_closed': False}):
        assert record_attention.receipt('u', 'c', sealed(**changes), store=store).projected is False
    store.rows[('content', 'u/' + content)]['batch_pipeline']['segment_ids'] = ['first']
    assert record_attention.receipt('u', 'c', row, store=store).projected is False
    store.rows[('content', 'u/' + content)]['batch_pipeline']['segment_ids'] = ['first', 'second']
    store.rows[('content', 'u/' + content)]['batch_pipeline']['namespace'] = 'batch_pipeline_dev'
    assert record_attention.receipt('u', 'c', row, store=store).projected is False
    store.rows[('content', 'u/' + content)]['batch_pipeline']['namespace'] = store.namespace
    store.rows[('content', 'u/' + content)]['job_id'] = 'other'
    assert record_attention.receipt('u', 'c', row, store=store).projected is False
    store.rows[('intakes', job)]['owner_id'] = 'other'
    assert record_attention.receipt('u', 'c', row, store=store, require_projection=False).admitted is False


def test_deadline_preserves_unresolved_f_join_boundary(serving, monkeypatch):
    episode = {'id': 'e', 'status': 'live', 'pending_boundary': {'c': {'decision': 'pending'}}}
    monkeypatch.setattr(pipeline_settlement.episodes, 'get_episode_for_conversation', lambda *_: episode)
    monkeypatch.setattr(
        pipeline_settlement.service, 'close_pipeline_snapshot', lambda *a, **k: pytest.fail('F owns this')
    )
    assert not pipeline_settlement.settle('u', 'c', sealed(), 1770, now=1770)
    assert episode['pending_boundary'] == {'c': {'decision': 'pending'}}


def test_fast_compose_requires_current_notes_receipt(serving):
    runtime.begin_promotion('u', trigger='api_read', now=100)
    row = sealed()
    assert not runtime.fast_members('u', [row])
    row[policy.FIELD] = {'notes_fingerprint': runtime.notes_fingerprint(row)}
    assert runtime.fast_members('u', [row])
    row['sync_content_revision'] += 1
    assert not runtime.fast_members('u', [row])


def test_deadline_uses_whole_intake_extent_not_the_first_projected_unit():
    row = sealed(recorded_end=100)
    assert policy.dispatch_at(row, {'pipeline_capture_end': 1000}) == 2680
    assert (
        policy.dispatch_at(sealed(recorded_end=200), {'pipeline_capture_end': 1000, 'pipeline_dispatch_at': 2680})
        == 2680
    )
    assert policy.dispatch_at(row, {'pipeline_capture_end': 1000, 'pipeline_dispatch_at': 2500}) == 2500


def test_callback_does_not_invent_patient_admission_from_a_speech_span(serving):
    runtime.observe_surface('u', 'background', {'foreground': False}, now=100)
    assert decision('u', sealed(), {}, now=100) == (False, None, None)


def test_native_intake_clock_includes_unprojected_units_and_silent_tails():
    from config.record_audio import record_identity
    from utils.batch_pipeline import record_attention
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore

    store = MemoryStore()
    store.namespace = 'batch_pipeline_prod'
    content, _ = record_identity('u', 'c')
    job = 'bp_' + content
    store.rows[('intakes', job)] = {
        'segment_ids': ['first', 'second'],
        'owner_id': 'u',
        'conversation_id': 'c',
        'content_id': content,
        'pipeline_record_barrier': {
            'record_lane_owner': 'batch_live_v1',
            'status': 'completed',
            'record_upload_revision': 3,
        },
        'record_ranges': [{'start': 10, 'end': 100}, {'start': 100, 'end': 1000}],
    }
    row = sealed(recorded_end=90, finished_at=1100)
    first = record_attention.receipt('u', 'c', row, store=store)
    assert first.admitted is True and first.projected is False and first.capture_end == 1000
    store.rows[('content', 'u/' + content)] = {
        'status': 'completed',
        'job_id': job,
        'dispatch_protocol': 'batch_v1',
        'batch_pipeline': {'namespace': store.namespace, 'segment_ids': ['first', 'second']},
    }
    final = record_attention.receipt('u', 'c', row, store=store)
    assert final.projected is True and final.capture_end == 1000
    for ranges in (
        [],
        [{'start': 10, 'end': 100}],
        [{'start': 10, 'end': 100}, {'start': 100, 'end': None}],
        [{'start': 10, 'end': 100}, {'start': 100, 'end': 90}],
        [{'start': 10, 'end': 100}, {'start': 100, 'end': True}],
    ):
        store.rows[('intakes', job)]['record_ranges'] = ranges
        assert record_attention.receipt('u', 'c', row, store=store).capture_end is None


def test_note_clocks_use_admitted_audio_extent_and_unknown_stays_unknown(serving):
    row = sealed(recorded_end=90, pipeline_attention={'sealed_at': 1100})
    context = {'pipeline_seal': policy.seal_snapshot(row), 'pipeline_fingerprint': runtime.notes_fingerprint(row)}
    assert (
        runtime.prepare_notes_receipt(row, {'summary_output_present': True}, 'u', now=2000, context=context)[
            'capture_latency'
        ]
        is None
    )
    context['pipeline_capture_end'] = 1000
    write = {'summary_output_present': True}
    receipt = runtime.prepare_notes_receipt(row, write, 'u', now=2000, context=context)
    assert receipt['capture_latency'] == 1000 and receipt['capture_seal_latency'] == 100
    assert write[policy.FIELD]['capture_end'] == 1000


def test_mode_off_removes_projection_wait_for_accepted_record(serving, monkeypatch):
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'off')
    monkeypatch.setattr(runtime, 'attention', lambda *a, **k: pytest.fail('rollback needs no presence'))
    context = {'pipeline_record': True}
    assert decision('u', sealed(), context, projected=False, now=100) == (False, None, None)
    assert decision('u', sealed(), context, projected=True, now=100) == (False, None, None)


def test_unknown_clock_retains_legacy_hold_after_full_projection(serving):
    runtime.observe_surface('u', 'background', {'foreground': False}, now=100)
    assert decision('u', sealed(), {'pipeline_record': True}, now=100) == (False, None, policy.seal_snapshot(sealed()))


@pytest.mark.parametrize('changed', [{'record_audio_partial': {'barrier': True}}, {'record_upload_failed': True}])
def test_partial_or_failed_seal_wait_cannot_outlive_original_hour(serving, changed):
    obligation = {'first_pending_at': 100, 'pipeline_dispatch_at': 1770, 'pipeline_record': True}
    assert decision('u', sealed(**changed), obligation, now=3699) == (False, 3700, None)
    assert decision('u', sealed(**changed), obligation, now=3700) == (False, None, None)
    assert obligation['first_pending_at'] == 100


@pytest.mark.parametrize('mode,seal', [('off', 'true'), ('serve', 'false')])
def test_pipeline_kills_ignore_accepted_episode_deadline(serving, monkeypatch, mode, seal):
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', mode)
    monkeypatch.setenv('PIPELINE_SEAL_FAST_ENABLED', seal)
    monkeypatch.setattr(
        pipeline_settlement.episodes,
        'get_episode_for_conversation',
        lambda *a: pytest.fail('kill must retain the legacy episode path'),
    )
    assert not pipeline_settlement.settle('u', 'c', sealed(), 1770, now=1770)
