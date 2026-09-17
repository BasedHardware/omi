"""Independent default-off switches for the three PR #14165 basic-plan gates.

Import-light: readers and composed YAML only. Behavioral OFF/ON coverage for
each gate lives next to the existing #14165 tests (those files already pay for
the heavy router / coordinator imports in module-scoped fixtures).
"""

from __future__ import annotations

import functools
from pathlib import Path

import pytest
import yaml

from utils.free_tier_basic_gates import (
    BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED,
    BASIC_PLAN_GATE_PROACTIVITY_ENABLED,
    BASIC_PLAN_GATE_PROXY_EMBED_ENABLED,
    basic_plan_gate_eager_extraction_enabled,
    basic_plan_gate_proactivity_enabled,
    basic_plan_gate_proxy_embed_enabled,
)
from utils.free_tier_cohort import EMERGENCY_STOP_ENV_VAR

BACKEND = Path(__file__).resolve().parents[2]
_READERS = (
    (BASIC_PLAN_GATE_PROACTIVITY_ENABLED, basic_plan_gate_proactivity_enabled),
    (BASIC_PLAN_GATE_PROXY_EMBED_ENABLED, basic_plan_gate_proxy_embed_enabled),
    (BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED, basic_plan_gate_eager_extraction_enabled),
)


@functools.cache
def _composed() -> dict:
    return yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))


@pytest.fixture(autouse=True)
def _clear_gate_env(monkeypatch):
    for name, _reader in _READERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(EMERGENCY_STOP_ENV_VAR, raising=False)


# red-proof: treat ``'1'`` / ``'yes'`` / ``'on'`` as on
@pytest.mark.parametrize('name, reader', _READERS)
@pytest.mark.parametrize(
    'value, expected',
    [
        ('true', True),
        ('TRUE', True),
        ('True', True),
        ('false', False),
        ('1', False),
        ('yes', False),
        ('on', False),
        ('', False),
        (None, False),
    ],
)
def test_env_parse_accepts_only_true_case_insensitive(monkeypatch, name, reader, value, expected) -> None:
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)
    assert reader() is expected


@pytest.mark.parametrize('name, reader', _READERS)
def test_emergency_stop_revokes_a_lit_gate(monkeypatch, name, reader) -> None:
    monkeypatch.setenv(name, 'true')
    assert reader() is True
    monkeypatch.setenv(EMERGENCY_STOP_ENV_VAR, 'true')
    assert reader() is False


def test_the_three_switches_are_independent(monkeypatch) -> None:
    """Lighting one gate does not light the other two."""
    monkeypatch.setenv(BASIC_PLAN_GATE_PROACTIVITY_ENABLED, 'true')
    assert basic_plan_gate_proactivity_enabled() is True
    assert basic_plan_gate_proxy_embed_enabled() is False
    assert basic_plan_gate_eager_extraction_enabled() is False

    monkeypatch.delenv(BASIC_PLAN_GATE_PROACTIVITY_ENABLED)
    monkeypatch.setenv(BASIC_PLAN_GATE_PROXY_EMBED_ENABLED, 'true')
    assert basic_plan_gate_proactivity_enabled() is False
    assert basic_plan_gate_proxy_embed_enabled() is True
    assert basic_plan_gate_eager_extraction_enabled() is False

    monkeypatch.delenv(BASIC_PLAN_GATE_PROXY_EMBED_ENABLED)
    monkeypatch.setenv(BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED, 'true')
    assert basic_plan_gate_proactivity_enabled() is False
    assert basic_plan_gate_proxy_embed_enabled() is False
    assert basic_plan_gate_eager_extraction_enabled() is True


def test_readers_re_read_env_at_call_time(monkeypatch) -> None:
    assert basic_plan_gate_proactivity_enabled() is False
    monkeypatch.setenv(BASIC_PLAN_GATE_PROACTIVITY_ENABLED, 'true')
    assert basic_plan_gate_proactivity_enabled() is True
    monkeypatch.setenv(BASIC_PLAN_GATE_PROACTIVITY_ENABLED, 'false')
    assert basic_plan_gate_proactivity_enabled() is False


def _literal(env_map: dict, key: str) -> str:
    entry = env_map.get(key) or {}
    return str(entry.get('value') or '')


def test_dev_lights_each_gate_on_the_identities_that_run_its_code_path() -> None:
    dev = _composed()['environments']['dev']
    desktop = dev['desktop_backend']['env']
    backend = dev['cloud_run']['services']['backend']['env']
    assert _literal(desktop, BASIC_PLAN_GATE_PROACTIVITY_ENABLED) == 'true'
    assert _literal(desktop, BASIC_PLAN_GATE_PROXY_EMBED_ENABLED) == 'true'
    assert _literal(backend, BASIC_PLAN_GATE_PROXY_EMBED_ENABLED) == 'true'
    assert _literal(backend, BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED) == 'true'


def test_prod_states_all_three_gates_false_on_every_identity_that_declares_them() -> None:
    prod = _composed()['environments']['prod']
    desktop = prod['desktop_backend']['env']
    backend = prod['cloud_run']['services']['backend']['env']
    listen = prod['gke']['backend-listen']['env']
    pusher = prod['gke']['pusher']['env']
    sync = prod['cloud_run']['services']['backend-sync']['env']
    assert _literal(desktop, BASIC_PLAN_GATE_PROACTIVITY_ENABLED) == 'false'
    assert _literal(desktop, BASIC_PLAN_GATE_PROXY_EMBED_ENABLED) == 'false'
    assert _literal(backend, BASIC_PLAN_GATE_PROXY_EMBED_ENABLED) == 'false'
    for env_map in (listen, pusher, backend, sync):
        assert _literal(env_map, BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED) == 'false'


def test_proactivity_is_not_declared_on_process_conversation_hosts() -> None:
    """desktop_proactivity.router is mounted only by desktop_backend.py."""
    prod = _composed()['environments']['prod']
    for env_map in (
        prod['gke']['backend-listen']['env'],
        prod['gke']['pusher']['env'],
        prod['cloud_run']['services']['backend']['env'],
        prod['cloud_run']['services']['backend-sync']['env'],
    ):
        assert BASIC_PLAN_GATE_PROACTIVITY_ENABLED not in env_map


def test_each_gate_site_calls_only_its_own_reader() -> None:
    proactivity = (BACKEND / 'routers/desktop_proactivity.py').read_text(encoding='utf-8')
    proxy = (BACKEND / 'routers/desktop_proxy.py').read_text(encoding='utf-8')
    coordinator = (BACKEND / 'utils/conversations/process_conversation.py').read_text(encoding='utf-8')
    assert 'basic_plan_gate_proactivity_enabled()' in proactivity
    assert 'basic_plan_gate_proxy_embed_enabled' not in proactivity
    assert 'basic_plan_gate_eager_extraction_enabled' not in proactivity
    assert 'basic_plan_gate_proxy_embed_enabled()' in proxy
    assert 'basic_plan_gate_proactivity_enabled' not in proxy
    assert 'basic_plan_gate_eager_extraction_enabled' not in proxy
    assert 'basic_plan_gate_eager_extraction_enabled()' in coordinator
    assert 'basic_plan_gate_proactivity_enabled' not in coordinator
    assert 'basic_plan_gate_proxy_embed_enabled' not in coordinator
