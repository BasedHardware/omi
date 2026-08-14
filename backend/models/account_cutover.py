"""Whole-account cohort cutover contracts.

Server-authoritative whole-account cutover state is distinct from universal memory
membership and task-intelligence workflow mode. Those remain domain fences;
this model owns the account-wide legacy → migrating → new transition plus the
accepted lossy rollback that can strand new-backend writes.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from config.account_cutover import ACCOUNT_CUTOVER_SCHEMA_VERSION

# Persisted schema version is owned by config; keep the model literal aligned.
assert ACCOUNT_CUTOVER_SCHEMA_VERSION == 1

StableId = Annotated[
    str,
    StringConstraints(strip_whitespace=False, min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]*$'),
]


class AccountCutoverState(str, Enum):
    """Legal whole-account cutover states.

    ``rolled_back_stranded`` records that the account returned to the legacy
    data plane after ``new`` while acknowledging that new-backend writes may
    remain stranded and are not automatically reconciled.
    """

    legacy = 'legacy'
    migrating = 'migrating'
    new = 'new'
    rolled_back_stranded = 'rolled_back_stranded'


class OfflineQueueInstruction(str, Enum):
    """Server instruction for legacy offline/outbox queues on clients.

    ``drain`` is only legal before the migration fence (legacy plane still
    writable). ``quarantine`` applies once the account enters ``migrating``.
    """

    none = 'none'
    drain = 'drain'
    quarantine = 'quarantine'


class AccountCutoverClientAction(str, Enum):
    """Fail-closed client surface before product traffic."""

    none = 'none'
    force_upgrade = 'force_upgrade'
    migration_maintenance = 'migration_maintenance'


class AccountCutoverCheckpointPhase(str, Enum):
    """Forward-migration checkpoint phases (legacy-side seam only)."""

    not_started = 'not_started'
    inventory = 'inventory'
    offline_queue_fenced = 'offline_queue_fenced'
    exporting = 'exporting'
    importing = 'importing'
    verifying = 'verifying'
    cutover_ready = 'cutover_ready'
    completed = 'completed'
    failed = 'failed'
    paused = 'paused'


class PlatformMinimumBuild(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    platform: str = Field(min_length=1, max_length=32)
    minimum_supported_build: int = Field(ge=0)


class AccountCutoverManifestSummary(BaseModel):
    """Opaque forward-migration manifest identity without user content."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    manifest_id: Optional[StableId] = None
    schema_version: int = Field(default=1, ge=1)
    checkpoint_phase: AccountCutoverCheckpointPhase = AccountCutoverCheckpointPhase.not_started
    checkpoint_token: Optional[str] = Field(default=None, max_length=128)
    destination_backend_bound: bool = False
    stranded_new_data: bool = False


class AccountCutoverRecord(BaseModel):
    """Persisted server-authoritative cutover document."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    schema_version: Literal[1] = 1
    uid: str = Field(min_length=1)
    state: AccountCutoverState = AccountCutoverState.legacy
    account_generation: int = Field(default=0, ge=0)
    ui_generation: int = Field(default=0, ge=0)
    api_generation: int = Field(default=0, ge=0)
    stranded_new_data: bool = False
    offline_queue_instruction: OfflineQueueInstruction = OfflineQueueInstruction.none
    checkpoint_phase: AccountCutoverCheckpointPhase = AccountCutoverCheckpointPhase.not_started
    checkpoint_token: Optional[str] = Field(default=None, max_length=128)
    manifest_id: Optional[StableId] = None
    destination_backend_bound: bool = False

    def persisted_payload(self) -> dict[str, object]:
        return {
            'schema_version': ACCOUNT_CUTOVER_SCHEMA_VERSION,
            'uid': self.uid,
            'state': self.state.value,
            'account_generation': self.account_generation,
            'ui_generation': self.ui_generation,
            'api_generation': self.api_generation,
            'stranded_new_data': self.stranded_new_data,
            'offline_queue_instruction': self.offline_queue_instruction.value,
            'checkpoint_phase': self.checkpoint_phase.value,
            'checkpoint_token': self.checkpoint_token,
            'manifest_id': self.manifest_id,
            'destination_backend_bound': self.destination_backend_bound,
        }


class AccountCutoverControl(BaseModel):
    """Authenticated bootstrap/control projection for bridge clients."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    schema_version: Literal[1] = 1
    state: AccountCutoverState = AccountCutoverState.legacy
    account_generation: int = Field(default=0, ge=0)
    ui_generation: int = Field(default=0, ge=0)
    api_generation: int = Field(default=0, ge=0)
    client_action: AccountCutoverClientAction = AccountCutoverClientAction.none
    offline_queue_instruction: OfflineQueueInstruction = OfflineQueueInstruction.none
    stranded_new_data: bool = False
    legacy_writes_allowed: bool = True
    product_traffic_allowed: bool = True
    auth_bootstrap_reachable: bool = True
    minimum_supported_builds: tuple[PlatformMinimumBuild, ...] = ()
    migration: AccountCutoverManifestSummary = Field(default_factory=AccountCutoverManifestSummary)


class AccountCutoverTransitionRequest(BaseModel):
    """Operator/coordinator transition request (internal seam)."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    target_state: AccountCutoverState
    expected_account_generation: int = Field(ge=0)
    next_account_generation: Optional[int] = Field(default=None, ge=0)
    stranded_new_data: Optional[bool] = None
    offline_queue_instruction: Optional[OfflineQueueInstruction] = None
    checkpoint_phase: Optional[AccountCutoverCheckpointPhase] = None
    checkpoint_token: Optional[str] = Field(default=None, max_length=128)
    manifest_id: Optional[StableId] = None
    reason: str = Field(min_length=1, max_length=64)


__all__ = [
    'AccountCutoverCheckpointPhase',
    'AccountCutoverClientAction',
    'AccountCutoverControl',
    'AccountCutoverManifestSummary',
    'AccountCutoverRecord',
    'AccountCutoverState',
    'AccountCutoverTransitionRequest',
    'OfflineQueueInstruction',
    'PlatformMinimumBuild',
]
