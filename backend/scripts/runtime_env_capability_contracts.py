"""Explicit deployable capability contracts for backend runtime admission.

Capability membership is intentionally independent of runtime flag presence.
An omitted flag must make a declared host fail admission, not make the host
disappear from validation.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from config.memory_rollout import MemoryRolloutMode, rollout_mode_env_value
from scripts.runtime_env_durable_dispatch_contracts import ValidationError

ConfigDict = dict[str, Any]

CONVERSATION_FINALIZATION_CAPABILITY = 'conversation.finalize.persisted'
CANONICAL_MEMORY_MUTATION_CAPABILITY = 'memory.canonical.mutate'

_KNOWN_CAPABILITIES = frozenset(
    {
        CONVERSATION_FINALIZATION_CAPABILITY,
        CANONICAL_MEMORY_MUTATION_CAPABILITY,
    }
)
_FINALIZATION_CAPABILITIES = frozenset(
    {
        CONVERSATION_FINALIZATION_CAPABILITY,
        CANONICAL_MEMORY_MUTATION_CAPABILITY,
    }
)

# This roster is the independent authority for where persisted conversation
# finalization executes. Do not derive it from env keys or imports: omission of
# MEMORY_ENABLED from Pusher was the 2026-08-30 incident. backend-sync is the
# Cloud Tasks conversation-finalization writer for pendant/phone conversations.
_EXPECTED_DEPLOYABLE_CAPABILITIES: dict[tuple[str, str], frozenset[str]] = {
    ('gke', 'backend-listen'): _FINALIZATION_CAPABILITIES,
    ('gke', 'pusher'): _FINALIZATION_CAPABILITIES,
    ('cloud_run', 'backend'): _FINALIZATION_CAPABILITIES,
    ('cloud_run', 'backend-sync'): _FINALIZATION_CAPABILITIES,
}

# Declared on every finalization host with the same literal, or live capture
# (backend-listen / pusher / backend-sync) and regenerate (cloud_run/backend)
# silently run different pipelines. An omitted flag must fail admission, not
# fall through to the process-local False default.
SUMMARY_PIPELINE_FLAGS = (
    'CONVERSATION_NOTES_V2_ENABLED',
    'CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED',
    'CONVERSATION_OCR_CONTEXT_ENABLED',
)

# The runtime resolves these flags with strip().casefold() against the truthy
# set {'1','true','yes','on'}; anything else — including '' — is silently False.
# Admission therefore only accepts that truthy set and its falsy counterparts,
# so an empty or misspelled literal cannot pass the contract while behaving
# like the omitted/False case the contract exists to reject.
_SUMMARY_FLAG_LITERALS = frozenset({'1', 'true', 'yes', 'on', '0', 'false', 'no', 'off'})


def _as_config_dict(value: object) -> ConfigDict | None:
    return cast(ConfigDict, value) if isinstance(value, dict) else None


def _declared_capabilities(service_config: ConfigDict) -> tuple[frozenset[str], str | None]:
    raw = service_config.get('capabilities')
    if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
        return frozenset(), 'capabilities must be a non-empty list of strings'
    declared = frozenset(raw)
    if len(declared) != len(raw):
        return declared, 'capabilities must not contain duplicates'
    return declared, None


def _iter_declared_services(env_config: ConfigDict) -> Iterable[tuple[str, str, ConfigDict]]:
    gke = _as_config_dict(env_config.get('gke')) or {}
    for name, raw_service in gke.items():
        if name == 'config_map':
            continue
        service = _as_config_dict(raw_service)
        if service is not None and 'capabilities' in service:
            yield 'gke', name, service

    cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
    services = _as_config_dict(cloud_run.get('services')) or {}
    for name, raw_service in services.items():
        service = _as_config_dict(raw_service)
        if service is not None and 'capabilities' in service:
            yield 'cloud_run', name, service


def _service_config(env_config: ConfigDict, platform: str, service_name: str) -> ConfigDict | None:
    if platform == 'gke':
        services = _as_config_dict(env_config.get('gke')) or {}
    else:
        cloud_run = _as_config_dict(env_config.get('cloud_run')) or {}
        services = _as_config_dict(cloud_run.get('services')) or {}
    return _as_config_dict(services.get(service_name))


def _literal_env(service_config: ConfigDict) -> dict[str, str]:
    env = _as_config_dict(service_config.get('env')) or {}
    literal: dict[str, str] = {}
    for name, raw_entry in env.items():
        entry = _as_config_dict(raw_entry)
        if entry is not None and 'value' in entry:
            literal[name] = str(entry['value'])
    return literal


def validate_conversation_finalization_capabilities(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Validate the explicit finalization host roster and its memory-write fence."""

    errors: list[ValidationError] = []
    declared_by_host: dict[tuple[str, str], frozenset[str]] = {}
    summary_flag_values: dict[str, dict[str, str]] = {flag: {} for flag in SUMMARY_PIPELINE_FLAGS}

    for platform, service_name, service_config in _iter_declared_services(env_config):
        key = (platform, service_name)
        scope = f'{env}/{platform}/{service_name}'
        declared, shape_error = _declared_capabilities(service_config)
        declared_by_host[key] = declared
        if shape_error is not None:
            errors.append(ValidationError(scope, shape_error))

        unknown = sorted(declared - _KNOWN_CAPABILITIES)
        for capability in unknown:
            errors.append(ValidationError(scope, f'unknown runtime capability {capability!r}'))

        expected = _EXPECTED_DEPLOYABLE_CAPABILITIES.get(key)
        if expected is None and declared.intersection(_KNOWN_CAPABILITIES):
            errors.append(
                ValidationError(
                    scope,
                    'declares conversation-finalization capability but is not covered by the explicit deployable roster',
                )
            )
        elif expected is not None:
            for capability in sorted(declared - expected):
                errors.append(ValidationError(scope, f'capability {capability!r} is not permitted for this deployable'))

    for key, expected in _EXPECTED_DEPLOYABLE_CAPABILITIES.items():
        platform, service_name = key
        scope = f'{env}/{platform}/{service_name}'
        service_config = _service_config(env_config, platform, service_name)
        if service_config is None:
            errors.append(
                ValidationError(
                    scope,
                    'required conversation-finalization deployable is omitted from runtime_env',
                )
            )
            continue

        declared = declared_by_host.get(key, frozenset())
        for capability in sorted(expected - declared):
            errors.append(ValidationError(scope, f'missing required runtime capability {capability!r}'))

        # Use the production parser and its compatibility meaning. In
        # particular, legacy MEMORY_MODE=read still permits mutation today;
        # duplicating token policy here would let admission drift from runtime.
        literal_env = _literal_env(service_config)
        resolved_mode = rollout_mode_env_value(literal_env)
        if resolved_mode not in {MemoryRolloutMode.write.value, MemoryRolloutMode.read.value}:
            raw_enabled = literal_env.get('MEMORY_ENABLED')
            raw_mode = literal_env.get('MEMORY_MODE')
            errors.append(
                ValidationError(
                    scope,
                    'capability memory.canonical.mutate requires the runtime memory fence to permit writes; '
                    f'MEMORY_ENABLED={raw_enabled!r} MEMORY_MODE={raw_mode!r} resolves to {resolved_mode!r}',
                )
            )

        for flag in SUMMARY_PIPELINE_FLAGS:
            if flag not in literal_env:
                errors.append(
                    ValidationError(
                        scope,
                        f'summary-pipeline flag {flag} must be a literal on every conversation-finalization host',
                    )
                )
                continue
            # Compare raw literals, not normalized values: the pusher co-host
            # gate (verify_pusher_cohost_env_diff.py) enforces byte-identical
            # values for these same flags, so admission must not accept drift
            # (e.g. 'true' vs ' TRUE ') that the co-host gate would reject.
            summary_flag_values[flag][scope] = literal_env[flag]
            if literal_env[flag].strip().casefold() not in _SUMMARY_FLAG_LITERALS:
                errors.append(
                    ValidationError(
                        scope,
                        f'summary-pipeline flag {flag} must be an explicit boolean literal '
                        f'(true/false), got {literal_env[flag]!r}',
                    )
                )

    for flag, host_values in summary_flag_values.items():
        distinct = set(host_values.values())
        if len(distinct) > 1:
            rendered = ', '.join(f'{scope}={value!r}' for scope, value in sorted(host_values.items()))
            errors.append(
                ValidationError(
                    f'{env}/conversation-finalization',
                    f'summary-pipeline flag {flag} disagrees across finalization hosts: {rendered}',
                )
            )

    return errors


__all__ = [
    'CANONICAL_MEMORY_MUTATION_CAPABILITY',
    'CONVERSATION_FINALIZATION_CAPABILITY',
    'SUMMARY_PIPELINE_FLAGS',
    'validate_conversation_finalization_capabilities',
]
