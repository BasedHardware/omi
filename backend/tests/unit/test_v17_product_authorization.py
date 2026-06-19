from config.v17_memory import V17Capabilities, V17Mode
from utils.memory.v17_default_read_rollout import (
    V17DefaultReadRolloutDecision,
    V17GlobalReadGateDecision,
    V17ReadDecision,
)
from utils.memory.v17_product_authorization import (
    V17ProductAuthorizationContext,
    authorize_v17_product_memory_route,
)


class _Readers:
    def __init__(self, *, global_gate, default_rollout=None, archive_rollout=None):
        self.global_gate = global_gate
        self.default_rollout = default_rollout
        self.archive_rollout = archive_rollout or default_rollout
        self.calls = []

    def read_global(self, *, db_client):
        self.calls.append(('global', db_client))
        return self.global_gate

    def read_default(self, *, uid, db_client, consumer):
        self.calls.append(('default', uid, db_client, consumer))
        return self.default_rollout

    def read_archive(self, *, uid, db_client, consumer):
        self.calls.append(('archive', uid, db_client, consumer))
        return self.archive_rollout


class _Db:
    pass


def _capabilities(*, reads_enabled=True):
    return V17Capabilities(
        uid='u1',
        mode=V17Mode.read if reads_enabled else V17Mode.off,
        legacy_only=not reads_enabled,
        shadow_artifacts_enabled=False,
        v17_writes_enabled=reads_enabled,
        v17_reads_enabled=reads_enabled,
        legacy_reads_authoritative=not reads_enabled,
        account_generation=3,
    )


def _rollout(*, read_decision=V17ReadDecision.USE_V17, default_grant=True, archive_capability=False, reason='ok'):
    return V17DefaultReadRolloutDecision(
        uid='u1',
        source_path='users/u1/memory_control/state',
        consumer='omi_chat',
        rollout_capabilities=_capabilities(reads_enabled=read_decision == V17ReadDecision.USE_V17),
        app_has_default_memory_grant=default_grant,
        archive_capability=archive_capability,
        vector_projection_commit_id='projection-1',
        reason=reason,
        explicit_read_decision=read_decision,
    )


def _global_gate(read_decision=V17ReadDecision.USE_V17, reason='ok'):
    return V17GlobalReadGateDecision(
        source_path='memory_control/v17_global_read_gate',
        read_decision=read_decision,
        reason=reason,
    )


def test_default_product_authorization_denies_missing_rollout_before_default_policy_or_item_access():
    readers = _Readers(
        global_gate=_global_gate(),
        default_rollout=_rollout(
            read_decision=V17ReadDecision.DENY_MEMORY, default_grant=False, reason='missing_rollout_state'
        ),
    )

    decision = authorize_v17_product_memory_route(
        V17ProductAuthorizationContext(uid='u1', consumer='omi_chat', surface='product_default_search'),
        db_client=_Db(),
        read_global_gate=readers.read_global,
        read_default_rollout=readers.read_default,
        read_archive_rollout=readers.read_archive,
    )

    assert decision.allowed is False
    assert decision.read_decision == V17ReadDecision.DENY_MEMORY
    assert decision.reason == 'missing_rollout_state'
    assert decision.policy is None
    assert readers.calls == [
        ('global', decision.db_client),
        ('default', 'u1', decision.db_client, 'omi_chat'),
    ]


def test_default_product_authorization_allows_enabled_granted_default_without_archive_visibility():
    readers = _Readers(global_gate=_global_gate(), default_rollout=_rollout(archive_capability=True))

    decision = authorize_v17_product_memory_route(
        V17ProductAuthorizationContext(
            uid='u1',
            consumer='omi_chat',
            surface='product_default_search',
            app_id='omi-chat',
            key_id='first-party-session',
            scopes=('memories.read',),
        ),
        db_client=_Db(),
        read_global_gate=readers.read_global,
        read_default_rollout=readers.read_default,
        read_archive_rollout=readers.read_archive,
    )

    assert decision.allowed is True
    assert decision.read_decision == V17ReadDecision.USE_V17
    assert decision.policy is not None
    assert decision.policy.archive_capability is False
    assert decision.policy.app_has_default_memory_grant is True
    assert decision.observability['app_context'] == {
        'app_id': 'omi-chat',
        'key_id': 'first-party-session',
        'scopes': ['memories.read'],
    }
    assert decision.observability['archive_default_visible'] is False
    assert readers.calls == [
        ('global', decision.db_client),
        ('default', 'u1', decision.db_client, 'omi_chat'),
    ]


