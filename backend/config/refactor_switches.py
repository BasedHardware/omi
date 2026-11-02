"""Boolean-parser migration without changing a shadow host's serving path.

No-identity switches migrate only in global serve mode. Per-owner callers may
supply an identity to admit the configured capture-coverage serve cohort.
Imports stay lazy because refactor_modes itself imports config.policy.batch.
"""

from collections.abc import Mapping


def _enabled(uid: str | None, environ: Mapping[str, str] | None) -> bool:
    from config.refactor_modes import serving_for

    return serving_for('CAPTURE_COVERAGE_MODE', uid, environ=environ)


def default_on(name: str, legacy: bool, *, uid: str | None = None, environ=None) -> bool:
    from config.refactor_modes import default_on as parse

    # refactor: superseded by config.refactor_modes when CAPTURE_COVERAGE_MODE=serve
    return parse(name, environ=environ) if _enabled(uid, environ) else legacy


def default_off(name: str, legacy: bool, *, uid: str | None = None, environ=None) -> bool:
    from config.refactor_modes import default_off as parse

    # refactor: superseded by config.refactor_modes when CAPTURE_COVERAGE_MODE=serve
    return parse(name, environ=environ) if _enabled(uid, environ) else legacy
