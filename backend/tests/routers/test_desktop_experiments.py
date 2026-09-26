"""EXP-002 desktop enrollment endpoint: gates, fail-closed, and plane choice.

The contract under test (see
``backend/docs/experiments/EXP-002-desktop-identity-memory-v1.md``):

- Stable and non-beta bundles never enroll (channel gate) and never receive
  arm chrome.
- Binaries below the version floor never enroll.
- Kill switch off → no write, control chrome, existing assignment preserved.
- Persist or plane failure → control chrome, no variant delivered.
- Successful enrollment persists the arm name and enables chrome, and is
  idempotent across calls.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from routers import desktop_experiments as router
from tests.unit.fixtures.generic_firestore_fake import FakeFirestore
from utils.jit_rollout import JITDecisionReason, JITErrorClass, JITFlagEvaluation, TriState


def _request(
    *,
    experiment_id: str = router.EXP_002_EXPERIMENT_ID,
    channel: str = 'beta',
    bundle_id: str = 'com.omi.computer-macos.beta',
    app_version: str = '0.12.273',
) -> router.DesktopExperimentEnrollRequest:
    return router.DesktopExperimentEnrollRequest(
        experiment_id=experiment_id,
        channel=channel,
        bundle_id=bundle_id,
        app_version=app_version,
    )


class _FakeFlagProvider:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    async def __call__(self, uid: str) -> JITFlagEvaluation:
        state = TriState.ENABLED if self.enabled else TriState.DISABLED
        return JITFlagEvaluation(state, TriState.DISABLED, JITDecisionReason.EVALUATED, JITErrorClass.NONE)


@pytest.fixture
def direct_run_blocking(monkeypatch):
    async def _run_blocking(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(router, 'run_blocking', _run_blocking)


@pytest.fixture
def firestore(monkeypatch, direct_run_blocking):
    db = FakeFirestore()
    monkeypatch.setattr(router, '_assignments_client', lambda: db)
    return db


@pytest.fixture(autouse=True)
def _telemetry(monkeypatch):
    from utils.product_telemetry import set_product_telemetry_client_for_tests

    class _FakePosthog:
        def __init__(self):
            self.events: list[dict[str, Any]] = []

        def capture(self, **event):
            self.events.append(event)

    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'fake-key')
    fake = _FakePosthog()
    set_product_telemetry_client_for_tests(fake)
    yield fake.events
    set_product_telemetry_client_for_tests(None)


def _flag(monkeypatch, enabled: bool):
    monkeypatch.setattr(router, '_flag_provider', _FakeFlagProvider(enabled))


async def test_unknown_experiment_is_404():
    with pytest.raises(HTTPException) as exc:
        await router.enroll_desktop_experiment(_request(experiment_id='EXP-999-nope'), uid='uid1')
    assert exc.value.status_code == 404


async def test_stable_channel_is_refused_without_writing(firestore, monkeypatch):
    _flag(monkeypatch, True)
    response = await router.enroll_desktop_experiment(
        _request(channel='stable', bundle_id='com.omi.computer-macos'), uid='uid1'
    )
    assert response.enrolled is False
    assert response.chrome_enabled is False
    assert response.reason == 'channel_not_allowed'
    assert response.variant is None


async def test_non_beta_bundle_is_refused_without_writing(firestore, monkeypatch):
    _flag(monkeypatch, True)
    response = await router.enroll_desktop_experiment(_request(bundle_id='com.omi.omi-dev-dogfood'), uid='uid1')
    assert response.reason == 'channel_not_allowed'
    assert response.enrolled is False


async def test_below_minimum_version_is_refused(firestore, monkeypatch):
    _flag(monkeypatch, True)
    response = await router.enroll_desktop_experiment(_request(app_version='0.12.200'), uid='uid1')
    assert response.reason == 'app_version_below_minimum'
    assert response.enrolled is False
    assert response.chrome_enabled is False


async def test_kill_switch_off_leaves_assignments_and_paints_control(firestore, monkeypatch):
    _flag(monkeypatch, False)
    response = await router.enroll_desktop_experiment(_request(), uid='uid1')
    assert response.enrolled is False
    assert response.chrome_enabled is False
    assert response.reason == 'kill_switch_off'
    assert response.variant is None


async def test_kill_switch_off_returns_existing_assignment_without_rewriting(firestore, monkeypatch, _telemetry):
    _flag(monkeypatch, True)
    first = await router.enroll_desktop_experiment(_request(), uid='uid1')
    assert first.enrolled and first.chrome_enabled
    written_before = len(_telemetry)

    _flag(monkeypatch, False)
    second = await router.enroll_desktop_experiment(_request(), uid='uid1')
    assert second.enrolled is True
    assert second.variant == first.variant
    assert second.chrome_enabled is False
    assert second.reason == 'kill_switch_off'
    assert len(_telemetry) == written_before


async def test_enrollment_persists_arm_name_and_enables_chrome(firestore, monkeypatch, _telemetry):
    _flag(monkeypatch, True)
    response = await router.enroll_desktop_experiment(_request(), uid='uid1')
    assert response.enrolled is True
    assert response.chrome_enabled is True
    assert response.variant in {'control', 'memory_v1'}
    assert response.newly_enrolled is True
    assert any(e['event'] == 'Experiment Enrolled' for e in _telemetry)
    enrolled = [e for e in _telemetry if e['event'] == 'Experiment Enrolled']
    assert enrolled[0]['properties']['variant'] == response.variant
    assert enrolled[0]['properties']['experiment_id'] == router.EXP_002_EXPERIMENT_ID


async def test_reenroll_is_idempotent_and_keeps_variant(firestore, monkeypatch, _telemetry):
    _flag(monkeypatch, True)
    first = await router.enroll_desktop_experiment(_request(), uid='uid1')
    count_after_first = len(_telemetry)
    second = await router.enroll_desktop_experiment(_request(), uid='uid1')
    assert second.variant == first.variant
    assert second.newly_enrolled is False
    assert len(_telemetry) == count_after_first


async def test_persist_failure_fails_closed_to_control(monkeypatch, direct_run_blocking):
    class _RaisingFirestore(FakeFirestore):
        def collection(self, path):
            raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(router, '_assignments_client', lambda: _RaisingFirestore())
    _flag(monkeypatch, True)
    response = await router.enroll_desktop_experiment(_request(), uid='uid1')
    assert response.enrolled is False
    assert response.chrome_enabled is False
    assert response.variant is None
    assert response.reason == 'persist_failed'


async def test_unavailable_plane_skips_enrollment(monkeypatch, direct_run_blocking):
    def _raise():
        raise RuntimeError('OMI_FIRESTORE_DATA_PLANE_PROJECT is required on desktop-backend')

    monkeypatch.setattr(router, '_assignments_client', _raise)
    _flag(monkeypatch, True)
    response = await router.enroll_desktop_experiment(_request(), uid='uid1')
    assert response.enrolled is False
    assert response.chrome_enabled is False
    assert response.reason == 'assignments_plane_unavailable'


async def test_both_arms_enroll_through_the_same_endpoint(firestore, monkeypatch, _telemetry):
    """The endpoint must produce both arms over enough uids — the holdout has
    to appear in the roster for the experiment to be analyzable at all."""
    _flag(monkeypatch, True)
    variants = set()
    for i in range(40):
        response = await router.enroll_desktop_experiment(_request(), uid=f'both-arms-{i}')
        assert response.enrolled
        variants.add(response.variant)
    assert variants == {'control', 'memory_v1'}
