# LIFECYCLE: permanent
"""PL-426: abandoned local silence is neither vendor spend nor a health vote.

Run real admission, provider intent/settlement and health logic on Firestore,
Postgres and the simulator. Only audio inspection, vendor IO and artifact IO
are synthetic. Full qualification requires OMI_REQUIRE_STORE_BACKENDS=all.
"""

from __future__ import annotations

from copy import deepcopy
from functools import partial
import os
from pathlib import Path
import sys
from unittest.mock import Mock

os.environ.setdefault('OMI_ENV_STAGE', 'offline')
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

pytest_plugins = ['tests.conftest']

import pytest

from config.policy import BatchUnitPolicy
from database.batch_pipeline_intake import admit
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline import provider_stt, route_selection, vendor_health, vendor_route_metrics
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.provider_stt_admission import SttRoute, enqueue_in_transaction
from utils.batch_pipeline.vendor_route_contracts import VendorAttempt

pytestmark = pytest.mark.integration
T0 = 1_800_000_000.0
ROUTE = SttRoute('provider', 'unsupported_language', 'modulate', 'ja')
OVERFLOW = SttRoute('provider', 'none', 'modulate', 'en')


class Artifacts:
    """Token-addressed result objects with a controllable lost upload reply."""

    def __init__(self):
        self.objects = {}
        self.fail = True
        self.write_before_failure = False
        self.writes = []

    def fetch_audio(self, item):
        return b'synthetic-pcm'

    def persist_recovery_result(self, item, payload, token):
        uri = f'gs://synthetic/{item.segment_id}/{token}'
        self.writes.append((item.segment_id, token))
        if not self.fail or self.write_before_failure:
            self.objects[uri] = deepcopy(payload)
        if self.fail:
            raise TimeoutError('synthetic artifact reply lost')
        return uri

    def find_recovery_result(self, item, token):
        uri = f'gs://synthetic/{item.segment_id}/{token}'
        return uri if uri in self.objects else None

    def load_result(self, item, uri):
        return deepcopy(self.objects[uri])


def read(h, sid):
    return h.store.run(lambda tx: tx.get('jobs', sid))


def seed(h, count=1, route=ROUTE):
    owner = h.seed_user('silent')
    units = [
        WorkItem(f'silent-{i}', owner, T0 + i, f'gs://synthetic/source-{i}#7', 5, Priority.FRESH, privacy_generation=0)
        for i in range(count)
    ]
    binding = ProjectionBinding(owner, 'upload', 'content', tuple(unit.segment_id for unit in units), language='ja')
    assert (
        admit(
            h.store,
            units,
            binding,
            T0,
            namespace=h.namespace,
            policy=BatchUnitPolicy(batch_enabled=True, batch_percent=100),
            enqueue=partial(enqueue_in_transaction, route=route),
        )['outcome']
        == 'batch'
    )
    return units


def health(clock):
    service = vendor_health.VendorHealthService(
        shared=vendor_health.MemoryStore(),
        local=vendor_health.MemoryStore(),
        routes=lambda: route_selection.current_table()[0].routes,
        enabled=lambda: True,
        clock=clock,
        rng=lambda: 0.5,
        background=False,
    )
    service.record_attempt = Mock(wraps=service.record_attempt)
    return service


