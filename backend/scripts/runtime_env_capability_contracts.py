"""Explicit deployable capability contracts for backend runtime admission.

Capability membership is intentionally independent of runtime flag presence.
An omitted flag must make a declared host fail admission, not make the host
disappear from validation.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any, cast

from config.memory_rollout import MemoryRolloutMode, rollout_mode_env_value
from scripts.runtime_env_durable_dispatch_contracts import ValidationError
from scripts.runtime_env_compat import VOICE_STAGING_BUCKET_ENV, VOICE_STAGING_BUCKETS

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

# Summary acceptance must agree on every finalization host.
FINALIZATION_GATE_FLAGS = ('CLIENT_SUMMARIES_AT_CAP_ENABLED',)

BATCH_FINAL_PASS_FLAG = 'BATCH_FINAL_PASS_ENABLED'
BATCH_FINAL_PASS_HOSTS = (
    ('gke', 'backend-listen'),
    ('gke', 'pusher'),
    ('cloud_run', 'backend'),
    ('cloud_run', 'backend-sync'),
    ('cloud_run', 'backend-sync-backfill'),
    ('cloud_run', 'backend-integration'),
)


HOSTED_DIARIZATION_URL_ENV = 'HOSTED_DIARIZATION_API_URL'


def _host_env(platform: str, name: str, config: ConfigDict) -> ConfigDict:
    services = config.get('gke', {}) if platform == 'gke' else config.get('cloud_run', {}).get('services', {})
    return (services.get(name, {}) or {}).get('env', {}) or {}


def _host_has_diarizer_url(platform: str, name: str, config: ConfigDict) -> bool:
    """True when the host can call the batch diarizer.

    A literal value decides. An unknown source (environment, secret, or any
    other non-literal binding) counts as present, so the check errs toward
    keeping the pass on.
    """
    env = _host_env(platform, name, config)
    if HOSTED_DIARIZATION_URL_ENV in env:
        return _binding_has_url(env[HOSTED_DIARIZATION_URL_ENV])
    if platform == 'cloud_run':
        services = config.get('cloud_run', {}).get('services', {})
        secrets = (services.get(name, {}) or {}).get('secrets', {}) or {}
        if HOSTED_DIARIZATION_URL_ENV in secrets:
            return True
    if platform == 'gke':
        shared = (config.get('gke', {}).get('config_map', {}) or {}).get('entries', {}) or {}
        if HOSTED_DIARIZATION_URL_ENV in shared:
            return _binding_has_url(shared[HOSTED_DIARIZATION_URL_ENV])
    return False


def _binding_has_url(binding: object) -> bool:
    if not isinstance(binding, dict):
        return True
    if 'value' not in binding:
        return True  # Not a literal: unknown source, keep the pass on.
    value = binding.get('value')
    return value is not None and bool(str(value).strip())


def validate_batch_final_pass_hosts(env: str, config: ConfigDict) -> list[ValidationError]:
    """Independent serving roster: deleting a binding cannot hide a runtime.

    Every production host needs an explicit true or false. A host without a
    diarizer URL may be switched off on its own, since its pass can only fall
    back. A host with the URL stays on unless every production host is off, which
    keeps the full rollback valid.
    """
    if env != 'prod':
        return []
    errors, values = [], {}
    gke = config.get('gke', {})
    config_map = gke.get('config_map', {})
    flag = BATCH_FINAL_PASS_FLAG
    for platform, name in BATCH_FINAL_PASS_HOSTS:
        services = gke if platform == 'gke' else config.get('cloud_run', {}).get('services', {})
        entry = services.get(name, {}).get('env', {}).get(flag, {})
        value = entry.get('value')
        if platform == 'gke':
            expected = {'name': config_map.get('name'), 'key': flag}
            if entry.get('config_map') != expected or not expected['name']:
                errors.append(ValidationError(f'{platform}/{name}', f'{flag} must use the shared ConfigMap'))
            source = config_map.get('entries', {}).get(flag, {})
            value = source.get('value') if source.get('source') == 'literal' else None
        if value not in {'true', 'false'}:
            errors.append(ValidationError(f'{platform}/{name}', f'{flag} needs an explicit true/false binding'))
        else:
            values[(platform, name)] = value
    if len(values) == len(BATCH_FINAL_PASS_HOSTS) and all(v == 'false' for v in values.values()):
        return errors  # Full rollback: every production host is off.
    for (platform, name), value in values.items():
        # GKE hosts share one ConfigMap entry, and their Helm values can carry the
        # URL outside the manifest, so a GKE host is never exempt from the rule.
        has_url = platform == 'gke' or _host_has_diarizer_url(platform, name, config)
        if value == 'false' and has_url:
            errors.append(
                ValidationError(
                    f'{platform}/{name}',
                    f'{flag} must stay true on a host with {HOSTED_DIARIZATION_URL_ENV} unless every production host is off',
                )
            )
        # An exempt Cloud Run host must also list the URL in forbidden_env, so the
        # live service state is checked for it and an undeclared binding cannot hide.
        if value == 'false' and platform == 'cloud_run' and not has_url:
            forbidden = config.get('cloud_run', {}).get('services', {}).get(name, {}).get('forbidden_env') or []
            if HOSTED_DIARIZATION_URL_ENV not in forbidden:
                errors.append(
                    ValidationError(
                        f'{platform}/{name}',
                        f'{flag}=false needs {HOSTED_DIARIZATION_URL_ENV} in forbidden_env so the live service is checked for it',
                    )
                )
    return errors


# The runtime resolves these flags with strip().casefold() against the truthy
# set {'1','true','yes','on'}; anything else — including '' — is silently False.
# Admission therefore only accepts that truthy set and its falsy counterparts,
# so an empty or misspelled literal cannot pass the contract while behaving
# like the omitted/False case the contract exists to reject.
_SUMMARY_FLAG_LITERALS = frozenset({'1', 'true', 'yes', 'on', '0', 'false', 'no', 'off'})

# Deploys pin exact booleans; the runtime summary kill switch defaults on.
_EXACT_BOOLEAN_FLAGS = frozenset({'CLIENT_SUMMARIES_AT_CAP_ENABLED'})
_EXACT_BOOLEAN_LITERALS = frozenset({'true', 'false'})


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


def validate_voice_transcription_storage(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Keep the voice upload route's staging bucket explicit in each environment."""
    expected = VOICE_STAGING_BUCKETS.get(env)
    if expected is None:
        return []
    config = _service_config(env_config, 'cloud_run', 'backend') or {}
    if _literal_env(config).get(VOICE_STAGING_BUCKET_ENV) == expected:
        return []
    return [
        ValidationError(
            f'{env}/cloud_run/backend',
            f'voice transcription requires literal BUCKET_TEMPORAL_SYNC_LOCAL={expected}',
        )
    ]


