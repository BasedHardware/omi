"""Cohort admission and emergency stop for the free-tier rollout flags.

Before this module, ``FREE_TIER_LOCAL_PROCESSING`` and
``FREE_TIER_MEMORY_SUPPRESSION`` were global booleans: lighting one lit it for
100% of basic users on that environment, with no remote stop (direction review
2026-09-07 §7 item 3; flip review F-5). This module makes a lit flag mean
"lit for the configured cohort", fail-closed, and adds two stops that need no
cohort edit.

Admission (per flag, from the environment, read at call time):

    <FLAG>_COHORT = "uid:<uid>[,uid:<uid>...][,pct:<0-100>]"

* ``uid:<uid>`` admits that account.
* ``pct:<n>`` admits accounts whose stable hash bucket is below ``n``. The
  bucket is ``sha256("free-tier-cohort:" + uid)`` so both flags select the
  same accounts at the same percentage (one coherent product per user), and
  so the selection is independent of process, host, and time.
* Unset, empty, or malformed admits **nobody**. Malformed is logged once per
  process so a typo is discoverable without lighting anyone.

Stops (both revoke admission for everyone, including listed uids):

* ``FREE_TIER_EMERGENCY_STOP=true`` — environment; needs a redeploy.
* PostHog flag ``free-tier-kill-switch-v1`` — remote, honoured without a
  redeploy, read through the same bounded provider the JIT rollout uses
  (``utils.jit_rollout.PostHogJITFlagProvider``). Only a **definitively
  enabled** kill switch stops; unknown / absent / PostHog down never blocks
  by itself, matching the JIT precedent, so an outage cannot re-light or
  un-light a cohort. The remote read happens only after the environment
  cohort admits the account, so a dark fleet makes no provider calls.

Callers that cannot name the account are never admitted: the policy modules
answer ``False`` for a lit flag when given no uid and log once. That is the
fail-closed default the direction review asked for — a boolean alone lights
nobody.
"""

# LIFECYCLE: permanent

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass

from utils.jit_rollout import JITFlagEvaluation, PostHogJITFlagProvider, TriState

logger = logging.getLogger(__name__)

COHORT_ENV_SUFFIX = '_COHORT'
EMERGENCY_STOP_ENV_VAR = 'FREE_TIER_EMERGENCY_STOP'
# Remote stop. The exposure key is required by the provider and is read but
# never used for admission: the environment cohort is the only admission
# source today. Do not turn it into one without a rollout record.
FREE_TIER_COHORT_FLAG_KEY = 'free-tier-cohort-v1'
FREE_TIER_KILL_SWITCH_FLAG_KEY = 'free-tier-kill-switch-v1'
_HASH_SALT = b'free-tier-cohort:'
_KILL_SWITCH_CACHE_SECONDS = 20.0
_KILL_SWITCH_RESULT_TIMEOUT_SECONDS = 5.0
_KILL_SWITCH_CACHE_ENTRIES = 4096

# Closed vocabulary; low cardinality so it can be logged and counted.
COHORT_REASONS: frozenset[str] = frozenset(
    {
        'cohort_unset',
        'cohort_malformed',
        'cohort_uid',
        'cohort_pct',
        'cohort_not_admitted',
        'no_uid',
        'emergency_stop_env',
        'kill_switch_remote',
    }
)


@dataclass(frozen=True)
class CohortDecision:
    admitted: bool
    reason: str

    def __post_init__(self) -> None:
        if self.reason not in COHORT_REASONS:
            raise ValueError(f'unknown cohort reason {self.reason!r}')


@dataclass(frozen=True)
class _ParsedCohort:
    uids: frozenset[str]
    pct: int  # 0..100


_warned_lock = threading.Lock()
_warned: set[str] = set()


def _warn_once(key: str, message: str, *args: object) -> None:
    with _warned_lock:
        if key in _warned:
            return
        _warned.add(key)
    logger.warning(message, *args)


def cohort_env_name(flag: str) -> str:
    return f'{flag}{COHORT_ENV_SUFFIX}'


