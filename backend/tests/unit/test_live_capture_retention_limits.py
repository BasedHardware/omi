"""Kill-switch declarations and bounded, fail-closed retention."""

from pathlib import Path

import pytest
import yaml

from config.audio_timeline import live_capture_window_retention_enabled, live_capture_window_merge_preservation_enabled
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


_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)


@pytest.fixture(scope='module')
def declarations():
    """Parse the manifest and chart values once, outside the timed call phase."""
    manifest = yaml.load((BACKEND / 'deploy/runtime_env.yaml').read_text(), Loader=_LOADER)
    charts = {
        path: yaml.load(path.read_text(), Loader=_LOADER)['env']
        for chart in ('backend-listen', 'pusher')
        for path in (BACKEND / 'charts' / chart).glob('*values.yaml')
    }
    return manifest, charts


# Rollout (2026-10-05): the proven merge union is on for prod listen and its inert pusher mirror.
UNION_ON_SCOPES = {('prod', 'backend-listen'), ('prod', 'pusher')}


def test_composed_and_helm_declarations_pin_rollout_state(declarations):
    manifest, charts = declarations
    off_flags = (
        FLAG,
        'LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION',
        'LIVE_CAPTURE_WINDOW_STRICT_PROJECTION',
    )
    union = 'LIVE_CAPTURE_WINDOW_MERGE_UNION'
    for env_name, env in manifest['environments'].items():
        services = {**env['gke'], **env['cloud_run']['services']}
        for name, service in services.items():
            declared = service.get('env', {})
            for flag in off_flags:
                if flag in declared:
                    assert declared[flag] == {'category': 'rollout', 'value': 'false'}
            if union in declared:
                expected = 'true' if (env_name, name) in UNION_ON_SCOPES else 'false'
                assert declared[union] == {'category': 'rollout', 'value': expected}
    assert charts
    for path, values in charts.items():
        for flag in off_flags:
            assert [v for v in values if v.get('name') == flag] == [{'name': flag, 'value': 'false'}]
        expected = 'true' if path.name.startswith('prod_') else 'false'
        assert [v for v in values if v.get('name') == union] == [{'name': union, 'value': expected}]


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


@pytest.mark.parametrize('value', [None, '', 'false', '0', 'garbage', 'true', '1', 'yes', 'on'])
def test_merge_preservation_default_off_parser(monkeypatch, value):
    flag = 'LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION'
    if value is None:
        monkeypatch.delenv(flag, raising=False)
    else:
        monkeypatch.setenv(flag, value)
    assert live_capture_window_merge_preservation_enabled() == (value in ('true', '1', 'yes', 'on'))
