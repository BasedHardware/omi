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
  redeploy, read with the same client configuration and tri-state mapping
  as the JIT rollout (``utils.jit_rollout``) but on this module's own small
  executor, so a stall here cannot occupy the JIT admission bulkhead and vice
  versa. Only a **definitively enabled** kill switch stops; unknown / absent
  / PostHog down never blocks by itself, matching the JIT precedent, so an
  outage cannot re-light or un-light a cohort. The remote read happens only
  after the environment cohort admits the account, so a dark fleet makes no
  provider calls; after a genuine provider failure (timeout, unconfigured,
  malformed, unexpected exception) the reader backs off for
  ``_PROVIDER_BACKOFF_SECONDS`` process-wide, so a sweep over hundreds of
  admitted accounts pays one timeout, not one per account. Hitting the
  in-flight cap is **not** a failure and never arms that backoff, so ordinary
  concurrency cannot blind the stop fleet-wide. Failures are logged once per
  class.

Callers that cannot name the account are never admitted: the policy modules
answer ``False`` for a lit flag when given no uid and log once. That is the
fail-closed default the direction review asked for — a boolean alone lights
nobody.
"""

# LIFECYCLE: permanent

from __future__ import annotations

import hashlib
import importlib
import logging
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

from utils.jit_rollout import TriState

logger = logging.getLogger(__name__)

COHORT_ENV_SUFFIX = '_COHORT'
EMERGENCY_STOP_ENV_VAR = 'FREE_TIER_EMERGENCY_STOP'
# Remote stop. Reserved exposure key: read by nothing, listed so nobody
# reuses the name for a different meaning. The environment cohort is the only
# admission source today; do not make PostHog one without a rollout record.
FREE_TIER_COHORT_FLAG_KEY = 'free-tier-cohort-v1'
FREE_TIER_KILL_SWITCH_FLAG_KEY = 'free-tier-kill-switch-v1'
_HASH_SALT = b'free-tier-cohort:'
_KILL_SWITCH_CACHE_SECONDS = 20.0
_KILL_SWITCH_UNKNOWN_CACHE_SECONDS = 5.0
_KILL_SWITCH_CACHE_ENTRIES = 4096
_POSTHOG_TIMEOUT_SECONDS = 2.0
# Must stay above the SDK's own timeout, and the in-flight cap must not exceed
# the worker count: a caller queued behind a busy worker would otherwise wait
# its predecessor's full client timeout plus its own and be misread as a
# provider timeout, arming the process-wide backoff on a healthy provider.
_POSTHOG_RESULT_TIMEOUT_SECONDS = 2.5
_PROVIDER_BACKOFF_SECONDS = 30.0
_PROVIDER_MAX_WORKERS = 2
_PROVIDER_MAX_IN_FLIGHT = _PROVIDER_MAX_WORKERS

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
            # A leading/trailing/doubled comma is a typo, not a semicolon:
            # fail closed so the operator notices instead of a silently
            # truncated (or entirely different) cohort going live.
            return None
        kind, sep, value = token.partition(':')
        kind = kind.strip().lower()
        value = value.strip()
        if not sep or not value:
            return None
        if kind == 'uid':
            uids.add(value)
        elif kind == 'pct':
            # ``str.isdigit`` accepts superscripts and non-ASCII digits that
            # ``int`` then rejects or silently converts; ASCII only.
            if not (value.isascii() and value.isdigit()):
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

_client: Any | None = None
_client_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()
_in_flight = threading.BoundedSemaphore(_PROVIDER_MAX_IN_FLIGHT)
_backoff_lock = threading.Lock()
_backoff_until = 0.0
_cache_lock = threading.Lock()
_cache: OrderedDict[str, tuple[TriState, float]] = OrderedDict()


def _build_posthog_client() -> Any | None:
    # Same configuration as utils.jit_rollout.PostHogJITFlagProvider._build_client.
    api_key = (os.getenv('POSTHOG_PROJECT_API_KEY') or os.getenv('POSTHOG_API_KEY') or '').strip()
    if not api_key:
        return None
    module = importlib.import_module('posthog')
    client_class = getattr(module, 'Posthog')
    return client_class(
        project_api_key=api_key,
        host=os.getenv('POSTHOG_HOST', 'https://app.posthog.com'),
        send=False,
        sync_mode=True,
        feature_flags_request_timeout_seconds=_POSTHOG_TIMEOUT_SECONDS,
    )


def _get_client() -> Any:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _build_posthog_client()
    if _client is None:
        raise LookupError('posthog_unconfigured')
    return _client


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=_PROVIDER_MAX_WORKERS, thread_name_prefix='free-tier-kill')
        return _executor


def close_free_tier_control_plane() -> None:
    """Stop accepting kill-switch work without blocking application shutdown.

    Mirrors ``utils.jit_rollout.close_posthog_control_plane``: queued calls
    are cancelled; already-running SDK calls retain their own bounded timeout
    and are not waited on here. A later in-process startup lazily creates a
    fresh isolated executor. Wired next to the JIT close hook in the service
    shutdown paths.
    """
    global _executor
    with _executor_lock:
        executor = _executor
        _executor = None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)


def _tri_state(flags: Mapping[str, Any], key: str) -> TriState:
    value = flags.get(key)
    if value is True:
        return TriState.ENABLED
    if value is False:
        return TriState.DISABLED
    return TriState.UNKNOWN


def _fetch_kill_switch(uid: str) -> TriState:
    """One bounded decide call; raises on any provider problem."""
    variants = _get_client().get_feature_variants(uid)
    if not isinstance(variants, Mapping):
        raise TypeError('malformed_feature_flags')
    # PostHog omits a boolean flag from a healthy decide response when it
    # evaluates false for the distinct id — the kill switch's normal dark
    # state. Following the JIT contract (utils.jit_rollout), absence in a
    # well-formed mapping means the provider was reachable and asserted no
    # kill: DISABLED, not UNKNOWN, so admitted accounts are not re-queried
    # every short unknown-TTL. UNKNOWN stays reserved for a present-but-
    # non-bool value and the whole-response failure paths.
    if FREE_TIER_KILL_SWITCH_FLAG_KEY not in variants:
        return TriState.DISABLED
    return _tri_state(variants, FREE_TIER_KILL_SWITCH_FLAG_KEY)


def _note_provider_failure(error_class: str) -> None:
    global _backoff_until
    with _backoff_lock:
        _backoff_until = time.monotonic() + _PROVIDER_BACKOFF_SECONDS
    _warn_once(
        f'kill_switch:{error_class}',
        'free-tier cohort: remote kill switch unavailable (%s); treating as unknown and backing off %ss',
        error_class,
        int(_PROVIDER_BACKOFF_SECONDS),
    )


def _kill_switch_state(uid: str) -> TriState:
    """Definitive remote kill state for one account; UNKNOWN on any failure.

    Tests monkeypatch this (or ``_fetch_kill_switch`` / ``_get_client``).
    Never raises. Bounded: one in-process cache, a small executor, an
    in-flight cap, a result timeout, and a process-wide backoff after any
    failure so a provider stall costs one wait, not one per account.
    """
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(uid)
        if entry is not None and entry[1] > now:
            _cache.move_to_end(uid)
            return entry[0]
    with _backoff_lock:
        backing_off = now < _backoff_until
    state = TriState.UNKNOWN
    if not backing_off:
        if not _in_flight.acquire(blocking=False):
            # Concurrency, not ill health. Arming the process-wide backoff here
            # would let ordinary load blind the kill switch fleet-wide for
            # 30 s at a time; this caller alone answers UNKNOWN (cached for the
            # short unknown TTL) and the next one re-reads.
            _warn_once(
                'kill_switch:saturated',
                'free-tier cohort: remote kill switch at its in-flight cap; treating as unknown for this call',
            )
        else:
            future: Future[TriState] | None = None
            try:
                future = _get_executor().submit(_fetch_kill_switch, uid)
                state = future.result(timeout=_POSTHOG_RESULT_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                if future is not None:
                    future.cancel()
                _note_provider_failure('timeout')
            except LookupError:
                _note_provider_failure('unconfigured')
            except TypeError:
                _note_provider_failure('malformed')
            except Exception as exc:
                _note_provider_failure(type(exc).__name__)
            finally:
                if future is None or future.done() or future.cancel():
                    _in_flight.release()
                else:
                    # A still-running fetch keeps its slot until it finishes.
                    future.add_done_callback(lambda _f: _in_flight.release())
    ttl = _KILL_SWITCH_CACHE_SECONDS if state != TriState.UNKNOWN else _KILL_SWITCH_UNKNOWN_CACHE_SECONDS
    with _cache_lock:
        _cache[uid] = (state, time.monotonic() + ttl)
        _cache.move_to_end(uid)
        while len(_cache) > _KILL_SWITCH_CACHE_ENTRIES:
            _cache.popitem(last=False)
    return state


def reset_kill_switch_cache_for_tests() -> None:
    global _backoff_until
    with _cache_lock:
        _cache.clear()
    with _backoff_lock:
        _backoff_until = 0.0


# --- the decision ---------------------------------------------------------


def cohort_decision(flag: str, uid: str | None) -> CohortDecision:
    """Is ``uid`` admitted to ``flag``'s cohort right now?

    Order: environment stop, then environment cohort, then the remote kill
    switch (only for an admitted account). Every non-admitting answer is
    fail-closed and carries a reason from ``COHORT_REASONS``.

    Total by construction: a lit flag sits on the finalization and sweep
    paths, so nothing this module can do may raise into them. The inner
    function is written to be total; this wrapper is the guarantee, because
    "the grammar is total" was already believed once about a narrower guard
    (a non-ASCII ``pct`` digit, a uid whose ``__str__`` or UTF-8 encode
    raises) and was wrong.
    """
    try:
        return _cohort_decision(flag, uid)
    except Exception:
        _warn_once(
            f'{flag}:decision_error',
            'free-tier cohort: %s decision raised; admitting nobody',
            flag,
        )
        return CohortDecision(admitted=False, reason='cohort_malformed')


def _cohort_decision(flag: str, uid: str | None) -> CohortDecision:
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
    try:
        parsed = parse_cohort(raw)
    except Exception:
        # The grammar is total, but a lit flag must never raise into a
        # finalization or the sweep: anything unexpected is "malformed".
        parsed = None
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
    'close_free_tier_control_plane',
    'cohort_admits',
    'cohort_bucket',
    'cohort_decision',
    'cohort_env_name',
    'emergency_stop_engaged',
    'parse_cohort',
    'reset_kill_switch_cache_for_tests',
]
