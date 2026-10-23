"""Versioned, immutable batch decisions. Resolution is an admission operation."""

from dataclasses import dataclass, fields
import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from config.policy.parts import PolicyPart, boolean, member, policy_environment, source_role
from config.rollout_cohorts import runtime_percent

# Compatibility exceptions: these deployed cohorts used the same unsalted
# sha256 first-four-byte bucket. A salt migration would reassign existing users.
COHORT_SALTS = {
    'batch-pipeline': '',
    'batch-live-stt-retire': '',  # intentionally nested in batch
    'first-summary': '',  # existing assignment retained (E1)
    'transcription-final-pass': '',  # existing assignment retained (E1)
}
LEGACY_CORRELATED_COHORTS = frozenset({'first-summary', 'transcription-final-pass'})
STT_ROUTES = frozenset({'parakeet', 'provider'})
PROVIDER_REASONS = frozenset({'none', 'byok', 'unsupported_language'})
PROVIDER_SERVICES = frozenset({'none', 'byok', 'soniox', 'deepgram', 'modulate'})
_ROUTE_DEFAULTS = {'stt_route': 'parakeet', 'provider_reason': 'none', 'provider_service': 'none'}
_UNSET = object()


def cohort_bucket(
    uid: str,
    salt: str,
    *,
    bits: int = 32,
    formula: str = 'fraction',
    separator: str = ':',
    clamp_upper: bool = False,
    empty_salt_prefix: bool = False,
) -> float:
    """Shared hash primitive preserving each deployed cohort's assignment.

    Fractional buckets use the first 32/64 bits scaled to [0, 100]. Older
    modulo cohorts deliberately retain their modulo bias. A caller's salt,
    width and separator are part of its persisted rollout contract.
    """
    if bits not in (32, 64):
        raise ValueError('cohort bucket requires 32 or 64 bits')
    if formula not in ('fraction', 'modulo'):
        raise ValueError('cohort bucket requires fraction or modulo formula')
    payload = f'{salt}{separator}{uid}' if salt or empty_salt_prefix else uid
    value = int.from_bytes(hashlib.sha256(payload.encode()).digest()[: bits // 8], 'big')
    bucket = value % 100 if formula == 'modulo' else value / 2**bits * 100
    return min(bucket, math.nextafter(100.0, 0.0)) if clamp_upper else bucket


@dataclass(frozen=True)
class BatchUnitPolicy(PolicyPart):
    schema_version: int = 1
    batch_enabled: bool = False
    batch_percent: float = 0.0
    batch_allowlisted: bool = False
    live_admission_enabled: bool = False
    live_record_enabled: bool = False
    retire_percent: float = 0.0
    live_stt_retired: bool = False
    final_pass_enabled: bool = False
    final_pass_authoritative: bool = False
    # Contract (c) STT route (lane 8): stamped by intake once the route is known.
    stt_route: str = 'parakeet'
    provider_reason: str = 'none'
    provider_service: str = 'none'

    def __post_init__(self):
        object.__setattr__(self, 'batch_percent', float(self.batch_percent))
        object.__setattr__(self, 'retire_percent', float(self.retire_percent))
        if self.live_stt_retired and not self.batch_enabled:
            raise ValueError('live STT retirement requires batch coverage')
        if not 0 <= self.retire_percent <= self.batch_percent <= 100:
            raise ValueError('retire percent must be nested within batch percent')
        if not _valid_route(self.stt_route, self.provider_reason, self.provider_service):
            raise ValueError('closed STT route fields required')
        super().__post_init__()
        # Additive fields enter the identity only when set: a snapshot stamped before
        # they existed keeps its stored policy_id (default route == pre-field row).
        content = {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name != 'policy_id' and _ROUTE_DEFAULTS.get(f.name, _UNSET) != getattr(self, f.name)
        }
        object.__setattr__(
            self,
            'policy_id',
            hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        )

    @classmethod
    def from_dict(cls, raw: object) -> 'BatchUnitPolicy':
        if not isinstance(raw, Mapping):
            raise ValueError('serialized admission policy must be a dict')
        values = dict(raw)
        values['batch_percent'] = parse_percent(str(values.get('batch_percent', 0)))
        values['retire_percent'] = min(parse_percent(str(values.get('retire_percent', 0))), values['batch_percent'])
        if not values.get('batch_enabled', False):
            values['live_stt_retired'] = False
        route = (values.get(key, default) for key, default in _ROUTE_DEFAULTS.items())
        if not _valid_route(*route):
            # A malformed route reads as the default (no BYOK funding claim): fail closed.
            for key in _ROUTE_DEFAULTS:
                values.pop(key, None)
        return super().from_dict(values)


def _valid_route(route: object, reason: object, service: object) -> bool:
    return (
        route in STT_ROUTES
        and reason in PROVIDER_REASONS
        and service in PROVIDER_SERVICES
        and (route == 'provider') == (service != 'none')
    )


def batch_generation_violations(policy_or_values: BatchUnitPolicy | Mapping[str, Any]) -> tuple[str, ...]:
    """Return impossible admission combinations for generated batch policies.

    Keep these relationships beside ``BatchUnitPolicy`` so the pairwise
    generator and its constraints evolve with the immutable policy shape.
    """

    def get(key: str) -> Any:
        if isinstance(policy_or_values, Mapping):
            return policy_or_values[key]
        return getattr(policy_or_values, key)

    def has(*keys: str) -> bool:
        return not isinstance(policy_or_values, Mapping) or all(key in policy_or_values for key in keys)

    violations: list[str] = []

    if (
        has('retire_percent', 'batch_percent')
        and not 0 <= float(get('retire_percent')) <= float(get('batch_percent')) <= 100
    ):
        violations.append('retire_percent_must_be_nested_within_batch_percent')
    if has('batch_allowlisted', 'batch_enabled') and bool(get('batch_allowlisted')) and not bool(get('batch_enabled')):
        violations.append('batch_allowlisted_requires_batch_enabled')
    if (
        has('batch_enabled', 'batch_percent', 'batch_allowlisted')
        and bool(get('batch_enabled'))
        and float(get('batch_percent')) == 0
        and not bool(get('batch_allowlisted'))
    ):
        violations.append('zero_percent_batch_requires_allowlist')
    if (
        has('live_record_enabled', 'batch_enabled', 'live_admission_enabled')
        and bool(get('live_record_enabled'))
        and not (bool(get('batch_enabled')) and bool(get('live_admission_enabled')))
    ):
        violations.append('live_record_requires_batch_and_live_admission')
    if (
        has('live_stt_retired', 'batch_enabled', 'retire_percent')
        and bool(get('live_stt_retired'))
        and not (bool(get('batch_enabled')) and float(get('retire_percent')) > 0)
    ):
        violations.append('live_stt_retirement_requires_batch_and_positive_retire_percent')
    if (
        has('final_pass_authoritative', 'final_pass_enabled')
        and bool(get('final_pass_authoritative'))
        and not bool(get('final_pass_enabled'))
    ):
        violations.append('authoritative_final_pass_requires_final_pass')
    return tuple(violations)


def parse_percent(raw: str) -> float:
    try:
        value = float(raw)
        return value if math.isfinite(value) and 0 <= value <= 100 else 0.0
    except (ValueError, TypeError):
        return 0.0


def resolve_batch_policy(
    uid: str, *, flags: Mapping[str, str] | None = None, now=None, source='admission'
) -> BatchUnitPolicy:
    """Read each input once. Explicit flags are a hermetic complete environment.

    ``now``/``source`` describe the caller, never policy identity. Membership
    comes from the configured rollout cache in production and explicit flags in
    replay. Retire is clamped to batch percent and also requires batch admission.
    """
    env = policy_environment(flags)

    def cohort(name, key):
        return member(uid, env, name, key, explicit=flags is not None)

    def enabled(key, default='false', *, strip=True):
        return boolean(env, key, default, strip=strip, uid=uid)

    percent_raw = env.get('BATCH_PIPELINE_PERCENT', '0')
    percent = parse_percent(percent_raw)
    try:
        valid_percent = math.isfinite(float(percent_raw)) and 0 <= float(percent_raw) <= 100
    except ValueError:
        valid_percent = False
    if flags is None:
        # Contract (f): production reads the percent from `rollout_cohorts/_ramp` (30s cache, LKG on
        # error) and records it in the snapshot; the env value stays the fail-safe when no document
        # sets it. Explicit flags (hermetic replay) are a complete environment and never read _ramp.
        ramped = runtime_percent('batch-pipeline', env_default=math.nan)
        if math.isfinite(ramped):
            percent, valid_percent = parse_percent(str(ramped)), True
    eligible = enabled('BATCH_PIPELINE_ENABLED', strip=False) and valid_percent and bool(uid)
    allowlisted = eligible and cohort('batch-pipeline', 'BATCH_PIPELINE_UID_ALLOWLIST')
    batch = eligible and (allowlisted or cohort_bucket(uid, COHORT_SALTS['batch-pipeline']) < percent)
    live_admission = enabled('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', strip=False)
    retire_raw = env.get('BATCH_LIVE_STT_RETIRE_PERCENT', '0')
    if flags is None:
        ramped_retire = runtime_percent('batch-live-stt-retire', env_default=math.nan)
        if math.isfinite(ramped_retire):
            retire_raw = str(ramped_retire)
    retire = min(parse_percent(retire_raw), percent)
    final_pass = False
    if env.get('TRANSCRIPTION_FINAL_PASS_DIARIZER', 'legacy') == 'pyannote_shadow':
        final_percent = max(0.0, min(100.0, float(env.get('TRANSCRIPTION_FINAL_PASS_PERCENT', '0'))))
        final_pass = cohort('transcription-final-pass', 'TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST') or (
            cohort_bucket(uid, COHORT_SALTS['transcription-final-pass']) < final_percent
        )
    return BatchUnitPolicy(
        source_role=source_role(env, 'admission'),
        batch_enabled=batch,
        batch_percent=percent,
        batch_allowlisted=allowlisted,
        live_admission_enabled=live_admission,
        live_record_enabled=live_admission and batch,
        retire_percent=retire,
        live_stt_retired=batch and bool(uid) and cohort_bucket(uid, COHORT_SALTS['batch-live-stt-retire']) < retire,
        final_pass_enabled=final_pass,
        final_pass_authoritative=final_pass and enabled('TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE', strip=False),
    )


# E1 scope for CI and hermetic harness environment separation. Worker
# dispositions, service discovery/auth and process lifecycle are E1b/control config.
SNAPSHOT_ENV_KEYS = frozenset(
    {
        'BATCH_PIPELINE_ENABLED',
        'BATCH_PIPELINE_PERCENT',
        'BATCH_PIPELINE_UID_ALLOWLIST',
        'BATCH_PIPELINE_LIVE_ADMISSION_ENABLED',
        'BATCH_LIVE_STT_RETIRE_PERCENT',
        'BATCH_PIPELINE_RECOVERY_MODE',
        'BATCH_PIPELINE_RECOVERY_ALL_ADMITTED',
        'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST',
        'BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED',
        'BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED',
        'BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED',
        'BATCH_PIPELINE_REQUIRE_LIVE_TARGET_ENABLED',
        'BATCH_PIPELINE_PROJECTION_TIMING_ENABLED',
        'BATCH_PIPELINE_HEAD_PRIORITY_ENABLED',
        'BATCH_PIPELINE_SHARED_LIVE_ENABLED',
        'BATCH_PIPELINE_MAX_ATTEMPTS',
        'BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED',
        'BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED',
    }
)
