"""Closed label and cancellation contracts for pusher receive observations."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import yaml

from routers import metrics as metrics_router
from utils import pusher_receive_metrics as metrics


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', metrics.STAGES)
async def test_current_stall_visible_before_completion_and_unwinds_on_cancel(monkeypatch, stage):
    callbacks = []
    handles = []
    clock = [0.0]

    def later(delay, callback):
        assert delay == 300
        callbacks.append(callback)
        handle = SimpleNamespace(cancelled=False)
        handle.cancel = lambda: setattr(handle, 'cancelled', True)
        handles.append(handle)
        return handle

    monkeypatch.setattr(metrics, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(metrics.asyncio, 'get_running_loop', lambda: SimpleNamespace(call_later=later))
    counter = metrics.WORK_STALLS.labels(stage)
    gauge = metrics.WORK_STALLED.labels(stage)
    histogram = metrics.WORK_DURATION.labels(stage)
    before = counter._value.get(), gauge._value.get(), histogram._sum.get()
    with pytest.raises(asyncio.CancelledError):
        with metrics.observe_work(stage):
            clock[0] = 301
            callbacks[0]()
            assert counter._value.get() == before[0] + 1
            assert gauge._value.get() == before[1] + 1
            raise asyncio.CancelledError
    assert handles[0].cancelled
    assert counter._value.get() == before[0] + 1
    assert gauge._value.get() == before[1]
    assert histogram._sum.get() == before[2] + 301


@pytest.mark.asyncio
async def test_overdue_callback_and_fast_completion(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(metrics, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    before = metrics.WORK_STALLS.labels('custody_commit')._value.get()
    with metrics.observe_work('custody_commit'):
        clock[0] = 301
    assert metrics.WORK_STALLS.labels('custody_commit')._value.get() == before + 1
    with metrics.observe_work('custody_commit'):
        pass
    assert metrics.WORK_STALLS.labels('custody_commit')._value.get() == before + 1
    with pytest.raises(ValueError):
        with metrics.observe_work('untrusted'):
            pass


def test_socket_frames_use_closed_age_and_kind_labels(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(metrics, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    observation = metrics.SocketObservation()
    observation.reason = 'peer'
    for age, bucket in ((0, '<5m'), (300, '5m_to_30m'), (1800, '30m_plus')):
        for header, kind in ((100, 'heartbeat'), (101, 'audio'), (103, 'control'), (None, 'invalid')):
            clock[0] = age
            counter = metrics.SOCKET_FRAMES.labels(kind, bucket)
            before = counter._value.get()
            observation.frame(header)
            assert counter._value.get() == before + 1
    counter = metrics.SOCKET_CLOSED.labels('peer', '30m_plus', 'audio')
    before = counter._value.get()
    observation.close()
    observation.close()
    assert counter._value.get() == before + 1


def test_authorized_metrics_route_exposes_all_bounded_children(monkeypatch):
    monkeypatch.setenv('METRICS_SECRET', 'synthetic-scrape-token')
    app = FastAPI()
    app.include_router(metrics_router.router)
    with TestClient(app) as client:
        assert client.get('/metrics').status_code == 401
        response = client.get('/metrics', headers={'Authorization': 'Bearer synthetic-scrape-token'})
    assert response.status_code == 200
    families = (
        metrics.SOCKET_FRAMES,
        metrics.SOCKET_CLOSED,
        metrics.WORK_STALLS,
        metrics.WORK_STALLED,
        metrics.WORK_DURATION,
    )
    samples = [sample for family in families for metric in family.collect() for sample in metric.samples]
    assert len([sample for sample in samples if not sample.name.endswith('_created')]) == 140
    assert len(samples) <= 225  # Production may expose prometheus_client's *_created series.
    for sample in samples:
        assert sample.name in response.text
        assert set(sample.labels) <= {'kind', 'age_bucket', 'reason', 'frames_seen', 'stage', 'le'}


@pytest.mark.parametrize('environment', ['prod', 'dev'])
def test_committed_pusher_scrape_has_no_metric_filter(environment):
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load(
        (root / f'charts/monitoring/kube-prometheus-stack/{environment}_omi_monitoring_values.yaml').read_text()
    )
    jobs = config['prometheus']['prometheusSpec']['additionalScrapeConfigs']
    job = next(job for job in jobs if job['job_name'] == 'pusher-metrics')
    assert job['metrics_path'] == '/metrics'
    assert job['authorization']['credentials_file'].endswith('/metrics-scrape-token/token')
    assert not job.get('metric_relabel_configs')
    assert 'app.include_router(metrics.router)' in (root / 'pusher/main.py').read_text()
