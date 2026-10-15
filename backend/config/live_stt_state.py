"""Environment- and identity-scoped live STT routing state keys.

Key namespaces carry the deployment stage and a domain-separated fingerprint of
the actual serving endpoint plus credential identity, so dev evidence can never
mutate prod routing health and a changed endpoint/account starts with fresh
state. Raw URLs and credentials never enter Redis paths, logs, or metrics.
"""

from __future__ import annotations

import hashlib
import os

from config.stt_provider_policy import MODULATE_SUPPORTED_LANGUAGES, PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL

COST_PREFIX = 'omi:live-stt:cost-v8'
FLEET_PREFIX = 'omi:live-stt:fleet-v2'
LOCAL_CIRCUIT_PREFIX = 'omi:live-stt:local-selection'
FAMILIES = ('deepgram', 'modulate', 'parakeet', 'soniox')
ROUTED_LANGUAGES = frozenset(
    MODULATE_SUPPORTED_LANGUAGES | frozenset().union(*PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL.values()) | {'other'}
)

_CREDENTIAL_ENV = {
    'modulate': 'MODULATE_API_KEY',
    'soniox': 'SONIOX_API_KEY',
    'deepgram': 'DEEPGRAM_API_KEY',
}
_ENDPOINT_ENV = {
    'soniox': 'SONIOX_WS_URL',
}
_DEFAULT_ENDPOINT = {
    'modulate': 'wss://modulate-developer-apis.com/api/velma-2-stt-streaming',
    'soniox': 'wss://stt-rt.soniox.com/transcribe-websocket',
}
_STAGES = frozenset({'prod', 'dev', 'local', 'offline'})


def stage() -> str:
    raw = os.getenv('OMI_ENV_STAGE', '').strip().lower()
    if raw in _STAGES:
        return raw
    if os.getenv('PROVIDER_MODE', '').strip().lower() == 'offline':
        return 'offline'
    return 'unknown'


def _digest(*parts: str) -> str:
    return hashlib.sha256('\x1f'.join(parts).encode()).hexdigest()[:32]


def family_credential(family: str) -> str:
    env = _CREDENTIAL_ENV.get(family)
    return os.getenv(env, '') if env else ''


def family_endpoint(family: str) -> str:
    if family == 'parakeet':
        return os.getenv('HOSTED_PARAKEET_API_URL', '').rstrip('/')
    if family == 'deepgram':
        enabled = os.getenv('DEEPGRAM_SELF_HOSTED_ENABLED', '').strip().lower() == 'true'
        return os.getenv('DEEPGRAM_SELF_HOSTED_URL', '') if enabled else ''
    env = _ENDPOINT_ENV.get(family)
    if env and os.getenv(env):
        return os.getenv(env, '')
    return _DEFAULT_ENDPOINT.get(family, '')


def target_endpoint(target) -> str:
    endpoint = getattr(target, 'endpoint', None)
    if endpoint:
        return endpoint
    return family_endpoint(target.family)


def cost_key(target, language: str) -> str:
    fingerprint = _digest('live-stt-cost-v8', target.family, target_endpoint(target), family_credential(target.family))
    return f'{COST_PREFIX}:{stage()}:{fingerprint}:{target.id}:{language}'


def cost_lease_key(target, language: str) -> str:
    fingerprint = _digest('live-stt-cost-v8', target.family, target_endpoint(target), family_credential(target.family))
    return f'{COST_PREFIX}:{stage()}:{fingerprint}:lease:{target.id}:{language}'


def fleet_prefix(family: str, *, account: bool = False, endpoint: str | None = None) -> str:
    if account:
        fingerprint = _digest('live-stt-fleet-v2-account', family, family_credential(family))
    else:
        fingerprint = _digest(
            'live-stt-fleet-v2-endpoint',
            family,
            family_endpoint(family) if endpoint is None else endpoint,
            family_credential(family),
        )
    return f'{FLEET_PREFIX}:{stage()}:{fingerprint}'


def circuit_prefix(family: str, *, endpoint: str | None = None) -> str:
    """Process-local selection-breaker identity (stage + family + endpoint; credential excluded)."""
    fingerprint = _digest(
        'live-stt-local-selection',
        family,
        family_endpoint(family) if endpoint is None else endpoint,
    )
    return f'{LOCAL_CIRCUIT_PREFIX}:{stage()}:{fingerprint}'


def fleet_state_key(family: str, *, account: bool = False, endpoint: str | None = None) -> str:
    return f'{fleet_prefix(family, account=account, endpoint=endpoint)}:state:{family}'


def fleet_probe_key(family: str, *, account: bool = False, endpoint: str | None = None) -> str:
    return f'{fleet_prefix(family, account=account, endpoint=endpoint)}:probe:{family}'


def fleet_score_keys(family: str, language: str, bucket: int, *, endpoint: str | None = None) -> tuple[str, str]:
    stem = f'{fleet_prefix(family, endpoint=endpoint)}:score:{family}:{language}:{bucket}'
    return stem + ':text', stem + ':no_text'


def state_identity(targets=()) -> str:
    """Fingerprint of the endpoint/credential inputs that own shared routing state."""
    parts = [stage()]
    for family in FAMILIES:
        parts.append(_digest('credential', family, family_credential(family)))
        parts.append(_digest('endpoint', family, family_endpoint(family)))
    for target in sorted(targets, key=lambda entry: entry.id):
        parts.append(_digest('target', target.id, target.family, target_endpoint(target)))
    return _digest('live-stt-state', *parts)
