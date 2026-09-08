"""Behavioral tests for Parakeet-owned live-stream admission."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

PARAKEET_ADMISSION = Path(__file__).resolve().parents[2] / 'parakeet' / 'admission.py'


@pytest.fixture
def admission():
    return SimpleNamespace(**runpy.run_path(str(PARAKEET_ADMISSION)))


def test_one_parakeet_owner_caps_requests_from_all_27_listener_clients(admission):
    controller = admission.StreamAdmissionController(capacity=25, allocation_percent=100)

    with ThreadPoolExecutor(max_workers=27) as pool:
        results = list(pool.map(lambda _index: controller.try_acquire(), range(27)))

    leases = [result.lease for result in results if result.lease is not None]
    assert len(leases) == 25
    assert sum(result.reason == 'capacity_full' for result in results) == 2
    assert controller.active == 25

    for lease in leases:
        lease.release()
    assert controller.active == 0


def test_admission_lease_release_is_idempotent(admission):
    controller = admission.StreamAdmissionController(capacity=1, allocation_percent=100)
    lease = controller.try_acquire().lease
    assert lease is not None

    lease.release()
    lease.release()

    assert controller.active == 0
    assert controller.try_acquire().lease is not None


def test_allocation_zero_rejects_before_consuming_capacity(admission):
    controller = admission.StreamAdmissionController(capacity=25, allocation_percent=0)

    result = controller.try_acquire()

    assert result.lease is None
    assert result.reason == 'allocation_rejected'
    assert controller.active == 0


def test_partial_allocation_is_deterministic_at_the_sampling_seam(admission):
    rejected = admission.StreamAdmissionController(
        capacity=25,
        allocation_percent=10,
        sample=lambda: 0.10,
    )
    admitted = admission.StreamAdmissionController(
        capacity=25,
        allocation_percent=10,
        sample=lambda: 0.099,
    )

    assert rejected.try_acquire().reason == 'allocation_rejected'
    assert admitted.try_acquire().lease is not None


@pytest.mark.parametrize(
    ('env', 'message'),
    [
        ({}, 'PARAKEET_STREAM_CAPACITY'),
        (
            {'PARAKEET_STREAM_CAPACITY': '25'},
            'PARAKEET_STREAM_ALLOCATION_PERCENT',
        ),
        (
            {
                'PARAKEET_STREAM_CAPACITY': '0',
                'PARAKEET_STREAM_ALLOCATION_PERCENT': '100',
            },
            'PARAKEET_STREAM_CAPACITY',
        ),
        (
            {
                'PARAKEET_STREAM_CAPACITY': '25',
                'PARAKEET_STREAM_ALLOCATION_PERCENT': '101',
            },
            'PARAKEET_STREAM_ALLOCATION_PERCENT',
        ),
    ],
)
def test_deploy_owned_settings_are_required_and_validated(admission, env, message):
    with pytest.raises(ValueError, match=message):
        admission.StreamAdmissionController.from_env(env)
