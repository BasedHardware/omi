"""Hermetic paid admission, debounce wiring, and mentor log privacy checks."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from config.plan_catalog import PAID_PLAN_TYPES, PlanType
from tests.unit.test_realtime_integrations_usage_tracking import integration_harness  # noqa: F401
from utils import mentor_admission as admission_module
from database.cache_manager import InMemoryCacheManager

SECRET = 'PRIVATE_TRANSCRIPT_NEVER_STORED_5921'


@pytest.fixture
def admission(monkeypatch):
    # Dependency initialization belongs to setup, not the behavioral call-phase budget.
    from utils import managed_compute  # noqa: F401
    from database import _client as client_db
    from database import cache as cache_db
    from database import users as users_db

    lookup = MagicMock(return_value=None)
    cache = InMemoryCacheManager()
    monkeypatch.setattr(cache_db, 'get_memory_cache', lambda: cache)
    monkeypatch.setattr(users_db, 'get_user_valid_subscription', lookup)
    monkeypatch.setattr(client_db, 'get_customer_firestore_client', lambda: 'fake-client')
    fallback = MagicMock()
    monkeypatch.setattr(admission_module, 'record_fallback', fallback)
    return lookup, fallback


@pytest.mark.parametrize('plan', [None, PlanType.basic, *PAID_PLAN_TYPES])
def test_paid_plan_admission_uses_canonical_resolution(admission, plan, caplog):
    lookup, fallback = admission
    lookup.return_value = SimpleNamespace(plan=plan) if plan is not None else None
    with caplog.at_level('INFO'):
        assert admission_module.mentor_plan_allows_evaluation('synthetic') is (plan in PAID_PLAN_TYPES)
    lookup.assert_called_once_with('synthetic', firestore_client='fake-client', provision=False)
    fallback.assert_not_called()
    if plan not in PAID_PLAN_TYPES:
        assert 'mentor_plan_admission outcome=skipped reason=basic_not_entitled' in caplog.text


@pytest.mark.parametrize('failure', ['lookup', 'unknown_plan'])
def test_lookup_failure_is_counted_fail_open(admission, failure, caplog):
    lookup, fallback = admission
    if failure == 'lookup':
        lookup.side_effect = RuntimeError(SECRET)
    else:
        lookup.return_value = SimpleNamespace(plan='future_plan')
    assert admission_module.mentor_plan_allows_evaluation('synthetic') is True
    fallback.assert_called_once()
    assert 'outcome=fail_open' in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize('plan', [PlanType.basic, PlanType.unlimited])
def test_entitlement_is_cached_per_uid_for_300_seconds(admission, plan):
    lookup, _ = admission
    lookup.return_value = SimpleNamespace(plan=plan)
    allowed = plan in PAID_PLAN_TYPES
    assert admission_module.mentor_plan_allows_evaluation('synthetic') is allowed
    assert admission_module.mentor_plan_allows_evaluation('synthetic') is allowed
    assert lookup.call_count == 1
    assert admission_module.mentor_plan_allows_evaluation('other-synthetic') is allowed
    assert lookup.call_count == 2
    from database import cache as cache_db

    cache = cache_db.get_memory_cache()
    entry = cache.cache['mentor_entitlement:synthetic']
    assert entry.ttl == 300
    entry.timestamp -= 301
    lookup.return_value = SimpleNamespace(plan=PlanType.basic if allowed else PlanType.unlimited)
    assert admission_module.mentor_plan_allows_evaluation('synthetic') is not allowed
    assert lookup.call_count == 3


@pytest.mark.parametrize('failure', ['lookup', 'unknown_plan'])
def test_unresolved_entitlement_is_not_cached(admission, failure):
    lookup, fallback = admission
    if failure == 'lookup':
        lookup.side_effect = [RuntimeError(SECRET), SimpleNamespace(plan=PlanType.basic)]
    else:
        lookup.side_effect = [SimpleNamespace(plan='future_plan'), SimpleNamespace(plan=PlanType.basic)]
    assert admission_module.mentor_plan_allows_evaluation('synthetic') is True
    assert admission_module.mentor_plan_allows_evaluation('synthetic') is False
    assert lookup.call_count == 2
    fallback.assert_called_once()


@pytest.fixture
def pipeline(integration_harness, monkeypatch):  # noqa: F811
    app = integration_harness.app
    monkeypatch.setenv('MENTOR_GATE_DEBOUNCE_ENABLED', 'false')
    app.get_mentor_notification_frequency.return_value = 3
    return app


@pytest.mark.parametrize('debounce', [True, False])
def test_free_skip_precedes_all_model_and_context_calls(pipeline, monkeypatch, debounce):
    """A free user consumes neither a gate evaluation nor any context/model work."""
    app = pipeline
    monkeypatch.setenv('MENTOR_GATE_DEBOUNCE_ENABLED', str(debounce))
    for name, result in [
        ('read', None),
        ('read_authoritative', None),
        ('claim', True),
        ('record', None),
        ('release', None),
    ]:
        monkeypatch.setattr(app.mentor_gate_state, name, MagicMock(return_value=result))
    app.mentor_plan_allows_evaluation.return_value = False
    assert app.admit_mentor_evaluation('synthetic', [{'text': 'word ' * 120, 'is_user': True}]) is None
    for call in (
        app.get_prompt_memories,
        app.generate_embedding,
        app.query_vectors_by_metadata,
    ):
        call.assert_not_called()
    app.mentor_plan_allows_evaluation.assert_called_once_with('synthetic')
    app.mentor_gate_state.record.assert_not_called()
    if debounce:
        app.mentor_gate_state.release.assert_called_once_with('synthetic')


def test_runtime_env_and_charts_enable_debounce_on_all_mentor_hosts():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    manifest = yaml.load((root / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    for stage in ('prod', 'dev'):
        env = manifest['environments'][stage]
        hosts = [env['gke'][name]['env'] for name in ('pusher', 'backend-listen')]
        hosts.append(env['cloud_run']['services']['backend']['env'])
        for host in hosts:
            assert host['MENTOR_GATE_DEBOUNCE_ENABLED']['value'] == 'true'
            assert not {'MENTOR_GATE_MIN_NEW_WORDS', 'MENTOR_GATE_MIN_SECONDS', 'MENTOR_GATE_DAILY_CAP'} & host.keys()
        for name, suffix in [('pusher', 'pusher'), ('backend-listen', 'backend_listen')]:
            chart = yaml.load(
                (root / f'charts/{name}/{stage}_omi_{suffix}_values.yaml').read_text(), Loader=yaml.CSafeLoader
            )
            values = {entry['name']: entry.get('value') for entry in chart['env']}
            for flag in ('MENTOR_GATE_DEBOUNCE_ENABLED',):
                assert values[flag] == env['gke'][name]['env'][flag]['value']
