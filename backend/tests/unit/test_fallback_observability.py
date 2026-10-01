from __future__ import annotations

import logging

import pytest

from utils.observability import fallback as fallback_mod
from utils.stt.live_failure import PendingLiveFailover


class FakeCounterChild:
    def __init__(self, parent, labels):
        self.parent = parent
        self.labels = labels

    def inc(self, amount: float = 1.0):
        self.parent.increments.append((self.labels, amount))


class FakeCounter:
    def __init__(self):
        self.increments: list[tuple[dict[str, str], float]] = []

    def labels(self, **labels):
        return FakeCounterChild(self, labels)


@pytest.mark.parametrize(
    'typed,subtype',
    [
        ('modulate_serve_error', 'modulate_serve_error'),
        ('connection_lost', 'connection_lost'),
        ('send_failed', 'send_failed'),
        (None, 'untyped'),
        ('unbounded vendor message', 'untyped'),
    ],
)
def test_failed_live_hop_logs_bounded_typed_subtype_without_new_metric_labels(monkeypatch, caplog, typed, subtype):
    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    pending = PendingLiveFailover(from_mode='parakeet', to_mode='modulate')
    with caplog.at_level(logging.WARNING, logger=fallback_mod.logger.name):
        pending.note_failure(typed)
        pending.note_failure(typed)
    assert counter.increments == [
        (
            {
                'component': 'stt_live_session',
                'from_mode': 'parakeet',
                'to_mode': 'modulate',
                'reason': 'other',
                'outcome': 'exhausted',
            },
            1.0,
        )
    ]
    assert len(caplog.records) == 1
    assert caplog.records[0].message == (
        'omi_fallback_event component=stt_live_session from=parakeet to=modulate '
        f'reason=other outcome=exhausted subtype={subtype}'
    )


def test_unknown_stt_subtype_is_bucketed_in_log(monkeypatch, caplog):
    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    with caplog.at_level(logging.WARNING, logger=fallback_mod.logger.name):
        fallback_mod.record_fallback(
            component='stt_live_session',
            from_mode='parakeet',
            to_mode='modulate',
            reason='other',
            outcome='exhausted',
            failure_subtype='unbounded vendor message',
        )
    assert len(caplog.records) == 1
    assert caplog.records[0].message.endswith(' subtype=unknown')
    assert 'unbounded' not in caplog.records[0].message


def test_record_fallback_increments_metric_and_logs_same_fields(monkeypatch, caplog):
    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)

    with caplog.at_level(logging.WARNING, logger=fallback_mod.logger.name):
        fallback_mod.record_fallback(
            component='sync_dispatch',
            from_mode='cloud_tasks',
            to_mode='inline',
            reason='enqueue_failed',
            outcome='degraded',
        )

    assert counter.increments == [
        (
            {
                'component': 'sync_dispatch',
                'from_mode': 'cloud_tasks',
                'to_mode': 'inline',
                'reason': 'enqueue_failed',
                'outcome': 'degraded',
            },
            1.0,
        )
    ]
    assert any(
        'omi_fallback_event' in record.message
        and 'component=sync_dispatch' in record.message
        and 'from=cloud_tasks' in record.message
        and 'to=inline' in record.message
        and 'reason=enqueue_failed' in record.message
        and 'outcome=degraded' in record.message
        for record in caplog.records
    )


def test_record_fallback_buckets_unknown_reason_and_invalid_outcome(monkeypatch):
    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)

    fallback_mod.record_fallback(
        component='not_a_real_component',
        from_mode='Cloud Tasks!',
        to_mode='',
        reason='totally_novel_failure',
        outcome='success',
    )

    labels, amount = counter.increments[0]
    assert amount == 1.0
    assert labels['component'] == 'other'
    assert labels['from_mode'] == 'cloud_tasks_'
    assert labels['to_mode'] == 'none'
    assert labels['reason'] == 'other'
    assert labels['outcome'] == 'degraded'


def test_bucket_reason_respects_allowlist_override():
    assert fallback_mod.bucket_reason('enqueue_failed') == 'enqueue_failed'
    assert fallback_mod.bucket_reason('weird') == 'other'
    assert fallback_mod.bucket_reason('custom', allowed=frozenset({'custom', 'other'})) == 'custom'


