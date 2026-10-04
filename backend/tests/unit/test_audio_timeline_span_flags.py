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


# Rollout step 2 (2026-10-04): span-bearing storage is on for prod listen and
# pusher only; the resolution consumer stays off everywhere.
SPANS_ON_SCOPES = {'prod/gke/backend-listen', 'prod/gke/pusher'}


# Rollout step 3: the resolution consumer is on for every prod processing host.
CONSUMER_ON_SCOPES = SPANS_ON_SCOPES | {
    'prod/cloud_run/backend',
    'prod/cloud_run/backend-sync',
    'prod/cloud_run/backend-sync-backfill',
    'prod/cloud_run/backend-integration',
}


def _expected(flag, scope):
    if flag == 'AUDIO_TIMELINE_SPANS':
        return 'true' if scope in SPANS_ON_SCOPES else 'false'
    return 'true' if scope in CONSUMER_ON_SCOPES else 'false'


def test_composed_declarations_pin_rollout_state():
    composed = yaml.load(
        (BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'),
        Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader),
    )

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
                expected = _expected(flag, scope)
                assert (entry.get('value') or '').strip().lower() == expected, f'{scope} must pin {flag} {expected}'
            if scope in SPANS_ON_SCOPES:
                # Spans must never ride on the v2 text translation that dropped
                # rejected segments in the 2026-09-26 flip.
                v2 = env_map.get('AUDIO_TIMELINE_V2')
                assert (
                    v2 is None or (v2.get('value') or '').strip().lower() == 'false'
                ), f'{scope} must keep AUDIO_TIMELINE_V2 false while spans are on'
        for name, job in composed['environments'][environment]['cloud_run'].get('jobs', {}).items():
            for flag in FLAGS:
                entry = job['env'].get(flag)
                if entry is not None:
                    assert (
                        entry.get('value') or ''
                    ).strip().lower() == 'false', f'{environment}/cloud_run_jobs/{name} must pin {flag} false'


def test_prod_helm_values_keep_v2_off_where_spans_are_on():
    for chart, values in (
        ('backend-listen', 'prod_omi_backend_listen_values.yaml'),
        ('pusher', 'prod_omi_pusher_values.yaml'),
    ):
        text = (BACKEND / 'charts' / chart / values).read_text(encoding='utf-8')
        env = {}
        name = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('- name:'):
                name = stripped.split(':', 1)[1].strip()
            elif stripped.startswith('value:') and name:
                env[name] = stripped.split(':', 1)[1].strip().strip('"\'').lower()
                name = None
        assert env.get('AUDIO_TIMELINE_SPANS') == 'true', f'{chart} prod must enable spans'
        assert env.get('LIVE_SPEAKER_SPAN_RESOLUTION') == 'true', f'{chart} prod must enable the consumer'
        assert env.get('AUDIO_TIMELINE_V2') == 'false', f'{chart} prod must keep AUDIO_TIMELINE_V2 false'
