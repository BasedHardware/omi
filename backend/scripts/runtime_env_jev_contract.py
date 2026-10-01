"""INV-MEM-5: the live Jev UID override belongs only in dev."""

from __future__ import annotations

from scripts.runtime_env_durable_dispatch_contracts import ValidationError

JEV_UID_ALLOWLIST = 'CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST'


def validate_jev_uid_allowlist(
    *, stage: str, scope: str, config: object, _seen: frozenset[int] = frozenset()
) -> list[ValidationError]:
    """Reject declarations, including empty literals and secret bindings.

    Accept both manifest maps and rendered env lists so a binding omitted from
    the manifest cannot hide in chart values or exported Cloud Run state.
    """
    if stage != 'prod' or id(config) in _seen:
        # A cyclic YAML alias was already walked on this path; do not recurse forever.
        return []
    _seen = _seen | {id(config)}
    errors: list[ValidationError] = []
    if isinstance(config, dict):
        if JEV_UID_ALLOWLIST in config or config.get('name') == JEV_UID_ALLOWLIST:
            errors.append(ValidationError(scope, f'{JEV_UID_ALLOWLIST} is dev-only and forbidden in prod'))
        for name, value in config.items():
            errors.extend(validate_jev_uid_allowlist(stage=stage, scope=f'{scope}/{name}', config=value, _seen=_seen))
    elif isinstance(config, list):
        for index, value in enumerate(config):
            errors.extend(validate_jev_uid_allowlist(stage=stage, scope=f'{scope}/{index}', config=value, _seen=_seen))
    return errors
