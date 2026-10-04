"""Kill-switch declarations and bounded, fail-closed retention."""

from pathlib import Path

import pytest
import yaml

from config.audio_timeline import live_capture_window_retention_enabled
from utils.audio_timeline import CaptureTimeline, SendMap

FLAG = 'LIVE_CAPTURE_WINDOW_RETENTION'
BACKEND = Path(__file__).resolve().parents[2]


def test_default_off_and_limits_snapshotted(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert not live_capture_window_retention_enabled()
    timeline = CaptureTimeline(100)
    sends = SendMap(100)
    assert timeline.max_anchors == 64 and sends._max_spans == 4096
    monkeypatch.setenv(FLAG, 'true')
    assert live_capture_window_retention_enabled()
    assert timeline.max_anchors == 64 and sends._max_spans == 4096
    assert CaptureTimeline(100).max_anchors == 512
    assert SendMap(100)._max_spans == 16384


@pytest.mark.parametrize('value', ['', 'FALSE', '0', 'garbage'])
def test_unrecognized_or_falsy_flag_is_off(monkeypatch, value):
    monkeypatch.setenv(FLAG, value)
    assert not live_capture_window_retention_enabled()


def test_composed_and_helm_declarations_are_all_off():
    manifest = yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text())
    for env in manifest['environments'].values():
        for service in (*env['gke'].values(), *env['cloud_run']['services'].values()):
            if FLAG in service.get('env', {}):
                assert service['env'][FLAG] == {'category': 'rollout', 'value': 'false'}
    for chart in ('backend-listen', 'pusher'):
        for path in (BACKEND / 'charts' / chart).glob('*values.yaml'):
            declarations = [v for v in yaml.safe_load(path.read_text())['env'] if v.get('name') == FLAG]
            assert declarations == [{'name': FLAG, 'value': 'false'}]


@pytest.mark.parametrize('enabled', [False, True])
def test_bounds_still_evict_and_refuse_old_positions(monkeypatch, enabled):
    monkeypatch.setenv(FLAG, 'true' if enabled else 'false')
    timeline = CaptureTimeline(100)
    for i in range(timeline.max_anchors + 1):
        timeline.accept(b'\0\0' * 100, 101 + i * 4, 1 + i * 4)
    assert len(timeline.anchors) == timeline.max_anchors
    assert timeline.wall_strict(50) is None
    sends = SendMap(100)
    for i in range(sends._max_spans + 1):
        sends.add_accepted(i * 100, i * 200, 100)
    assert sends.span_count == sends._max_spans
    assert sends.map_interval(0, 50) is None
    assert sends.map_interval(150, 250) is None  # gap is still unobserved
