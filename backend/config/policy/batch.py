"""Versioned, immutable batch decisions. Resolution is an admission operation."""

from dataclasses import asdict, dataclass, field, fields
import hashlib
import json
import math
import os
from collections.abc import Mapping

# Compatibility exceptions: these deployed cohorts used the same unsalted
# sha256 first-four-byte bucket. A salt migration would reassign existing users.
COHORT_SALTS = {
    'batch-pipeline': '',
    'batch-live-stt-retire': '',  # intentionally nested in batch
    'first-summary': '',  # existing assignment retained (E1)
    'transcription-final-pass': '',  # existing assignment retained (E1)
}
LEGACY_CORRELATED_COHORTS = frozenset({'first-summary', 'transcription-final-pass'})


def cohort_bucket(uid: str, salt: str) -> float:
    payload = uid if not salt else f'{salt}:{uid}'
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:4], 'big') / 2**32 * 100


@dataclass(frozen=True)
class BatchUnitPolicy:
    schema_version: int = 1
    batch_enabled: bool = False
    batch_percent: float = 0.0
    batch_allowlisted: bool = False
    live_admission_enabled: bool = False
    live_record_enabled: bool = False
    retire_percent: float = 0.0
    live_stt_retired: bool = False
    recovery_mode: str = 'off'
    recovery_all_admitted: bool = False
    recovery_allowlisted: bool = False
    recovery_enabled: bool = False
    projection_contention: bool = False
    async_projection: bool = False
    authoritative_labels: bool = False
    require_live_target: bool = False
    projection_timing: bool = False
    head_priority: bool = False
    shared_live: bool = False
    max_attempts: int = 5
    speech_empty_multilingual: bool = False
    terminal_empty_disposition: bool = False
    first_summary_enabled: bool = False
    first_summary_deadline_seconds: int = 120
    final_pass_enabled: bool = False
    final_pass_authoritative: bool = False
    policy_id: str = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, 'batch_percent', float(self.batch_percent))
        object.__setattr__(self, 'retire_percent', float(self.retire_percent))
        if self.live_stt_retired and not self.batch_enabled:
            raise ValueError('live STT retirement requires batch coverage')
        if not 0 <= self.retire_percent <= self.batch_percent <= 100:
            raise ValueError('retire percent must be nested within batch percent')
        content = {f.name: getattr(self, f.name) for f in fields(self) if f.name != 'policy_id'}
        object.__setattr__(
            self,
            'policy_id',
            hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping) -> 'BatchUnitPolicy':
        # Never read today's env to fill a partial historical snapshot. Unknown
        # additive fields are ignored; absent fields use the original code defaults.
        defaults = cls()
        values = {}
        for f in fields(cls):
            if not f.init or f.name not in raw:
                continue
            value, default = raw[f.name], getattr(defaults, f.name)
            if type(value) is type(default) or (type(default) is float and type(value) is int):
                values[f.name] = float(value) if type(default) is float else value
        values['batch_percent'] = _percent(str(values.get('batch_percent', 0)))
        values['retire_percent'] = min(_percent(str(values.get('retire_percent', 0))), values['batch_percent'])
        attempts = values.get('max_attempts', 5)
        values['max_attempts'] = attempts if 1 <= attempts <= 20 else 5
        values['first_summary_deadline_seconds'] = max(60, min(120, values.get('first_summary_deadline_seconds', 120)))
        if not values.get('batch_enabled', False):
            values['live_stt_retired'] = False
        return cls(**values)


