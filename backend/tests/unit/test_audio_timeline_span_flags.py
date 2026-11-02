"""Graduated span storage and resolution keep deployment declarations retired."""

from __future__ import annotations

from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[2]

FLAGS = ('AUDIO_TIMELINE_SPANS', 'LIVE_SPEAKER_SPAN_RESOLUTION')
SPANS_ON_SCOPES = {'prod/gke/backend-listen', 'prod/gke/pusher'}


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
                assert flag not in env_map, f'{scope} must not declare retired {flag}'
            if scope in SPANS_ON_SCOPES:
                # Spans must never ride on the v2 text translation that dropped
                # rejected segments in the 2026-09-26 flip.
                v2 = env_map.get('AUDIO_TIMELINE_V2')
                assert (
                    v2 is None or (v2.get('value') or '').strip().lower() == 'false'
                ), f'{scope} must keep AUDIO_TIMELINE_V2 false while spans are on'
        for name, job in composed['environments'][environment]['cloud_run'].get('jobs', {}).items():
            for flag in FLAGS:
                assert flag not in job['env'], f'{environment}/cloud_run_jobs/{name} must not declare {flag}'


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
        for flag in FLAGS:
            assert flag not in env, f'{chart} must not declare retired {flag}'
        assert env.get('AUDIO_TIMELINE_V2') == 'false', f'{chart} prod must keep AUDIO_TIMELINE_V2 false'
