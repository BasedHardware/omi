import pytest

from testing.memory.v3_local_telemetry import (
    FakeV3TelemetrySink,
    NullV3TelemetrySink,
    V3LocalTelemetryInput,
    V3ReadDisableConfig,
    build_v3_get_telemetry_event,
    decide_v3_read_disable,
    emit_v3_get_telemetry,
)


def _valid_input(**overrides):
    data = {
        'read_source': 'memory_compatibility_projection',
        'route_decision': 'use_memory',
        'failure_reason': 'none',
        'control_generation': 7,
        'projection_generation': 7,
        'account_generation': 7,
        'cursor_validation_result': 'not_present',
        'cursor_validation_reason': 'not_present',
        'canary_cohort': 'canary_1',
        'canary_enrollment': 'enrolled',
        'no_legacy_fallback': True,
        'projection_source': 'memory_derived_compatibility_projection',
        'request_limit': 25,
        'request_cursor_present': False,
        'request_offset_disallowed_in_v3': True,
        'archive_default_visibility_decision': 'default_unavailable',
        'short_term_default_visibility_decision': 'stale_hidden',
        'rollback_read_disable_gate': 'enabled',
        'approval_owner': 'missing',
        'approval_status': 'missing',
    }
    data.update(overrides)
    return V3LocalTelemetryInput(**data)


def test_builds_exact_low_cardinality_v3_get_event_without_uid_or_payload():
    event = build_v3_get_telemetry_event(_valid_input(request_limit=501))

    assert event['event_name'] == 'v3_get_memory_read_decision'
    assert event['route'] == 'GET /v3/memories'
    assert event['runtime_wired'] is False
    assert event['production_sink_call'] is False
    assert event['request_limit'] == 'over_max_rejected'
    assert event['schema_version'] == 1
    assert 'uid' not in event
    assert 'user_id' not in event
    assert 'request_payload' not in event
    assert 'cursor_token' not in event
    assert 'memory_content' not in event


def test_rejects_unbounded_failure_reason_and_secret_cursor_or_raw_content_extras():
    with pytest.raises(ValueError, match='failure_reason'):
        build_v3_get_telemetry_event(_valid_input(failure_reason='traceback user abc123'))

    forbidden_extra_keys = [
        'uid',
        'user_id',
        'cursor',
        'cursor_token',
        'secret',
        'request_payload',
        'memory_content',
        'text',
    ]
    for key in forbidden_extra_keys:
        with pytest.raises(ValueError, match=key):
            build_v3_get_telemetry_event(_valid_input(extra_labels={key: 'sensitive-value'}))


def test_rejects_user_ids_as_labels_and_unexpected_high_cardinality_labels():
    with pytest.raises(ValueError, match='extra_labels'):
        build_v3_get_telemetry_event(_valid_input(extra_labels={'session_id': 'abc'}))

    with pytest.raises(ValueError, match='approval_owner'):
        build_v3_get_telemetry_event(_valid_input(approval_owner='uid_123456'))


def test_fake_sink_records_events_and_null_sink_proves_no_production_call_by_default():
    telemetry_input = _valid_input()
    null_result = emit_v3_get_telemetry(telemetry_input)
    assert null_result.emitted is False
    assert null_result.production_sink_call is False

    fake_sink = FakeV3TelemetrySink()
    fake_result = emit_v3_get_telemetry(telemetry_input, sink=fake_sink)
    assert fake_result.emitted is True
    assert fake_result.production_sink_call is False
    assert len(fake_sink.events) == 1
    assert fake_sink.events[0]['telemetry_sink'] == 'fake_local_test_sink'

    explicit_null = NullV3TelemetrySink()
    assert explicit_null.events == []


def test_read_disable_config_enrolled_users_fail_closed_for_missing_malformed_or_disabled():
    missing = decide_v3_read_disable(config=None, enrolled_memory_user=True)
    assert missing.memory_reads_enabled is False
    assert missing.rollback_read_disable_gate == 'disabled'
    assert missing.failure_reason == 'control_missing'
    assert missing.fail_closed is True

    malformed = decide_v3_read_disable(config={'schema_version': '1'}, enrolled_memory_user=True)
    assert malformed.memory_reads_enabled is False
    assert malformed.failure_reason == 'control_malformed'
    assert malformed.fail_closed is True

    disabled = decide_v3_read_disable(
        config=V3ReadDisableConfig(schema_version=1, memory_reads_enabled=True, emergency_read_disable=True),
        enrolled_memory_user=True,
    )
    assert disabled.memory_reads_enabled is False
    assert disabled.rollback_read_disable_gate == 'disabled'
    assert disabled.failure_reason == 'rollback_read_disabled'
    assert disabled.fail_closed is True


def test_read_disable_config_enabled_only_for_valid_server_owned_config():
    decision = decide_v3_read_disable(
        config=V3ReadDisableConfig(schema_version=1, memory_reads_enabled=True, emergency_read_disable=False),
        enrolled_memory_user=True,
    )

    assert decision.memory_reads_enabled is True
    assert decision.rollback_read_disable_gate == 'enabled'
    assert decision.failure_reason == 'none'
    assert decision.fail_closed is False
    assert decision.source == 'server_owned_config_object'

    non_enrolled = decide_v3_read_disable(config=None, enrolled_memory_user=False)
    assert non_enrolled.memory_reads_enabled is False
    assert non_enrolled.rollback_read_disable_gate == 'not_wired'
    assert non_enrolled.failure_reason == 'none'
    assert non_enrolled.fail_closed is False