def _percent(raw: str) -> float:
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
    from config.rollout_cohorts import in_rollout_cohort

    env = dict(os.environ if flags is None else flags)

    def member(name, key):
        if flags is None:
            members = tuple(value.strip() for value in env.get(key, '').split(',') if value.strip())
            return in_rollout_cohort(uid, name, legacy_members=members)
        return bool(uid) and uid in {value.strip() for value in env.get(key, '').split(',') if value.strip()}

    def boolean(key, default='false', *, strip=True):
        value = env.get(key, default)
        return (value.strip() if strip else value).lower() == 'true'

    percent_raw = env.get('BATCH_PIPELINE_PERCENT', '0')
    percent = _percent(percent_raw)
    try:
        valid_percent = math.isfinite(float(percent_raw)) and 0 <= float(percent_raw) <= 100
    except ValueError:
        valid_percent = False
    allowlisted = member('batch-pipeline', 'BATCH_PIPELINE_UID_ALLOWLIST')
    batch = (
        boolean('BATCH_PIPELINE_ENABLED', strip=False)
        and valid_percent
        and bool(uid)
        and (allowlisted or cohort_bucket(uid, COHORT_SALTS['batch-pipeline']) < percent)
    )
    live_admission = boolean('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', strip=False)
    retire = min(_percent(env.get('BATCH_LIVE_STT_RETIRE_PERCENT', '0')), percent)
    recovery_mode = env.get('BATCH_PIPELINE_RECOVERY_MODE', 'off')
    recovery_all = recovery_mode.lower() == 'on' and boolean('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', strip=False)
    recovery_allowlisted = member('batch-pipeline-recovery', 'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST')
    try:
        attempts = int(env.get('BATCH_PIPELINE_MAX_ATTEMPTS', '5'))
        attempts = attempts if 1 <= attempts <= 20 else 5
    except ValueError:
        attempts = 5
    summary = boolean('FIRST_SUMMARY_DEADLINE_ENABLED') and (
        member('first-summary', 'FIRST_SUMMARY_UID_ALLOWLIST')
        or bool(uid)
        and cohort_bucket(uid, COHORT_SALTS['first-summary']) < _percent(env.get('FIRST_SUMMARY_DEADLINE_PERCENT', '0'))
    )
    try:
        deadline = max(60, min(120, int(env.get('FIRST_SUMMARY_DEADLINE_SECONDS', '120'))))
    except ValueError:
        deadline = 120
    final_pass = False
    if env.get('TRANSCRIPTION_FINAL_PASS_DIARIZER', 'legacy') == 'pyannote_shadow':
        final_percent = max(0.0, min(100.0, float(env.get('TRANSCRIPTION_FINAL_PASS_PERCENT', '0'))))
        final_pass = member('transcription-final-pass', 'TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST') or (
            cohort_bucket(uid, COHORT_SALTS['transcription-final-pass']) < final_percent
        )
    return BatchUnitPolicy(
        batch_enabled=batch,
        batch_percent=percent,
        batch_allowlisted=allowlisted,
        live_admission_enabled=live_admission,
        live_record_enabled=live_admission and batch,
        retire_percent=retire,
        live_stt_retired=batch and bool(uid) and cohort_bucket(uid, COHORT_SALTS['batch-live-stt-retire']) < retire,
        recovery_mode=recovery_mode.strip().lower(),
        recovery_all_admitted=recovery_all,
        recovery_allowlisted=recovery_allowlisted,
        recovery_enabled=recovery_all or recovery_mode.strip().lower() == 'on' and recovery_allowlisted,
        projection_contention=boolean('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED'),
        async_projection=boolean('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED'),
        authoritative_labels=boolean('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', strip=False),
        require_live_target=boolean('BATCH_PIPELINE_REQUIRE_LIVE_TARGET_ENABLED', strip=False),
        projection_timing=boolean('BATCH_PIPELINE_PROJECTION_TIMING_ENABLED'),
        head_priority=boolean('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED'),
        shared_live=boolean('BATCH_PIPELINE_SHARED_LIVE_ENABLED', strip=False),
        max_attempts=attempts,
        speech_empty_multilingual=boolean('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED'),
        terminal_empty_disposition=boolean('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED'),
        first_summary_enabled=summary,
        first_summary_deadline_seconds=deadline,
        final_pass_enabled=final_pass,
        final_pass_authoritative=final_pass and boolean('TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE', strip=False),
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