def test_llm_gateway_is_a_bounded_fallback_component():
    assert fallback_mod.bucket_component('llm_gateway') == 'llm_gateway'


def test_conversation_notes_is_a_bounded_fallback_component():
    assert fallback_mod.bucket_component('conversation_notes') == 'conversation_notes'


def test_stt_live_session_is_a_bounded_fallback_component():
    """Mid-session hops used component=stt_live_session; without the allowlist
    they bucketed to other, so omi-stt-fallback-leg-dead (keyed on stt_selection)
    could not see a 100% dead Soniox failover leg.
    """
    assert fallback_mod.bucket_component('stt_live_session') == 'stt_live_session'


def test_firestore_malformed_document_labels_are_bounded():
    assert fallback_mod.bucket_component('firestore_read') == 'firestore_read'
    assert fallback_mod.bucket_reason('malformed_doc') == 'malformed_doc'


def test_web_search_security_reasons_keep_their_exact_labels():
    # The Anthropic web-search gate records these reasons; if they are not
    # allowlisted they all collapse to ``other`` and the security withhold
    # paths become indistinguishable in metrics.
    assert fallback_mod.bucket_reason('private_tool_output_in_context') == 'private_tool_output_in_context'
    assert fallback_mod.bucket_reason('not_authorized') == 'not_authorized'
    assert fallback_mod.bucket_reason('authorization_unavailable') == 'authorization_unavailable'


def test_record_fallback_never_raises_on_metric_or_log_failure(monkeypatch):
    class BoomCounter:
        def labels(self, **_labels):
            raise RuntimeError('metric boom')

    class BoomLogger:
        def warning(self, *_args, **_kwargs):
            raise RuntimeError('log boom')

    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', BoomCounter())
    fallback_mod.record_fallback(
        component='pusher',
        from_mode='connected',
        to_mode='degraded',
        reason='circuit_open',
        outcome='degraded',
        log=BoomLogger(),
    )


def test_stt_selection_fallback_records_on_capability_mismatch(monkeypatch):
    from utils.stt import streaming as streaming_mod

    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    monkeypatch.setattr(streaming_mod, 'stt_service_models', ['modulate-velma-2'])

    service, lang, model = streaming_mod.get_stt_service_for_language('xx-unsupported')

    assert (service, lang, model) == (None, None, None)
    assert counter.increments == [
        (
            {
                'component': 'stt_selection',
                'from_mode': 'requested_non_en',
                'to_mode': 'unavailable',
                'reason': 'capability_mismatch',
                'outcome': 'exhausted',
            },
            1.0,
        )
    ]


def test_explicit_parakeet_preference_fallback_records_when_live_mode_is_incapable(monkeypatch):
    from utils.stt import streaming as streaming_mod

    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.test')
    monkeypatch.setattr(streaming_mod, 'stt_service_models', ['parakeet', 'modulate-velma-2'])

    service, lang, model = streaming_mod.get_stt_service_for_language(
        'es', multi_lang_enabled=True, preferred_service='parakeet'
    )

    assert (service, lang, model) == (streaming_mod.STTService.modulate, 'multi', 'velma-2')
    assert counter.increments == [
        (
            {
                'component': 'stt_selection',
                'from_mode': 'parakeet',
                'to_mode': 'modulate',
                'reason': 'capability_mismatch',
                'outcome': 'degraded',
            },
            1.0,
        )
    ]


def test_automatic_parakeet_capability_fallback_records_when_live_mode_is_incapable(monkeypatch):
    from utils.stt import streaming as streaming_mod

    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://parakeet.test')
    monkeypatch.setattr(streaming_mod, 'stt_service_models', ['parakeet', 'modulate-velma-2'])

    service, lang, model = streaming_mod.get_stt_service_for_language('es', multi_lang_enabled=True)

    assert (service, lang, model) == (streaming_mod.STTService.modulate, 'multi', 'velma-2')
    assert counter.increments == [
        (
            {
                'component': 'stt_selection',
                'from_mode': 'parakeet',
                'to_mode': 'modulate',
                'reason': 'capability_mismatch',
                'outcome': 'degraded',
            },
            1.0,
        )
    ]


