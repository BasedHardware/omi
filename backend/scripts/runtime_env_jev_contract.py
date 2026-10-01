"""INV-MEM-5: the live Jev UID override belongs only in dev."""

from __future__ import annotations

from scripts.runtime_env_durable_dispatch_contracts import ValidationError

JEV_UID_ALLOWLIST = 'CONVERSATION_RELEVANCE_JEV_UID_ALLOWLIST'


def validate_jev_uid_allowlist(
    *,
    stage: str,
    scope: str,
    config: object,
    allow_empty_residue: bool = False,
    _seen: frozenset[int] = frozenset(),
) -> list[ValidationError]:
    """Reject declarations, including empty literals and secret bindings.

    Accept both manifest maps and rendered env lists so a binding omitted from
    the manifest cannot hide in chart values or exported Cloud Run state.

    ``allow_empty_residue`` is for the exported LIVE Cloud Run state read before a
    deploy: services that once declared the variable keep an empty entry until the
    deploy's ``--remove-env-vars`` strips it, and an empty entry cannot select
    anything (the arm only honors the allowlist in dev). A non-empty value or a
    secret/valueFrom binding is still rejected.
    """
    if stage != 'prod' or id(config) in _seen:
        # A cyclic YAML alias was already walked on this path; do not recurse forever.
        return []
    _seen = _seen | {id(config)}
    errors: list[ValidationError] = []
    if isinstance(config, dict):
        named = config.get('name') == JEV_UID_ALLOWLIST
        empty_residue = (
            allow_empty_residue and named and not config.get('value') and not (set(config) - {'name', 'value'})
        )
        if (JEV_UID_ALLOWLIST in config or named) and not empty_residue:
            errors.append(ValidationError(scope, f'{JEV_UID_ALLOWLIST} is dev-only and forbidden in prod'))
        for name, value in config.items():
            errors.extend(
                validate_jev_uid_allowlist(
                    stage=stage,
                    scope=f'{scope}/{name}',
                    config=value,
                    allow_empty_residue=allow_empty_residue,
                    _seen=_seen,
                )
            )
    elif isinstance(config, list):
        for index, value in enumerate(config):
            errors.extend(
                validate_jev_uid_allowlist(
                    stage=stage,
                    scope=f'{scope}/{index}',
                    config=value,
                    allow_empty_residue=allow_empty_residue,
                    _seen=_seen,
                )
            )
    return errors
