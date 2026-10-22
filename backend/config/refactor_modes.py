"""Rollout modes and boolean switches for the capture/speaker/notes refactor.

Every new path in the refactor (plan: KB capture-speaker-notes-refactor) reads its
mode here, so one parser decides what an env value means:

- ``off``: the old path only; the new code does not run.
- ``shadow``: the old path serves; the new path also runs and logs disagreements.
- ``serve``: the new path serves for the cohort (see :func:`serving_for`).

A mode env holds one of those words. An unknown value keeps the documented default
and is logged once, so a typo never silently flips a path. The serve cohort is
``<NAME>_SERVE_PERCENT`` (salted uid bucket) plus ``<NAME>_SERVE_UID_SHA256S``
(comma-separated sha256 hex digests of uids, kept in runtime env or Secret Manager,
never a raw uid in the repository).
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Literal

from config.policy.batch import cohort_bucket

logger = logging.getLogger(__name__)

Mode = Literal['off', 'shadow', 'serve']
_MODES: frozenset[str] = frozenset(('off', 'shadow', 'serve'))
_TRUE = frozenset(('1', 'true', 'on', 'yes'))
_FALSE = frozenset(('0', 'false', 'off', 'no'))
_warned: set[str] = set()


def _warn_once(name: str, raw: str) -> None:
    if name not in _warned:
        _warned.add(name)
        logger.warning('event=config_value_unrecognized name=%s', name)


def mode(name: str, default: Mode = 'shadow') -> Mode:
    raw = os.getenv(name, '').strip().lower()
    if not raw:
        return default
    if raw in _MODES:
        return raw  # type: ignore[return-value]
    _warn_once(name, raw)
    return default


def default_on(name: str) -> bool:
    """A kill switch: on unless explicitly set to a false word. Unknown values stay on."""
    raw = os.getenv(name, '').strip().lower()
    if raw in _FALSE:
        return False
    if raw and raw not in _TRUE:
        _warn_once(name, raw)
    return True


def default_off(name: str) -> bool:
    """An opt-in switch: off unless explicitly set to a true word. Unknown values stay off."""
    raw = os.getenv(name, '').strip().lower()
    if raw in _TRUE:
        return True
    if raw and raw not in _FALSE:
        _warn_once(name, raw)
    return False


def uid_digest(uid: str) -> str:
    return hashlib.sha256(uid.encode()).hexdigest()


def serving_for(name: str, uid: str | None, default: Mode = 'shadow') -> bool:
    """Whether the new path serves this uid. ``off`` and ``shadow`` serve only the cohort."""
    current = mode(name, default)
    if current == 'off':
        return False
    if current == 'serve':
        return True
    if not uid:
        return False
    digests = {d.strip().lower() for d in os.getenv(f'{name}_SERVE_UID_SHA256S', '').split(',') if d.strip()}
    if digests and uid_digest(uid) in digests:
        return True
    try:
        percent = float(os.getenv(f'{name}_SERVE_PERCENT', '0') or 0)
    except ValueError:
        _warn_once(f'{name}_SERVE_PERCENT', 'invalid')
        percent = 0.0
    return percent > 0 and cohort_bucket(uid, name.lower()) < percent


def shadow_or_serve(name: str, default: Mode = 'shadow') -> bool:
    """Whether the new path runs at all (to log in shadow, or to serve)."""
    return mode(name, default) != 'off'
