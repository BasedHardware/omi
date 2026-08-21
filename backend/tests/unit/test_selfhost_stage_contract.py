"""`OMI_ENV_STAGE=selfhost` must behave exactly like a real deployment, on every stage consumer.

Our postures used to say `offline`, a value that upstream defines as "fake providers"
(backend/AGENTS.md, backend/.env.offline.template) while a self-hosted stack runs REAL providers that
merely happen to be local. We got the behaviour we wanted by coincidence — `offline` simply is not in
the dev-ish sets those consumers check. `selfhost` says what we are (ADR-0058), and this test turns
the coincidence into a contract: every place that branches on the stage is pinned here, so a future
upstream change to any of those sets fails loudly instead of silently reclassifying our deployments.

Why each row matters:
  * the gateway interlock decides whether OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE is required at all;
  * desktop proactivity's dev branch falls back to api.openai.com — it must never be reachable here;
  * cloud_tasks REQUIRES Google Cloud Tasks at startup for stage `prod`, which would stop an on-prem
    backend from booting;
  * promotion_flex must fail closed to Standard rather than read a cross-stage control document;
  * parity telemetry is a dev-only emitter.
"""

from __future__ import annotations

import pytest

from utils.env_loader import EnvStage, stage_env_filename, stage_from_env

SELFHOST = 'selfhost'


def test_selfhost_is_a_valid_stage_and_has_its_own_env_filename():
    assert EnvStage.SELFHOST.value == SELFHOST
    assert stage_from_env({'OMI_ENV_STAGE': 'SELFHOST'}) == SELFHOST
    assert stage_env_filename(SELFHOST) == '.env.selfhost'


def test_the_gateway_interlock_treats_selfhost_as_a_real_runtime(monkeypatch):
    """Not dev/local -> the prod acknowledgement is required, exactly as for a cloud runtime."""
    from utils.llm import gateway_client

    monkeypatch.setenv('OMI_ENV_STAGE', SELFHOST)
    monkeypatch.delenv('ENVIRONMENT', raising=False)
    monkeypatch.delenv('APP_ENV', raising=False)
    assert gateway_client._is_local_or_dev_runtime() is False

    monkeypatch.setenv('OMI_LLM_GATEWAY_FEATURE_MODE', 'gateway')
    monkeypatch.delenv('OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE', raising=False)
    with pytest.raises(RuntimeError, match='ALLOW_PROD_FEATURE_MODE'):
        gateway_client.should_route_features_through_gateway()

    monkeypatch.setenv('OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE', 'true')
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://llm_gateway:9080')
    assert gateway_client.should_route_features_through_gateway() is True


def test_selfhost_never_reaches_the_dev_openai_fallback(monkeypatch):
    """routers/desktop_proactivity gates its api.openai.com fallback on dev|local."""
    from utils.env_loader import resolve_stage_from_env

    monkeypatch.setenv('OMI_ENV_STAGE', SELFHOST)
    assert resolve_stage_from_env() not in {EnvStage.DEV.value, EnvStage.LOCAL.value}


def test_selfhost_does_not_demand_google_cloud_tasks_at_startup(monkeypatch):
    """utils/cloud_tasks raises at import-time validation only for stage `prod`."""
    import utils.cloud_tasks as cloud_tasks

    monkeypatch.setenv('OMI_ENV_STAGE', SELFHOST)
    monkeypatch.delenv('ACCOUNT_DELETION_DISPATCH_MODE', raising=False)
    # Must return without raising: the prod-only requirement does not apply to us.
    cloud_tasks.validate_account_deletion_dispatch_configuration()


def test_promotion_flex_fails_closed_on_selfhost(monkeypatch):
    """Only dev|prod have a flex-control document; anything else must fall back to Standard."""
    from utils.memory import promotion_flex

    monkeypatch.setenv('OMI_ENV_STAGE', SELFHOST)
    assert promotion_flex.background_flex_control_path() is None


def test_parity_telemetry_stays_silent_on_selfhost(monkeypatch):
    """The dev-only emitter must produce nothing: it gates on stage == 'dev'."""
    from routers.listen import parity_telemetry

    emitted: list[object] = []
    monkeypatch.setattr(parity_telemetry, 'record_fallback', lambda *a, **k: emitted.append(a), raising=False)

    parity_telemetry.record_parity_capture_event(
        stage='decode', outcome='ok', reason_class='none', environ={'OMI_ENV_STAGE': SELFHOST}
    )

    assert emitted == []