def test_hosted_vad_fallback_reason_buckets(monkeypatch):
    import httpx
    import requests
    from utils.stt import vad as vad_mod

    assert vad_mod._hosted_vad_fallback_reason(requests.Timeout()) == 'timeout'
    assert vad_mod._hosted_vad_fallback_reason(httpx.TimeoutException('slow')) == 'timeout'

    response = requests.Response()
    response.status_code = 503
    assert vad_mod._hosted_vad_fallback_reason(requests.HTTPError(response=response)) == 'provider_5xx'

    response429 = requests.Response()
    response429.status_code = 429
    assert vad_mod._hosted_vad_fallback_reason(requests.HTTPError(response=response429)) == 'provider_429'

    assert vad_mod._hosted_vad_fallback_reason(RuntimeError('boom')) == 'other'


def test_replay_diagnostics_are_bounded_log_values_not_metric_labels(monkeypatch, caplog):
    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    diagnostics = fallback_mod.ReplayLagDiagnostics(
        capture_seconds=1e20,
        admitted_seconds=float('nan'),
        seconds_since_text=-1,
        posts_since_anchor=1000001,
        empty_posts_since_anchor=-10,
        post_in_flight=True,
        empty_streak=5,
        cut_pending=True,
        pacing_wait=False,
    )
    fallback_mod.record_fallback(
        component='stt_live_session',
        from_mode='parakeet',
        to_mode='soniox',
        reason='capacity_full',
        outcome='recovered',
        capacity_subtype='replay_ring_cap',
        replay_diagnostics=diagnostics,
    )
    labels, _ = counter.increments[0]
    assert set(labels) == {'component', 'from_mode', 'to_mode', 'reason', 'outcome'}
    line = caplog.records[-1].message
    assert 'un_emitted_capture_seconds=86400.000' in line
    assert 'vad_admitted_seconds=-1.000' in line and 'seconds_since_text=-1.000' in line
    assert 'posts_since_anchor=1000000' in line and 'empty_posts_since_anchor=0' in line
    assert 'post_in_flight=1 empty_streak=5 cut_pending=1 pacing_wait=0' in line
    caplog.clear()
    fallback_mod.record_fallback(
        component='stt_live_session',
        from_mode='parakeet',
        to_mode='soniox',
        reason='capacity_full',
        outcome='recovered',
        capacity_subtype='buffer_cap',
        replay_diagnostics=diagnostics,
    )
    assert 'un_emitted_capture_seconds' not in caplog.records[-1].message


def test_first_text_diagnostics_are_bounded_log_fields_not_labels(monkeypatch, caplog):
    counter = FakeCounter()
    monkeypatch.setattr(fallback_mod, 'OMI_FALLBACK_TOTAL', counter)
    diagnostic = fallback_mod.FirstTextDeadlineDiagnostics(
        admitted_seconds=float('nan'),
        posts=1000001,
        empty_posts=-1,
        answered_empty_stranded_flushes=2,
        seconds_since_first_speech=1e20,
        episode_admitted_seconds=float('inf'),
        seconds_since_deadline_speech=12,
        answered_empty_admitted_seconds=1e20,
    )
    fallback_mod.record_fallback(
        component='stt_live_session',
        from_mode='parakeet',
        to_mode='soniox',
        reason='first_text_deadline',
        outcome='recovered',
        first_text_diagnostics=diagnostic,
    )
    labels, count = counter.increments[0]
    assert labels == {
        'component': 'stt_live_session',
        'from_mode': 'parakeet',
        'to_mode': 'soniox',
        'reason': 'first_text_deadline',
        'outcome': 'recovered',
    }
    assert count == 1
    assert caplog.records[-1].message.endswith(
        ' vad_admitted_seconds=-1.000 posts=1000000 empty_posts=0'
        ' answered_empty_stranded_flushes=2 seconds_since_first_speech=86400.000'
        ' episode_admitted_seconds=-1.000 seconds_since_deadline_speech=12.000'
        ' answered_empty_admitted_seconds=86400.000'
    )
    fallback_mod.record_fallback(
        component='stt_live_session',
        from_mode='parakeet',
        to_mode='soniox',
        reason='connection_lost',
        outcome='recovered',
        first_text_diagnostics=diagnostic,
    )
    assert 'vad_admitted_seconds' not in caplog.records[-1].message