def validate_conversation_finalization_capabilities(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Validate the explicit finalization host roster and its memory-write fence."""

    errors: list[ValidationError] = []
    declared_by_host: dict[tuple[str, str], frozenset[str]] = {}
    finalization_gate_values: dict[str, dict[str, str]] = {flag: {} for flag in FINALIZATION_GATE_FLAGS}

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

        # Use the production parser; duplicating token policy here would let
        # admission drift from runtime.
        literal_env = _literal_env(service_config)
        resolved_mode = rollout_mode_env_value(literal_env)
        if resolved_mode not in {MemoryRolloutMode.write.value, MemoryRolloutMode.read.value}:
            raw_enabled = literal_env.get('MEMORY_ENABLED')
            errors.append(
                ValidationError(
                    scope,
                    'capability memory.canonical.mutate requires the runtime memory fence to permit writes; '
                    f'MEMORY_ENABLED={raw_enabled!r} resolves to {resolved_mode!r}',
                )
            )

        for flag in FINALIZATION_GATE_FLAGS:
            if flag not in literal_env:
                errors.append(
                    ValidationError(
                        scope,
                        f'finalization gate {flag} must be a literal on every conversation-finalization host',
                    )
                )
                continue
            # Compare raw literals, not normalized values: the pusher co-host
            # gate (verify_pusher_cohost_env_diff.py) enforces byte-identical
            # values for these same flags, so admission must not accept drift
            # (e.g. 'true' vs ' TRUE ') that the co-host gate would reject.
            finalization_gate_values[flag][scope] = literal_env[flag]
            if flag in _EXACT_BOOLEAN_FLAGS:
                if literal_env[flag] not in _EXACT_BOOLEAN_LITERALS:
                    errors.append(
                        ValidationError(
                            scope,
                            f"rollout flag {flag} must be exactly 'true' or 'false' "
                            f'(its reader accepts nothing else), got {literal_env[flag]!r}',
                        )
                    )
                continue
            if literal_env[flag].strip().casefold() not in _SUMMARY_FLAG_LITERALS:
                errors.append(
                    ValidationError(
                        scope,
                        f'finalization gate {flag} must be an explicit boolean literal '
                        f'(true/false), got {literal_env[flag]!r}',
                    )
                )

    for flag, host_values in finalization_gate_values.items():
        distinct = set(host_values.values())
        if len(distinct) > 1:
            rendered = ', '.join(f'{scope}={value!r}' for scope, value in sorted(host_values.items()))
            errors.append(
                ValidationError(
                    f'{env}/conversation-finalization',
                    f'finalization gate {flag} disagrees across finalization hosts: {rendered}',
                )
            )

    return errors


SPEAKER_EMBEDDING_ENV = 'HOSTED_SPEAKER_EMBEDDING_API_URL'
SPEAKER_EMBEDDING_HOSTS: tuple[tuple[str, str], ...] = (
    ('gke', 'backend-listen'),
    ('gke', 'pusher'),
    ('cloud_run', 'backend'),
    ('cloud_run', 'backend-sync'),
    ('cloud_run', 'backend-sync-backfill'),
    ('cloud_run', 'backend-integration'),
)
_CLUSTER_LOCAL_DNS = '.svc.cluster.local'
# Cloud Run cannot resolve cluster DNS. Prod routes through the internal-ALB
# shared gateway (gateway IP + /diarizer); the dev gateway VIP was deleted
# 2026-11-02, so dev uses the documented rollback Ingress host. Admission
# rejects any other literal, including a value that merely agrees across
# Cloud Run hosts.
_CLOUD_RUN_SPEAKER_EMBEDDING_URL = {
    'dev': 'http://diarizer.omiapi.com:80',
    'prod': 'http://172.16.160.20/diarizer',
}


def validate_speaker_embedding_hosts(env: str, env_config: ConfigDict) -> list[ValidationError]:
    """Require a reachable diarizer route on every speaker-ID host.

    Live capture (GKE listen/pusher) and offline sync (Cloud Run) share
    ``utils.stt.speaker_embedding``. Omitting the URL on one host disables
    voice matching there while the others keep working. Cloud Run cannot use
    in-cluster DNS, so each Cloud Run host must use that environment's
    approved internal-ALB route. GKE hosts share one route (ClusterIP service
    DNS in prod, the legacy diarizer Ingress host in dev after the shared
    internal gateway was removed).
    """
    errors: list[ValidationError] = []
    gke_values: dict[str, str] = {}
    cloud_run_values: dict[str, str] = {}
    for platform, service_name in SPEAKER_EMBEDDING_HOSTS:
        service_config = _service_config(env_config, platform, service_name)
        if service_config is None:
            continue
        scope = f'{env}/{platform}/{service_name}'
        literal_env = _literal_env(service_config)
        value = (literal_env.get(SPEAKER_EMBEDDING_ENV) or '').strip()
        has_parakeet = bool((literal_env.get('HOSTED_PARAKEET_API_URL') or '').strip())
        # Tiny fixture manifests that only name a host for an unrelated contract
        # must not be forced to declare speaker embedding. The real STT hosts
        # already carry HOSTED_PARAKEET_API_URL; that is the co-host signal.
        if not value and not has_parakeet:
            continue
        if not value:
            errors.append(
                ValidationError(
                    scope,
                    f'{SPEAKER_EMBEDDING_ENV} must be a non-empty literal on every speaker-ID host',
                )
            )
            continue
        if platform == 'cloud_run' and _CLUSTER_LOCAL_DNS in value:
            errors.append(
                ValidationError(
                    scope,
                    f'{SPEAKER_EMBEDDING_ENV} must be the reachable ILB hostname, not cluster-local DNS',
                )
            )
        approved = _CLOUD_RUN_SPEAKER_EMBEDDING_URL.get(env) if platform == 'cloud_run' else None
        if approved and value != approved:
            errors.append(
                ValidationError(
                    scope,
                    f'{SPEAKER_EMBEDDING_ENV} must be the approved internal-ALB route {approved!r}',
                )
            )
        (gke_values if platform == 'gke' else cloud_run_values)[scope] = value

    for topology_values in (gke_values, cloud_run_values):
        distinct = set(topology_values.values())
        if len(distinct) > 1:
            rendered = ', '.join(f'{scope}={value!r}' for scope, value in sorted(topology_values.items()))
            errors.append(
                ValidationError(
                    f'{env}/speaker-embedding',
                    f'{SPEAKER_EMBEDDING_ENV} disagrees across hosts: {rendered}',
                )
            )
    return errors


__all__ = [
    'BATCH_FINAL_PASS_FLAG',
    'BATCH_FINAL_PASS_HOSTS',
    'CANONICAL_MEMORY_MUTATION_CAPABILITY',
    'CONVERSATION_FINALIZATION_CAPABILITY',
    'FINALIZATION_GATE_FLAGS',
    'SPEAKER_EMBEDDING_ENV',
    'SPEAKER_EMBEDDING_HOSTS',
    'validate_conversation_finalization_capabilities',
    'validate_batch_final_pass_hosts',
    'validate_speaker_embedding_hosts',
]