def test_archive_authorization_requires_explicit_request_and_persisted_archive_capability():
    readers = _Readers(global_gate=_global_gate(), archive_rollout=_rollout(archive_capability=False))

    explicit_without_capability = authorize_v17_product_memory_route(
        V17ProductAuthorizationContext(
            uid='u1',
            consumer='omi_chat',
            surface='product_archive_search',
            explicit_archive_request=True,
            requires_archive_capability=True,
        ),
        db_client=_Db(),
        read_global_gate=readers.read_global,
        read_default_rollout=readers.read_default,
        read_archive_rollout=readers.read_archive,
    )

    assert explicit_without_capability.allowed is False
    assert explicit_without_capability.reason == 'missing_chat_archive_capability'
    assert explicit_without_capability.policy is None

    readers = _Readers(global_gate=_global_gate(), archive_rollout=_rollout(archive_capability=True))
    persisted_capability_without_explicit_request = authorize_v17_product_memory_route(
        V17ProductAuthorizationContext(
            uid='u1',
            consumer='omi_chat',
            surface='product_archive_search',
            explicit_archive_request=False,
            requires_archive_capability=True,
        ),
        db_client=_Db(),
        read_global_gate=readers.read_global,
        read_default_rollout=readers.read_default,
        read_archive_rollout=readers.read_archive,
    )

    assert persisted_capability_without_explicit_request.allowed is False
    assert persisted_capability_without_explicit_request.reason == 'missing_explicit_archive_request'
    assert persisted_capability_without_explicit_request.policy is None
    assert readers.calls == [('global', persisted_capability_without_explicit_request.db_client)]


def test_archive_authorization_allows_only_when_explicit_and_persisted_capability_are_both_present():
    readers = _Readers(global_gate=_global_gate(), archive_rollout=_rollout(archive_capability=True))

    decision = authorize_v17_product_memory_route(
        V17ProductAuthorizationContext(
            uid='u1',
            consumer='omi_chat',
            surface='product_archive_search',
            explicit_archive_request=True,
            requires_archive_capability=True,
        ),
        db_client=_Db(),
        read_global_gate=readers.read_global,
        read_default_rollout=readers.read_default,
        read_archive_rollout=readers.read_archive,
    )

    assert decision.allowed is True
    assert decision.policy is not None
    assert decision.policy.archive_capability is True
    assert decision.observability['archive_capability_required'] is True
    assert decision.observability['archive_capability_granted'] is True
    assert decision.observability['archive_default_visible'] is False


def test_malformed_global_or_control_state_fails_closed_with_deterministic_reason():
    malformed_global = authorize_v17_product_memory_route(
        V17ProductAuthorizationContext(uid='u1', consumer='omi_chat', surface='product_default_search'),
        db_client=_Db(),
        read_global_gate=_Readers(
            global_gate=_global_gate(V17ReadDecision.DENY_MEMORY, 'malformed_global_read_gate')
        ).read_global,
    )

    assert malformed_global.allowed is False
    assert malformed_global.reason == 'malformed_global_read_gate'
    assert malformed_global.observability['read_decision'] == 'DENY_MEMORY'

    readers = _Readers(
        global_gate=_global_gate(),
        default_rollout=_rollout(
            read_decision=V17ReadDecision.DENY_MEMORY, default_grant=False, reason='malformed_rollout_state'
        ),
    )
    malformed_control = authorize_v17_product_memory_route(
        V17ProductAuthorizationContext(uid='u1', consumer='omi_chat', surface='product_default_search'),
        db_client=_Db(),
        read_global_gate=readers.read_global,
        read_default_rollout=readers.read_default,
    )

    assert malformed_control.allowed is False
    assert malformed_control.reason == 'malformed_rollout_state'
    assert malformed_control.observability['fallback_reason'] == 'malformed_rollout_state'
