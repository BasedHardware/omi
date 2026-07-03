from testing.memory.v3_get_dependency_seam import (
    LOW_CARDINALITY_DECISION_CODES,
    V3GetDependencyAdapters,
    V3GetDependencyContext,
    V3GetDependencyDecision,
    plan_v3_get_dependency_chain,
)


def _adapters(events, **overrides):
    def auth(context):
        events.append('auth')
        return V3GetDependencyDecision.allowed('auth_ok', subject_uid='server-uid')

    def reject_override(context):
        events.append('reject_client_uid_override')
        if context.client_uid_override_present:
            return V3GetDependencyDecision.fail_closed('client_uid_override_rejected', http_status=403)
        return V3GetDependencyDecision.allowed('no_client_uid_override')

    def enrollment(context):
        events.append('enrollment_control')
        if not context.enrolled:
            return V3GetDependencyDecision.legacy('non_enrolled_legacy_primary')
        if not context.control_ready:
            return V3GetDependencyDecision.fail_closed('control_unavailable', http_status=503)
        return V3GetDependencyDecision.allowed('control_ok')

    def config(context):
        events.append('config')
        if not context.config_ready:
            return V3GetDependencyDecision.fail_closed('config_unavailable', http_status=503)
        return V3GetDependencyDecision.allowed('config_ok')

    def cursor(context):
        events.append('cursor')
        if not context.cursor_ready:
            return V3GetDependencyDecision.fail_closed('cursor_invalid', http_status=400)
        return V3GetDependencyDecision.allowed('cursor_ok')

    def projection_source(context):
        events.append('projection_source')
        if not context.projection_source_ready:
            return V3GetDependencyDecision.fail_closed('projection_source_unavailable', http_status=503)
        return V3GetDependencyDecision.allowed('projection_source_ok')

    def rate_limit_backpressure(context):
        events.append('rate_limit_backpressure')
        if not context.backpressure_ready:
            return V3GetDependencyDecision.fail_closed('backpressure_denied', http_status=429)
        return V3GetDependencyDecision.allowed('rate_limit_backpressure_ok')

    values = {
        'authenticate_subject': auth,
        'reject_client_uid_override': reject_override,
        'load_enrollment_control': enrollment,
        'validate_runtime_config': config,
        'validate_cursor': cursor,
        'select_projection_source': projection_source,
        'check_rate_limit_backpressure': rate_limit_backpressure,
    }
    values.update(overrides)
    return V3GetDependencyAdapters(**values)


def _context(**overrides):
    values = {
        'route': 'GET /v3/memories',
        'client_uid_override_present': False,
        'enrolled': True,
        'control_ready': True,
        'config_ready': True,
        'cursor_ready': True,
        'projection_source_ready': True,
        'backpressure_ready': True,
    }
    values.update(overrides)
    return V3GetDependencyContext(**values)


def test_dependency_seam_runs_auth_first_and_rate_limit_before_projection_read():
    events = []
    result = plan_v3_get_dependency_chain(_context(), _adapters(events))

    assert result.status == 'READY'
    assert result.subject_uid == 'server-uid'
    assert events == [
        'auth',
        'reject_client_uid_override',
        'enrollment_control',
        'config',
        'cursor',
        'projection_source',
        'rate_limit_backpressure',
    ]
    assert result.should_fetch_memory_projection is True
    assert result.should_fetch_legacy is False
    assert result.projection_reads_allowed_after_step == 'rate_limit_backpressure'
    assert result.route_wired is False


def test_dependency_seam_rejects_client_uid_override_before_control_or_reads():
    events = []
    result = plan_v3_get_dependency_chain(_context(client_uid_override_present=True), _adapters(events))

    assert result.status == 'BLOCKED'
    assert result.decision_code == 'client_uid_override_rejected'
    assert result.http_status == 403
    assert events == ['auth', 'reject_client_uid_override']
    assert result.should_fetch_memory_projection is False
    assert result.should_fetch_legacy is False


def test_dependency_seam_preserves_non_enrolled_legacy_path_without_merge():
    events = []
    result = plan_v3_get_dependency_chain(_context(enrolled=False), _adapters(events))

    assert result.status == 'LEGACY_PRIMARY_ONLY'
    assert result.decision_code == 'non_enrolled_legacy_primary'
    assert events == ['auth', 'reject_client_uid_override', 'enrollment_control']
    assert result.should_fetch_legacy is True
    assert result.should_fetch_memory_projection is False
    assert result.legacy_fallback_allowed is False
    assert result.memory_legacy_merge_allowed is False