def stage(h, artifacts, vendor, service, now):
    return provider_stt.ProviderSttStage(
        h.store,
        artifacts,
        stt=vendor,
        allowed=lambda *_: True,
        inspect=lambda *_: (b'\0\0', 5.0, []),
        clock=lambda: now,
        health=service,
        armed=lambda: True,
    )


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('saved', [False, True])
@pytest.mark.parametrize('route', [ROUTE, OVERFLOW], ids=['unsupported', 'overflow'])
def test_pl426_restart_settles_the_same_silence_without_spend_or_health_vote(
    store_backend, monkeypatch, legacy, saved, route
):
    h = store_backend
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    (unit,) = seed(h, route=route)
    artifacts = Artifacts()
    artifacts.write_before_failure = saved
    vendor = Mock(side_effect=AssertionError('local silence must not call a vendor'))
    service = health(lambda: T0)
    assert stage(h, artifacts, vendor, service, T0).run(unit.segment_id).outcome == 'retry'
    running = read(h, unit.segment_id)
    assert running['state'] == provider_stt.RUNNING
    assert running['provider_intent']['vendor_skipped'] is True
    assert running['provider_intent']['measured_vad_speech_seconds'] == 0
    if legacy:

        def old_worker(tx):
            row = tx.get('jobs', unit.segment_id)
            row['provider_intent'].pop('vendor_skipped')
            tx.put('jobs', unit.segment_id, row)

        h.store.run(old_worker)
    late = T0 + provider_stt.ABANDON_SECONDS + 1
    overflow_audio = vendor_route_metrics.OVERFLOW_AUDIO.labels(route='modulate')
    before_audio = overflow_audio._value.get()
    if not saved:
        before_retry = read(h, unit.segment_id)
        assert stage(h, artifacts, vendor, service, late).run(unit.segment_id).outcome == 'retry'
        assert read(h, unit.segment_id) == before_retry
    artifacts.fail = False
    # A new stage owns no in-memory result or inspection from the failed delivery.
    replay = stage(h, artifacts, vendor, service, late)
    assert replay.run(unit.segment_id).reason == 'processed'
    settled = read(h, unit.segment_id)
    assert settled['state'] == 'result_ready' and settled['result']['outcome'] == 'silence'
    assert settled['provider_intent']['token'] == running['provider_intent']['token']
    assert settled['audio_uri'] == running['audio_uri']
    assert settled['projection_binding'] == running['projection_binding']
    assert settled['policy'] == running['policy']
    attempts = settled['provider_attempts']
    assert len(attempts) == 1 and attempts[0]['outcome'] == 'silence'
    assert attempts[0]['audio_seconds'] == 0 and not VendorAttempt.from_dict(attempts[0]).billable
    writes = list(artifacts.writes)
    replay.run(unit.segment_id)
    assert read(h, unit.segment_id) == settled
    assert artifacts.writes == writes
    assert {token for _, token in artifacts.writes} == {running['provider_intent']['token']}
    vendor.assert_not_called()
    service.record_attempt.assert_not_called()
    assert overflow_audio._value.get() == before_audio


def test_pl426_silent_crash_burst_cannot_poison_vendor_health_or_audio_counters(store_backend, monkeypatch):
    h = store_backend
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    units = seed(h, 6)
    now = [T0]
    service = health(lambda: now[0])
    vendor = Mock(side_effect=AssertionError('local silence must not call a vendor'))
    audio = vendor_route_metrics.ATTEMPT_AUDIO.labels(provider='modulate', outcome='abandoned')
    before = audio._value.get()
    for i, unit in enumerate(units):
        artifacts = Artifacts()
        assert stage(h, artifacts, vendor, service, T0).run(unit.segment_id).outcome == 'retry'
        artifacts.fail = False
        now[0] = T0 + provider_stt.ABANDON_SECONDS + 1 + 30 * i
        assert stage(h, artifacts, vendor, service, now[0]).run(unit.segment_id).reason == 'processed'
        assert read(h, unit.segment_id)['result']['outcome'] == 'silence'
    assert audio._value.get() == before
    assert service.allows('modulate')[0]
    service.record_attempt.assert_not_called()
    vendor.assert_not_called()


def test_pl426_positive_speech_abandonment_keeps_its_paid_attempt_and_health_failure(store_backend, monkeypatch):
    """The silence exception cannot absorb an actual vendor call with positive speech."""
    h = store_backend
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('BATCH_VENDOR_FAILOVER_ENABLED', 'false')
    (unit,) = seed(h)
    artifacts = Artifacts()
    service = health(lambda: T0)
    vendor = Mock(
        return_value={
            'audio_seconds': 5.0,
            'speech_seconds': 1.0,
            'speech_spans': [{'start': 0, 'end': 1}],
            'words': [{'word': 'synthetic', 'timestamp': [0, 1], 'speaker': 'SPEAKER_00'}],
            'diarization': {'turns': []},
            'words_provider': 'modulate',
            'language': 'ja',
            'recovery_version': 1,
        }
    )
    first = provider_stt.ProviderSttStage(
        h.store,
        artifacts,
        stt=vendor,
        allowed=lambda *_: True,
        inspect=lambda *_: (b'\0\0', 5.0, [{'start': 0, 'end': 1}]),
        clock=lambda: T0,
        health=service,
        armed=lambda: True,
    )
    assert first.run(unit.segment_id).outcome == 'retry'
    assert not read(h, unit.segment_id)['provider_intent'].get('vendor_skipped')
    artifacts.fail = False
    stage(h, artifacts, vendor, service, T0 + provider_stt.ABANDON_SECONDS + 1).run(unit.segment_id)
    settled = read(h, unit.segment_id)
    assert settled['state'] == 'quarantined'
    attempt = VendorAttempt.from_dict(settled['provider_attempts'][-1])
    assert attempt.outcome.value == 'abandoned' and attempt.billable and attempt.audio_seconds == 5
    assert vendor.call_count == 1
    service.record_attempt.assert_called_once()
