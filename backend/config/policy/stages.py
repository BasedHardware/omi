"""Role-owned stage policy resolution, called only on the first persisted claim."""

from dataclasses import dataclass
import math
from typing import Literal, overload

from config.policy.batch import COHORT_SALTS, parse_percent, cohort_bucket
from config.policy.parts import PolicyPart, boolean, member, policy_environment, source_role


@dataclass(frozen=True)
class ProjectionPolicy(PolicyPart):
    source_role: str = 'projection'
    projection_contention: bool = False
    async_projection: bool = False
    authoritative_labels: bool = False
    require_live_target: bool = False
    projection_timing: bool = False


@dataclass(frozen=True)
class SchedulerPolicy(PolicyPart):
    source_role: str = 'scheduler'
    head_priority: bool = False
    shared_live: bool = False
    max_attempts: int = 5

    def __post_init__(self):
        object.__setattr__(self, 'max_attempts', self.max_attempts if 1 <= self.max_attempts <= 20 else 5)
        super().__post_init__()


@dataclass(frozen=True)
class RecoveryPolicy(PolicyPart):
    source_role: str = 'recovery'
    recovery_mode: str = 'off'
    recovery_all_admitted: bool = False
    recovery_allowlisted: bool = False
    recovery_enabled: bool = False
    speech_empty_multilingual: bool = False
    terminal_empty_disposition: bool = False


@dataclass(frozen=True)
class FirstSummaryPolicy(PolicyPart):
    source_role: str = 'first_summary'
    first_summary_enabled: bool = False
    first_summary_deadline_seconds: int = 120

    def __post_init__(self):
        object.__setattr__(
            self, 'first_summary_deadline_seconds', max(60, min(120, self.first_summary_deadline_seconds))
        )
        super().__post_init__()


STAGE_TYPES = {
    'projection': ProjectionPolicy,
    'scheduler': SchedulerPolicy,
    'recovery': RecoveryPolicy,
    'first_summary': FirstSummaryPolicy,
}


@overload
def resolve_stage_policy(
    uid: str, stage: Literal['projection'], *, flags=None, obligation=None
) -> ProjectionPolicy: ...


@overload
def resolve_stage_policy(uid: str, stage: Literal['scheduler'], *, flags=None, obligation=None) -> SchedulerPolicy: ...


@overload
def resolve_stage_policy(uid: str, stage: Literal['recovery'], *, flags=None, obligation=None) -> RecoveryPolicy: ...


@overload
def resolve_stage_policy(
    uid: str, stage: Literal['first_summary'], *, flags=None, obligation=None
) -> FirstSummaryPolicy: ...


@overload
def resolve_stage_policy(uid: str, stage: str, *, flags=None, obligation=None) -> PolicyPart: ...


def resolve_stage_policy(uid: str, stage: str, *, flags=None, obligation=None) -> PolicyPart:
    env = policy_environment(flags)
    role = source_role(env, stage)
    if stage == 'projection':
        return ProjectionPolicy(
            source_role=role,
            projection_contention=boolean(env, 'BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED'),
            async_projection=boolean(env, 'BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED'),
            authoritative_labels=boolean(env, 'BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', strip=False),
            require_live_target=boolean(env, 'BATCH_PIPELINE_REQUIRE_LIVE_TARGET_ENABLED', strip=False),
            projection_timing=boolean(env, 'BATCH_PIPELINE_PROJECTION_TIMING_ENABLED'),
        )
    if stage == 'scheduler':
        try:
            attempts = int(env.get('BATCH_PIPELINE_MAX_ATTEMPTS', '5'))
        except ValueError:
            attempts = 5
        return SchedulerPolicy(
            source_role=role,
            head_priority=boolean(env, 'BATCH_PIPELINE_HEAD_PRIORITY_ENABLED'),
            shared_live=boolean(env, 'BATCH_PIPELINE_SHARED_LIVE_ENABLED', strip=False),
            max_attempts=attempts,
        )
    if stage == 'recovery':
        mode = env.get('BATCH_PIPELINE_RECOVERY_MODE', 'off')
        all_admitted = mode.lower() == 'on' and boolean(env, 'BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', strip=False)
        allowlisted = mode.strip().lower() == 'on' and member(
            uid, env, 'batch-pipeline-recovery', 'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', explicit=flags is not None
        )
        return RecoveryPolicy(
            source_role=role,
            recovery_mode=mode.strip().lower(),
            recovery_all_admitted=all_admitted,
            recovery_allowlisted=allowlisted,
            recovery_enabled=all_admitted or mode.strip().lower() == 'on' and allowlisted,
            speech_empty_multilingual=boolean(env, 'BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED'),
            terminal_empty_disposition=boolean(env, 'BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED'),
        )
    if stage == 'first_summary':
        master = boolean(env, 'FIRST_SUMMARY_DEADLINE_ENABLED')
        existing_deadline = (obligation or {}).get('summary_deadline_at')
        preserved = bool(
            master
            and obligation
            and not obligation.get('summary_seen')
            and not obligation.get('effects_only')
            and isinstance(existing_deadline, (int, float))
            and not isinstance(existing_deadline, bool)
            and math.isfinite(existing_deadline)
            and boolean(env, 'FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED')
        )
        enabled = (
            preserved
            or master
            and (
                member(uid, env, 'first-summary', 'FIRST_SUMMARY_UID_ALLOWLIST', explicit=flags is not None)
                or bool(uid)
                and cohort_bucket(uid, COHORT_SALTS['first-summary'])
                < parse_percent(env.get('FIRST_SUMMARY_DEADLINE_PERCENT', '0'))
            )
        )
        try:
            deadline = int(env.get('FIRST_SUMMARY_DEADLINE_SECONDS', '120'))
        except ValueError:
            deadline = 120
        return FirstSummaryPolicy(
            source_role=role, first_summary_enabled=enabled, first_summary_deadline_seconds=deadline
        )
    raise ValueError('unknown batch policy owner')