def parse_cohort(raw: str | None) -> _ParsedCohort | None:
    """Parse ``uid:<uid>,pct:<n>`` tokens. ``None`` means "admit nobody"."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    uids: set[str] = set()
    pct: int | None = None
    for token in text.split(','):
        token = token.strip()
        if not token:
            continue
        kind, sep, value = token.partition(':')
        kind = kind.strip().lower()
        value = value.strip()
        if not sep or not value:
            return None
        if kind == 'uid':
            uids.add(value)
        elif kind == 'pct':
            if not value.isdigit():
                return None
            parsed = int(value)
            if parsed < 0 or parsed > 100 or pct is not None:
                return None
            pct = parsed
        else:
            return None
    if not uids and pct is None:
        return None
    return _ParsedCohort(uids=frozenset(uids), pct=pct or 0)


def cohort_bucket(uid: str) -> int:
    """Stable 0..99 bucket for a uid; shared by every free-tier flag."""
    digest = hashlib.sha256(_HASH_SALT + uid.encode('utf-8')).hexdigest()
    return int(digest[:8], 16) % 100


def emergency_stop_engaged() -> bool:
    return os.getenv(EMERGENCY_STOP_ENV_VAR, '').strip().lower() in {'1', 'true', 'yes'}


# --- remote kill switch ---------------------------------------------------

_provider: PostHogJITFlagProvider | None = None
_provider_lock = threading.Lock()
_control_loop: asyncio.AbstractEventLoop | None = None
_control_loop_lock = threading.Lock()
_cache_lock = threading.Lock()
_cache: OrderedDict[str, tuple[TriState, float]] = OrderedDict()


def _get_provider() -> PostHogJITFlagProvider:
    global _provider
    with _provider_lock:
        if _provider is None:
            _provider = PostHogJITFlagProvider(
                rollout_flag_key=FREE_TIER_COHORT_FLAG_KEY,
                kill_switch_flag_key=FREE_TIER_KILL_SWITCH_FLAG_KEY,
            )
        return _provider


def _get_control_loop() -> asyncio.AbstractEventLoop:
    # Same confinement rule as utils.jit_rollout: sync callers (finalization
    # threads, the FastAPI sync pool, the sweep) never touch the server loop.
    global _control_loop
    with _control_loop_lock:
        if _control_loop is None or _control_loop.is_closed():
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, name='free-tier-cohort-control-loop', daemon=True)
            thread.start()
            _control_loop = loop
        return _control_loop


def _kill_switch_state(uid: str) -> TriState:
    """Definitive remote kill state for one account; UNKNOWN on any failure.

    Tests monkeypatch this. The evaluation's exposure flag is ignored on
    purpose (see module docstring).
    """
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(uid)
        if entry is not None and entry[1] > now:
            _cache.move_to_end(uid)
            return entry[0]
    try:
        future = asyncio.run_coroutine_threadsafe(_get_provider()(uid), _get_control_loop())
        evaluation: JITFlagEvaluation = future.result(timeout=_KILL_SWITCH_RESULT_TIMEOUT_SECONDS)
        state = evaluation.kill_switch
    except FuturesTimeoutError:
        state = TriState.UNKNOWN
    except Exception:
        state = TriState.UNKNOWN
    # Unknown answers cache briefly (an outage must not pin a stale answer for
    # the full TTL); definitive answers cache for the full TTL.
    ttl = _KILL_SWITCH_CACHE_SECONDS if state != TriState.UNKNOWN else 5.0
    with _cache_lock:
        _cache[uid] = (state, time.monotonic() + ttl)
        _cache.move_to_end(uid)
        while len(_cache) > _KILL_SWITCH_CACHE_ENTRIES:
            _cache.popitem(last=False)
    return state


def reset_kill_switch_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()


# --- the decision ---------------------------------------------------------


def cohort_decision(flag: str, uid: str | None) -> CohortDecision:
    """Is ``uid`` admitted to ``flag``'s cohort right now?

    Order: environment stop, then environment cohort, then the remote kill
    switch (only for an admitted account). Every non-admitting answer is
    fail-closed and carries a reason from ``COHORT_REASONS``.
    """
    if uid is None or not str(uid).strip():
        _warn_once(
            f'{flag}:no_uid',
            'free-tier cohort: %s consulted without a uid; admitting nobody at that call site until it passes one',
            flag,
        )
        return CohortDecision(admitted=False, reason='no_uid')
    if emergency_stop_engaged():
        return CohortDecision(admitted=False, reason='emergency_stop_env')
    env_name = cohort_env_name(flag)
    raw = os.getenv(env_name)
    parsed = parse_cohort(raw)
    if parsed is None:
        if raw is not None and raw.strip():
            _warn_once(f'{env_name}:malformed', 'free-tier cohort: %s is malformed; admitting nobody', env_name)
            return CohortDecision(admitted=False, reason='cohort_malformed')
        return CohortDecision(admitted=False, reason='cohort_unset')
    uid_text = str(uid).strip()
    if uid_text in parsed.uids:
        reason = 'cohort_uid'
    elif cohort_bucket(uid_text) < parsed.pct:
        reason = 'cohort_pct'
    else:
        return CohortDecision(admitted=False, reason='cohort_not_admitted')
    if _kill_switch_state(uid_text) == TriState.ENABLED:
        return CohortDecision(admitted=False, reason='kill_switch_remote')
    return CohortDecision(admitted=True, reason=reason)


def cohort_admits(flag: str, uid: str | None) -> bool:
    return cohort_decision(flag, uid).admitted


__all__ = [
    'COHORT_REASONS',
    'CohortDecision',
    'EMERGENCY_STOP_ENV_VAR',
    'FREE_TIER_COHORT_FLAG_KEY',
    'FREE_TIER_KILL_SWITCH_FLAG_KEY',
    'cohort_admits',
    'cohort_bucket',
    'cohort_decision',
    'cohort_env_name',
    'emergency_stop_engaged',
    'parse_cohort',
    'reset_kill_switch_cache_for_tests',
]
