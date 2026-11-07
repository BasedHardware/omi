"""Dark scheduling policy, durable deadlines and source clocks, no services."""

from copy import deepcopy
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
        'finished_at': 100,
        'recorded_end': 90,
        'transcript_segments': [{'text': 'Synthetic captured evidence', 'start': 0, 'end': 90}],
        **updates,
    }


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
    assert runtime.hold_decision('u', row, {}, now=120) == (False, None, None)
    assert row == before


def test_remote_owner_gate_runtime_kill_and_invalid_fail_closed(serving, monkeypatch):
    assert runtime.serving('u') and not runtime.serving('other')
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'invalid')
    assert not runtime.serving('u')
    assert runtime.hold_decision('u', sealed(), {}, now=120) == (False, None, None)
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
    assert runtime.hold_decision('u', sealed(), {}, now=101)[0]


def test_mcp_promotion_does_not_require_a_mobile_presence_lease(serving):
    assert runtime.attention('u', now=100) == 'unknown'
    assert runtime.begin_promotion('u', trigger='mcp_read', now=100)
    assert runtime.hold_decision('u', sealed(), {}, now=101)[0]


def test_unknown_presence_keeps_legacy_policy_without_explicit_demand(serving):
    assert runtime.hold_decision('u', sealed(), {}, now=100) == (False, None, None)


def test_accepted_deadline_dispatch_does_not_need_redis(serving, monkeypatch):
    monkeypatch.setattr(runtime, 'attention', lambda *_a, **_k: pytest.fail('deadline must be durable'))
    assert runtime.hold_decision('u', sealed(), {'pipeline_dispatch_at': 1770}, now=1770)[0]


def test_patient_wait_and_absolute_deadline_cannot_slide(serving):
    row = sealed()
    obligation = {'pipeline_dispatch_at': 1770}
    runtime.observe_surface('u', 'background', {'foreground': False}, now=1700)
    assert policy.dispatch_at(sealed(recorded_end=1000), obligation) == 1770
    assert runtime.hold_decision('u', row, obligation, now=1700) == (False, 1760, policy.seal_snapshot(row))
    assert runtime.hold_decision('u', row, obligation, now=1770)[0]
    assert policy.dispatch_at(sealed(recorded_end=None), {}) is None


def test_shadow_does_not_change_due_times_or_paid_work(serving, monkeypatch):
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'shadow')
    assert runtime.hold_decision('u', sealed(), {}, now=2000) == (False, None, None)


def test_accepted_patient_obligation_drains_after_kill(serving, monkeypatch):
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'off')
    obligation = {'pipeline_dispatch_at': 1770}
    assert runtime.hold_decision('u', sealed(), obligation, now=1770)[0]
    assert not runtime.hold_decision('u', sealed(), {}, now=1770)[0]


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
