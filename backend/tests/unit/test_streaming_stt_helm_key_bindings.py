"""Helm STT_SERVICE_MODELS must bind every key streaming startup fail-closes on.

``validate_streaming_stt_env`` is the listen/pusher startup check. It does not
export a provider→key table, so this guard probes that function with each listed
model and an empty env, then requires the named key to be bound in the same
values file (literal or secretKeyRef). A hardcoded second mapping would drift
the next time the validator grows another listed-provider check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from utils.stt.streaming import validate_streaming_stt_env

ROOT = Path(__file__).resolve().parents[3]
VALUES_FILES = (
    ROOT / 'backend/charts/backend-listen/dev_omi_backend_listen_values.yaml',
    ROOT / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml',
    ROOT / 'backend/charts/pusher/dev_omi_pusher_values.yaml',
    ROOT / 'backend/charts/pusher/prod_omi_pusher_values.yaml',
)

# Production error: "STT_SERVICE_MODELS lists soniox but SONIOX_API_KEY is empty".
_MISSING_KEY = re.compile(r'\bbut ([A-Z][A-Z0-9_]+) is empty\b')


def _listed_models(values: dict) -> tuple[str, ...] | None:
    for entry in values.get('env') or []:
        if not isinstance(entry, dict) or entry.get('name') != 'STT_SERVICE_MODELS':
            continue
        raw = entry.get('value')
        if not isinstance(raw, str):
            return ()
        return tuple(part.strip() for part in raw.split(',') if part.strip())
    return None


def _bound_env_names(values: dict) -> set[str]:
    bound: set[str] = set()
    for entry in values.get('env') or []:
        if not isinstance(entry, dict) or not isinstance(entry.get('name'), str):
            continue
        name = entry['name']
        value = entry.get('value')
        if isinstance(value, str) and value.strip():
            bound.add(name)
            continue
        value_from = entry.get('valueFrom')
        if not isinstance(value_from, dict):
            continue
        for field in ('secretKeyRef', 'configMapKeyRef'):
            ref = value_from.get(field)
            # The referenced key must carry the env var's own name. A provider
            # key wired to some other existing key (SONIOX_API_KEY <- MODULATE_API_KEY)
            # is non-empty, so startup admission passes and the provider then
            # fails authentication on its first failover.
            if isinstance(ref, dict) and ref.get('name') and ref.get('key') == name:
                bound.add(name)
                break
    return bound


def startup_key_for_listed_model(model: str) -> str | None:
    """Return the env var the real startup validator requires for ``model``, if any."""
    try:
        validate_streaming_stt_env({'STT_SERVICE_MODELS': model})
    except RuntimeError as exc:
        match = _MISSING_KEY.search(str(exc))
        if match is None:
            raise AssertionError(
                f'validate_streaming_stt_env rejected {model!r} without naming a missing key: {exc}'
            ) from exc
        return match.group(1)
    return None


def unbound_startup_keys(values: dict) -> list[tuple[str, str]]:
    models = _listed_models(values)
    if not models:
        return []
    bound = _bound_env_names(values)
    missing: list[tuple[str, str]] = []
    for model in models:
        key = startup_key_for_listed_model(model)
        if key is not None and key not in bound:
            missing.append((model, key))
    return missing


def test_validator_probe_derives_soniox_key_and_ignores_keyless_providers() -> None:
    assert startup_key_for_listed_model('soniox') == 'SONIOX_API_KEY'
    assert startup_key_for_listed_model('modulate-velma-2') is None
    assert startup_key_for_listed_model('dg-nova-3') is None
    assert startup_key_for_listed_model('parakeet') is None


def test_unbound_soniox_listing_is_the_origin_main_failure() -> None:
    """This is the chart shape origin/main shipped: listed soniox, no key binding."""
    values = {
        'env': [
            {'name': 'STT_SERVICE_MODELS', 'value': 'modulate-velma-2,soniox,dg-nova-3,parakeet'},
            {
                'name': 'MODULATE_API_KEY',
                'valueFrom': {'secretKeyRef': {'name': 'dev-omi-backend-secrets', 'key': 'MODULATE_API_KEY'}},
            },
        ]
    }
    assert unbound_startup_keys(values) == [('soniox', 'SONIOX_API_KEY')]


@pytest.mark.parametrize('values_path', VALUES_FILES, ids=lambda path: path.name)
def test_listen_and_pusher_stt_models_bind_startup_keys(values_path: Path) -> None:
    loaded = yaml.safe_load(values_path.read_text(encoding='utf-8'))
    assert isinstance(loaded, dict), values_path
    models = _listed_models(loaded)
    assert models, f'{values_path.name} must declare STT_SERVICE_MODELS for this guard to apply'
    missing = unbound_startup_keys(loaded)
    detail = ', '.join(f'{model} requires {key}' for model, key in missing)
    relative = values_path.relative_to(ROOT)
    assert missing == [], f'{relative} lists streaming providers whose startup keys are unbound: {detail}'


def test_a_provider_key_wired_to_a_different_secret_key_is_not_bound():
    values = {
        'env': [
            {
                'name': 'SONIOX_API_KEY',
                'valueFrom': {'secretKeyRef': {'name': 'dev-omi-backend-secrets', 'key': 'MODULATE_API_KEY'}},
            }
        ]
    }

    assert 'SONIOX_API_KEY' not in _bound_env_names(values)
