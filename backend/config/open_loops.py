"""Open-loop extraction switches.

``OPEN_LOOPS_ENABLED`` ships on: the notes call extracts the open-loop fields
(delegations, others' commitments, one observed issue/blocker) and persists
them in a server-only conversation field. Setting it off removes the prompt
rules, keeps the flag-off notes schema byte-identical, and stops persisting.

``OPEN_LOOPS_CARD_POLISH_ENABLED`` is off by default: review cards render from
the deterministic template, and this switch alone admits the optional single
cheap-model polish call.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

OPEN_LOOPS_ENABLED_ENV = 'OPEN_LOOPS_ENABLED'
OPEN_LOOPS_CARD_POLISH_ENABLED_ENV = 'OPEN_LOOPS_CARD_POLISH_ENABLED'

_OFF = frozenset(('0', 'false', 'off', 'no'))


def _enabled(name: str, default: bool, environ: Mapping[str, str] | None) -> bool:
    raw = (os.environ if environ is None else environ).get(name)
    if raw is None:
        return default
    return raw.strip().casefold() not in _OFF


def open_loops_enabled(environ: Mapping[str, str] | None = None) -> bool:
    return _enabled(OPEN_LOOPS_ENABLED_ENV, True, environ)


def card_polish_enabled(environ: Mapping[str, str] | None = None) -> bool:
    return _enabled(OPEN_LOOPS_CARD_POLISH_ENABLED_ENV, False, environ)