def test_dependency_seam_fail_closed_cases_stop_before_reads():
    cases = [
        ('control_ready', False, 'control_unavailable', ['auth', 'reject_client_uid_override', 'enrollment_control']),
        (
            'config_ready',
            False,
            'config_unavailable',
            ['auth', 'reject_client_uid_override', 'enrollment_control', 'config'],
        ),
        (
            'cursor_ready',
            False,
            'cursor_invalid',
            ['auth', 'reject_client_uid_override', 'enrollment_control', 'config', 'cursor'],
        ),
        (
            'projection_source_ready',
            False,
            'projection_source_unavailable',
            ['auth', 'reject_client_uid_override', 'enrollment_control', 'config', 'cursor', 'projection_source'],
        ),
        (
            'backpressure_ready',
            False,
            'backpressure_denied',
            [
                'auth',
                'reject_client_uid_override',
                'enrollment_control',
                'config',
                'cursor',
                'projection_source',
                'rate_limit_backpressure',
            ],
        ),
    ]
    for field, value, code, expected_events in cases:
        events = []
        result = plan_v3_get_dependency_chain(_context(**{field: value}), _adapters(events))
        assert result.status == 'BLOCKED'
        assert result.decision_code == code
        assert events == expected_events
        assert result.should_fetch_memory_projection is False
        assert result.should_fetch_legacy is False
        assert result.logs_secret_material is False
        assert result.logs_cursor_token is False
        assert result.logs_user_content is False


def test_dependency_seam_uses_bounded_low_cardinality_decision_codes_only():
    events = []
    result = plan_v3_get_dependency_chain(_context(backpressure_ready=False), _adapters(events))

    assert result.decision_code in LOW_CARDINALITY_DECISION_CODES
    assert result.logged_fields == {
        'route': 'GET /v3/memories',
        'decision_code': 'backpressure_denied',
        'dependency_step': 'rate_limit_backpressure',
        'status': 'BLOCKED',
    }
    assert 'server-uid' not in repr(result.logged_fields)
    assert 'cursor' not in ''.join(result.logged_fields.values())


def test_dependency_seam_normalizes_adapter_exceptions_timeouts_and_malformed_returns():
    cases = [
        (
            'adapter_exception',
            lambda context: (_ for _ in ()).throw(RuntimeError('provider exploded with user-secret')),
            'dependency_adapter_exception',
            503,
        ),
        (
            'adapter_timeout',
            lambda context: (_ for _ in ()).throw(TimeoutError('cursor token timed out')),
            'dependency_adapter_timeout',
            504,
        ),
        ('adapter_malformed', lambda context: {'kind': 'allow'}, 'dependency_adapter_malformed_return', 503),
    ]
    for case_id, adapter, expected_code, expected_status in cases:
        events = []
        result = plan_v3_get_dependency_chain(_context(), _adapters(events, validate_runtime_config=adapter))

        assert result.status == 'BLOCKED', case_id
        assert result.http_status == expected_status
        assert result.decision_code == expected_code
        assert result.dependency_step == 'config'
        assert result.should_fetch_memory_projection is False
        assert result.should_fetch_legacy is False
        assert 'secret' not in repr(result.logged_fields)
        assert 'token' not in repr(result.logged_fields)


def test_dependency_seam_restricts_legacy_primary_to_non_enrolled_enrollment_boundary():
    events = []
    result = plan_v3_get_dependency_chain(
        _context(),
        _adapters(
            events,
            validate_runtime_config=lambda context: V3GetDependencyDecision.legacy('non_enrolled_legacy_primary'),
        ),
    )

    assert result.status == 'BLOCKED'
    assert result.http_status == 500
    assert result.decision_code == 'dependency_contract_violation'
    assert result.dependency_step == 'config'
    assert result.should_fetch_legacy is False
    assert result.should_fetch_memory_projection is False


def test_dependency_seam_validates_decision_kind_status_and_subject_invariants():
    bad_auth_subject = plan_v3_get_dependency_chain(
        _context(),
        _adapters([], authenticate_subject=lambda context: V3GetDependencyDecision.allowed('auth_ok')),
    )
    bad_fail_status = plan_v3_get_dependency_chain(
        _context(),
        _adapters(
            [],
            validate_cursor=lambda context: V3GetDependencyDecision.fail_closed('cursor_invalid', http_status=200),
        ),
    )
    bad_allow_status = plan_v3_get_dependency_chain(
        _context(),
        _adapters(
            [],
            validate_cursor=lambda context: V3GetDependencyDecision(
                kind='allow', decision_code='cursor_ok', http_status=503
            ),
        ),
    )
    bad_kind = plan_v3_get_dependency_chain(
        _context(),
        _adapters(
            [],
            validate_cursor=lambda context: V3GetDependencyDecision(kind='maybe', decision_code='cursor_ok'),  # type: ignore[arg-type]
        ),
    )

    assert bad_auth_subject.status == 'BLOCKED'
    assert bad_auth_subject.decision_code == 'dependency_contract_violation'
    assert bad_auth_subject.http_status == 500
    assert bad_fail_status.decision_code == 'dependency_contract_violation'
    assert bad_allow_status.decision_code == 'dependency_contract_violation'
    assert bad_kind.decision_code == 'dependency_contract_violation'
