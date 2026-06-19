from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from config.v17_memory import V17Capabilities, V17Mode, V17RolloutState, decide_v17_capabilities
from database.v17_collections import V17Collections
from models.v17_product_memory import MemoryAccessPolicy, MemoryConsumer
from utils.memory.v17_product_memory_read_service import fetch_default_product_memory_search


@dataclass(frozen=True)
class V17DeveloperDefaultMemoryRolloutDecision:
    uid: str
    source_path: str
    rollout_capabilities: V17Capabilities
    app_has_default_memory_grant: bool
    archive_capability: bool = False
    reason: str = 'ok'

    @property
    def v17_default_developer_enabled(self) -> bool:
        return self.rollout_capabilities.v17_reads_enabled and self.app_has_default_memory_grant

    @property
    def fallback_reason(self) -> Optional[str]:
        if self.v17_default_developer_enabled:
            return None
        if self.reason != 'ok':
            return self.reason
        if not self.rollout_capabilities.v17_reads_enabled:
            return 'v17_reads_disabled'
        if not self.app_has_default_memory_grant:
            return 'missing_developer_default_memory_grant'
        return 'v17_default_developer_disabled'


def _disabled_v17_developer_rollout_decision(
    uid: str, source_path: str, reason: str
) -> V17DeveloperDefaultMemoryRolloutDecision:
    return V17DeveloperDefaultMemoryRolloutDecision(
        uid=uid,
        source_path=source_path,
        rollout_capabilities=V17Capabilities(
            uid=uid,
            mode=V17Mode.off,
            legacy_only=True,
            shadow_artifacts_enabled=False,
            v17_writes_enabled=False,
            v17_reads_enabled=False,
            legacy_reads_authoritative=True,
        ),
        app_has_default_memory_grant=False,
        archive_capability=False,
        reason=reason,
    )


def _developer_default_memory_grant_enabled(data: dict) -> bool:
    grants = data.get('grants')
    if isinstance(grants, dict):
        developer_grants = grants.get('developer') or grants.get('developer_api')
        if isinstance(developer_grants, dict) and developer_grants.get('default_memory') is True:
            return True
    return data.get('developer_default_memory_grant') is True


def read_v17_developer_default_memory_rollout(*, uid: str, db_client) -> V17DeveloperDefaultMemoryRolloutDecision:
    """Read server-owned V17 developer default-memory rollout state.

    The authoritative per-user document is `users/{uid}/memory_control/state`.
    Missing, malformed, uid-mismatched, or developer-grant-less docs fail closed
    before any `users/{uid}/memory_items` read. Archive stays default-disabled on
    this developer default-memory path regardless of persisted Archive fields.
    """

    source_path = V17Collections(uid=uid).memory_control_state
    try:
        snapshot = db_client.document(source_path).get()
        data = snapshot.to_dict() if getattr(snapshot, 'exists', True) else None
        if not isinstance(data, dict):
            return _disabled_v17_developer_rollout_decision(uid, source_path, 'missing_rollout_state')
        if data.get('uid', uid) != uid:
            return _disabled_v17_developer_rollout_decision(uid, source_path, 'uid_mismatch')

        state = V17RolloutState(
            uid=uid,
            mode=data.get('mode', V17Mode.off.value),
            mode_epoch=int(data.get('mode_epoch', 0) or 0),
            cutover_epoch=int(data.get('cutover_epoch', 0) or 0),
            account_generation=int(data.get('account_generation', 0) or 0),
            last_reconciled_legacy_revision=data.get('last_reconciled_legacy_revision'),
            fallback_projection_ready=data.get('fallback_projection_ready') is True,
            persistent_v17_writes_started=data.get('persistent_v17_writes_started') is True,
            decommission_reconciled=data.get('decommission_reconciled') is True,
            writes_blocked=data.get('writes_blocked') is True,
            stage_gates=data.get('stage_gates') or {},
        )
        capabilities = decide_v17_capabilities(uid, state.mode, state)
        return V17DeveloperDefaultMemoryRolloutDecision(
            uid=uid,
            source_path=source_path,
            rollout_capabilities=capabilities,
            app_has_default_memory_grant=_developer_default_memory_grant_enabled(data),
            archive_capability=False,
            reason='ok',
        )
    except (TypeError, ValueError, AttributeError):
        return _disabled_v17_developer_rollout_decision(uid, source_path, 'malformed_rollout_state')


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    raise ValueError('missing V17 memory timestamp')


def _format_developer_memory(item: dict, policy: MemoryAccessPolicy) -> dict:
    updated_at = _parse_datetime(item.get('date'))
    return {
        'id': item['memory_id'],
        'content': item.get('content') or '',
        'category': 'other',
        'visibility': 'private',
        'tags': ['v17_default_memory', f"tier:{item.get('tier')}"] if item.get('tier') else ['v17_default_memory'],
        'created_at': updated_at,
        'updated_at': updated_at,
        'manually_added': False,
        'scoring': None,
        'reviewed': True,
        'user_review': None,
        'edited': False,
        'v17_default_memory': True,
        'archive_default_visible': False,
        'policy': {
            'consumer': policy.consumer.value,
            'app_has_default_memory_grant': policy.app_has_default_memory_grant,
            'archive_capability': policy.archive_capability,
            'raw_provenance_capability': policy.raw_provenance_capability,
        },
    }


def search_v17_default_developer_memories(
    *,
    uid: str,
    query: str = '',
    limit: int,
    offset: int,
    db_client,
    rollout_capabilities: Optional[V17Capabilities],
    app_has_default_memory_grant: bool,
    now: Optional[datetime] = None,
) -> Optional[list[dict]]:
    """Return default-visible V17 product memories for the developer memory caller.

    Returns `None` when the concrete developer route should keep using the legacy
    `users/{uid}/memories` path. Firestore `memory_items` are touched only after
    persisted V17 read capability and developer default-memory grant both pass.
    """

    if not rollout_capabilities or not rollout_capabilities.v17_reads_enabled:
        return None
    if not app_has_default_memory_grant:
        return None

    bounded_limit = max(1, min(limit, 500))
    bounded_offset = max(0, offset)
    policy = MemoryAccessPolicy(
        consumer=MemoryConsumer.developer_api,
        app_has_default_memory_grant=True,
        archive_capability=False,
        raw_provenance_capability=False,
    )
    response = fetch_default_product_memory_search(
        uid=uid,
        query=query,
        db_client=db_client,
        policy=policy,
        now=now,
        limit=bounded_limit,
        offset=bounded_offset,
    )
    return [_format_developer_memory(item, policy) for item in response['items']]
