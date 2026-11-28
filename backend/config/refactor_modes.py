"""Rollout modes and boolean switches for the capture/speaker/notes refactor.

Every new path in the refactor (plan: KB capture-speaker-notes-refactor) reads its
mode here, so one parser decides what an env value means:

- ``off``: the old path only; the new code does not run.
- ``shadow``: the old path serves; the new path also runs and logs disagreements.
- ``serve``: the new path serves for the cohort (see :func:`serving_for`).

A mode env holds one of those words. An unset mode is ``off`` (ruling: R-20261128-01,
proposed): a shadow runs only where runtime env says so, so it is visible in config and
in the registry. ``_LEGACY_SHADOW_DEFAULT`` keeps the old ``shadow`` default for the
families that relied on it before 2026-11-28; that set may only shrink, as each family is
bound, served or retired. A caller's explicit ``default`` still wins. An unknown value
keeps the default and is logged once, so a typo never silently flips a path. The serve cohort is
``<NAME>_SERVE_PERCENT`` (salted uid bucket) plus ``<NAME>_SERVE_UID_SHA256S``
(comma-separated sha256 hex digests of uids, kept in runtime env or Secret Manager,
never a raw uid in the repository).
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from datetime import date, datetime, timezone
from typing import Literal
from collections.abc import Mapping

from config.policy.batch import cohort_bucket
from config.shadow_expiry import SHADOW_EXPIRES

logger = logging.getLogger(__name__)

Mode = Literal['off', 'shadow', 'serve']
_MODES: frozenset[str] = frozenset(('off', 'shadow', 'serve'))

# Families that ran as implicit shadows (no env binding) before the default became off.
# Frozen: tests/unit/test_refactor_modes.py fails if a name is added. Remove a name when
# its family is bound in env, ramped to serve or retired; never add one.
_LEGACY_SHADOW_DEFAULT: frozenset[str] = frozenset(
    {
        'CALLS_RECAP_MODE',
        'CAPTURE_COVERAGE_MODE',
        'LIFECYCLE_V2_MODE',
        'NOTES_PACKET_V2_MODE',
        'SPEAKER_EVIDENCE_MODE',
    }
)
_TRUE = frozenset(('1', 'true', 'on', 'yes'))
_FALSE = frozenset(('0', 'false', 'off', 'no'))
_warned: set[str] = set()

# These producers and consumers must select the same accounts at every ramp
# step. Per-mode salts make a 1% consumer almost never share a 1% producer.
WAVE2_MODES = frozenset(
    f'{name}_MODE'
    for name in (
        'SPEAKER_EVIDENCE',
        'MEDIA_NOISE',
        'CAPTURE_COVERAGE',
        'NOTES_PACKET_V2',
        'LIFECYCLE_V2',
        'CALLS_RECAP',
        'ACTION_ITEMS_V2',
        'STT_VOCAB',
    )
)
WAVE2_COHORT_SALT = 'capture-speaker-notes:wave2'


# Typed bindings make the generic cohort reader visible to registry validation.
CONVERSATION_TERMINAL_FAMILY_MODE_ENV = 'CONVERSATION_TERMINAL_FAMILY_MODE'
PUSHER_RECORD_CLOSE_NOTIFY_ENV = 'PUSHER_RECORD_CLOSE_NOTIFY_ENABLED'
PUSHER_RECORD_CLOSE_NOTIFY_SERVE_PERCENT_ENV = 'PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_PERCENT'
PUSHER_RECORD_CLOSE_NOTIFY_SERVE_UID_SHA256S_ENV = 'PUSHER_RECORD_CLOSE_NOTIFY_ENABLED_SERVE_UID_SHA256S'
RECORD_TOKEN_LEASE_MODE_ENV = 'RECORD_TOKEN_LEASE_MODE'
RECORD_TOKEN_LEASE_SERVE_PERCENT_ENV = 'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT'
RECORD_TOKEN_LEASE_SERVE_UID_SHA256S_ENV = 'RECORD_TOKEN_LEASE_MODE_SERVE_UID_SHA256S'
FROM_SEGMENTS_CONTINUED_PROCESSING_MODE_ENV = 'FROM_SEGMENTS_CONTINUED_PROCESSING_MODE'
FROM_SEGMENTS_CONTINUED_PROCESSING_SERVE_PERCENT_ENV = 'FROM_SEGMENTS_CONTINUED_PROCESSING_MODE_SERVE_PERCENT'
FROM_SEGMENTS_CONTINUED_PROCESSING_SERVE_UID_SHA256S_ENV = 'FROM_SEGMENTS_CONTINUED_PROCESSING_MODE_SERVE_UID_SHA256S'
CAPTURE_COVERAGE_MODE_ENV = 'CAPTURE_COVERAGE_MODE'
CAPTURE_COVERAGE_SERVE_PERCENT_ENV = 'CAPTURE_COVERAGE_MODE_SERVE_PERCENT'
CAPTURE_COVERAGE_SERVE_UID_SHA256S_ENV = 'CAPTURE_COVERAGE_MODE_SERVE_UID_SHA256S'
CALLS_RECAP_SERVE_PERCENT_ENV = 'CALLS_RECAP_MODE_SERVE_PERCENT'
CALLS_RECAP_SERVE_UID_SHA256S_ENV = 'CALLS_RECAP_MODE_SERVE_UID_SHA256S'
ACTION_ITEMS_V2_SERVE_PERCENT_ENV = 'ACTION_ITEMS_V2_MODE_SERVE_PERCENT'
ACTION_ITEMS_V2_SERVE_UID_SHA256S_ENV = 'ACTION_ITEMS_V2_MODE_SERVE_UID_SHA256S'
STT_VOCAB_SERVE_PERCENT_ENV = 'STT_VOCAB_MODE_SERVE_PERCENT'
STT_VOCAB_SERVE_UID_SHA256S_ENV = 'STT_VOCAB_MODE_SERVE_UID_SHA256S'
_COHORT_ENVS = {
    PUSHER_RECORD_CLOSE_NOTIFY_ENV: (
        PUSHER_RECORD_CLOSE_NOTIFY_SERVE_PERCENT_ENV,
        PUSHER_RECORD_CLOSE_NOTIFY_SERVE_UID_SHA256S_ENV,
    ),
    FROM_SEGMENTS_CONTINUED_PROCESSING_MODE_ENV: (
        FROM_SEGMENTS_CONTINUED_PROCESSING_SERVE_PERCENT_ENV,
        FROM_SEGMENTS_CONTINUED_PROCESSING_SERVE_UID_SHA256S_ENV,
    ),
    RECORD_TOKEN_LEASE_MODE_ENV: (RECORD_TOKEN_LEASE_SERVE_PERCENT_ENV, RECORD_TOKEN_LEASE_SERVE_UID_SHA256S_ENV),
    'CALLS_RECAP_MODE': (CALLS_RECAP_SERVE_PERCENT_ENV, CALLS_RECAP_SERVE_UID_SHA256S_ENV),
    'ACTION_ITEMS_V2_MODE': (ACTION_ITEMS_V2_SERVE_PERCENT_ENV, ACTION_ITEMS_V2_SERVE_UID_SHA256S_ENV),
    'STT_VOCAB_MODE': (STT_VOCAB_SERVE_PERCENT_ENV, STT_VOCAB_SERVE_UID_SHA256S_ENV),
    CAPTURE_COVERAGE_MODE_ENV: (CAPTURE_COVERAGE_SERVE_PERCENT_ENV, CAPTURE_COVERAGE_SERVE_UID_SHA256S_ENV),
}
CAPTURE_COVERAGE_SHADOW_PERCENT_ENV = 'CAPTURE_COVERAGE_MODE_SHADOW_PERCENT'
SPEAKER_EVIDENCE_SHADOW_PERCENT_ENV = 'SPEAKER_EVIDENCE_MODE_SHADOW_PERCENT'
MEDIA_NOISE_SHADOW_PERCENT_ENV = 'MEDIA_NOISE_MODE_SHADOW_PERCENT'
_SHADOW_PERCENT_ENVS = {
    CAPTURE_COVERAGE_MODE_ENV: CAPTURE_COVERAGE_SHADOW_PERCENT_ENV,
    'SPEAKER_EVIDENCE_MODE': SPEAKER_EVIDENCE_SHADOW_PERCENT_ENV,
    'MEDIA_NOISE_MODE': MEDIA_NOISE_SHADOW_PERCENT_ENV,
}


def _warn_once(name: str, raw: str) -> None:
    if name not in _warned:
        _warned.add(name)
        logger.warning('event=config_value_unrecognized name=%s', name)


def implicit_default(name: str) -> Mode:
    """The mode an unset or unrecognised binding resolves to when the caller names no default."""
    return 'shadow' if name in _LEGACY_SHADOW_DEFAULT else 'off'


_expired_logged: set[str] = set()


def _shadow_expired(name: str, today: date | None = None) -> bool:
    """True once a registry shadow row is past readout_by + grace (config/shadow_expiry.py)."""
    expires = SHADOW_EXPIRES.get(name)
    if expires is None:
        return False
    if (today or datetime.now(timezone.utc).date()) < date.fromisoformat(expires):
        return False
    if name not in _expired_logged:
        _expired_logged.add(name)
        logger.warning('event=shadow_expired name=%s expires=%s', name, expires)
    return True


def mode(name: str, default: Mode | None = None, *, environ: Mapping[str, str] | None = None) -> Mode:
    resolved = _parse_mode(name, default, environ)
    if resolved == 'shadow' and _shadow_expired(name):
        return 'off'
    return resolved


def _parse_mode(name: str, default: Mode | None, environ: Mapping[str, str] | None) -> Mode:
    if name == RECORD_TOKEN_LEASE_MODE_ENV:
        default = 'off'
    if default is None:
        default = implicit_default(name)
    raw = (os.environ if environ is None else environ).get(name, '').strip().lower()
    if not raw:
        return default
    if name == CONVERSATION_TERMINAL_FAMILY_MODE_ENV and raw == 'on':
        return 'serve'
    if raw in _MODES:
        return raw  # type: ignore[return-value]
    _warn_once(name, raw)
    return default


def default_on(name: str, *, environ: Mapping[str, str] | None = None) -> bool:
    """A kill switch: on unless explicitly set to a false word. Unknown values stay on."""
    raw = (os.environ if environ is None else environ).get(name, '').strip().lower()
    if raw in _FALSE:
        return False
    if raw and raw not in _TRUE:
        _warn_once(name, raw)
    return True


def default_off(name: str, *, environ: Mapping[str, str] | None = None) -> bool:
    """An opt-in switch: off unless explicitly set to a true word. Unknown values stay off."""
    raw = (os.environ if environ is None else environ).get(name, '').strip().lower()
    if raw in _TRUE:
        return True
    if raw and raw not in _FALSE:
        _warn_once(name, raw)
    return False


def quiet_empty_exit_enabled() -> bool:
    """Dark empty-row cleanup; uncertain server custody exits via orphan repair."""
    return default_off('QUIET_EMPTY_EXIT_ENABLED')


def batch_live_orphan_repair_enabled() -> bool:
    """Dark operator repair; retained audio exits via batch, empty rows via fenced cleanup."""
    return default_off('BATCH_LIVE_ORPHAN_REPAIR_ENABLED')


def no_speech_terminal_enabled() -> bool:
    """Default-on operator kill switch for the reversible no-speech terminal.

    Only the digest-approved operator tool reads this. No scheduled or automatic
    apply exists; false blocks new closes while undo always remains available.
    """
    return default_on('NO_SPEECH_TERMINAL_ENABLED')


def record_seal_repair_age_order() -> bool:
    """Prefer near-dead-letter records, then newest; off restores the name-ordered jobs scan."""
    return default_on('RECORD_SEAL_REPAIR_AGE_ORDER')


def raw_live_gapped_packs_enabled() -> bool:
    """Read gapped, unframed raw-live packs through their custody manifest.

    Off restores the pre-existing skip: a pack without a declared frame schema
    and a nonzero ``gap_count`` is not listed and cannot be decoded.
    """
    return default_on('RAW_LIVE_GAPPED_PACKS_ENABLED')


def inventory_manifest_body_cache_enabled() -> bool:
    return default_on('PRIVATE_SYNC_INVENTORY_MANIFEST_BODY_CACHE_ENABLED')


def batch_input_expiring_enabled() -> bool:
    """Stop held staging inputs at day 29; off restores the existing held lifecycle."""
    return default_on('BATCH_INPUT_EXPIRING_ENABLED')


def pipeline_ledger_enabled() -> bool:
    """Write-only in-flight ledger; off stops ledger writes and leaves capture behavior unchanged."""
    return default_on('PIPELINE_LEDGER')


def uid_digest(uid: str) -> str:
    return hashlib.sha256(uid.encode()).hexdigest()


def serving_for(
    name: str, uid: str | None, default: Mode | None = None, *, environ: Mapping[str, str] | None = None
) -> bool:
    """Whether the new path serves this uid. ``off`` and ``shadow`` serve only the cohort."""
    env = os.environ if environ is None else environ
    current = mode(name, default, environ=env)
    if current == 'off':
        return False
    if name == RECORD_TOKEN_LEASE_MODE_ENV:
        # Lease shadow is observation only; serve always honors its own cohort.
        if current != 'serve':
            return False
    elif current == 'serve':
        return True
    if not uid:
        return False
    percent_env, digests_env = _COHORT_ENVS.get(name, (f'{name}_SERVE_PERCENT', f'{name}_SERVE_UID_SHA256S'))
    digests = {d.strip().lower() for d in env.get(digests_env, '').split(',') if d.strip()}
    if digests and uid_digest(uid) in digests:
        return True
    try:
        percent = float(env.get(percent_env, '0') or 0)
    except ValueError:
        _warn_once(percent_env, 'invalid')
        percent = 0.0
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        _warn_once(percent_env, 'invalid')
        percent = 0.0
    salt = (
        'record-token-lease'
        if name == RECORD_TOKEN_LEASE_MODE_ENV
        else WAVE2_COHORT_SALT if name in WAVE2_MODES else name.lower()
    )
    return percent > 0 and cohort_bucket(uid, salt) < percent


def shadow_or_serve(name: str, default: Mode | None = None) -> bool:
    """Whether the new path runs at all (to log in shadow, or to serve)."""
    return mode(name, default) != 'off'


def cohort_configured(name: str, *, environ: Mapping[str, str] | None = None) -> bool:
    """Whether scheduling may need to discover a serve cohort before knowing its uid.

    Discovery never admits a user: the caller must still use serving_for on every
    selected row. Malformed/empty cohorts remain dormant like the serving parser.
    """
    env = os.environ if environ is None else environ
    current = mode(name, environ=env)
    if current != 'shadow':
        return current == 'serve'
    percent_env, digests_env = _COHORT_ENVS.get(name, (f'{name}_SERVE_PERCENT', f'{name}_SERVE_UID_SHA256S'))
    digests = [d.strip().lower() for d in env.get(digests_env, '').split(',')]
    if any(len(d) == 64 and all(c in '0123456789abcdef' for c in d) for d in digests):
        return True
    try:
        percent = float(env.get(percent_env, '0') or 0)
        return math.isfinite(percent) and 0 < percent <= 100
    except ValueError:
        return False


def shadow_sampled(name: str, uid: str | None, default_percent: float, default: Mode | None = None) -> bool:
    """Whether a costly shadow path runs for this uid: always for the serve cohort, else a uid sample.

    Shadow exists to measure; paying a database write for every user is not needed for that.
    ``<NAME>_SHADOW_PERCENT`` overrides ``default_percent`` (0 to 100).
    """
    if serving_for(name, uid, default):
        return True
    if mode(name, default) != 'shadow' or not uid:
        return False
    env = _SHADOW_PERCENT_ENVS.get(name, f'{name}_SHADOW_PERCENT')
    raw = os.getenv(env, '').strip()
    try:
        percent = float(raw) if raw else default_percent
    except ValueError:
        _warn_once(env, raw)
        percent = default_percent
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        _warn_once(env, raw)
        percent = default_percent
    return percent > 0 and cohort_bucket(uid, f'{name.lower()}:shadow') < percent
