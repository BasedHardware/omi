"""AUDIO_TIMELINE_SPANS and LIVE_SPEAKER_SPAN_RESOLUTION deployment defaults.

Both rollout switches must default off in source and stay pinned off in every
composed deployment declaration until the staged rollout promotes them.
Keeps this file import-light so the fast-unit duration guard stays honest.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from config.audio_timeline import audio_timeline_spans_enabled, live_speaker_span_resolution_enabled

BACKEND = Path(__file__).resolve().parents[2]

FLAGS = ('AUDIO_TIMELINE_SPANS', 'LIVE_SPEAKER_SPAN_RESOLUTION')


def test_flags_default_off(monkeypatch):
    for flag in FLAGS:
        monkeypatch.delenv(flag, raising=False)
    assert audio_timeline_spans_enabled() is False
    assert live_speaker_span_resolution_enabled() is False


def test_flags_truthy_parser(monkeypatch):
    monkeypatch.setenv('AUDIO_TIMELINE_SPANS', 'true')
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', '1')
    assert audio_timeline_spans_enabled() is True
    assert live_speaker_span_resolution_enabled() is True
    monkeypatch.setenv('AUDIO_TIMELINE_SPANS', '0')
    monkeypatch.setenv('LIVE_SPEAKER_SPAN_RESOLUTION', 'off')
    assert audio_timeline_spans_enabled() is False
    assert live_speaker_span_resolution_enabled() is False


def test_composed_declarations_pin_both_flags_off():
    composed = yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))

    def _env_maps(environment):
        env = composed['environments'][environment]
        yield f'{environment}/gke/backend-listen', env['gke']['backend-listen']['env']
        yield f'{environment}/gke/pusher', env['gke']['pusher']['env']
        for name, service in env['cloud_run']['services'].items():
            yield f'{environment}/cloud_run/{name}', service['env']

    for environment in ('dev', 'prod'):
        for scope, env_map in _env_maps(environment):
            for flag in FLAGS:
                entry = env_map.get(flag)
                assert entry is not None, f'{scope} must declare {flag}'
                assert (entry.get('value') or '').strip().lower() == 'false', f'{scope} must pin {flag} false'
        for name, job in composed['environments'][environment]['cloud_run'].get('jobs', {}).items():
            for flag in FLAGS:
                entry = job['env'].get(flag)
                if entry is not None:
                    assert (
                        entry.get('value') or ''
                    ).strip().lower() == 'false', f'{environment}/cloud_run_jobs/{name} must pin {flag} false'
