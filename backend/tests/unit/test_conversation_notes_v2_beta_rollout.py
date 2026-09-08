"""Where the conversation-notes-v2 rollout is on, and where it is not.

`CONVERSATION_NOTES_V2_ENABLED` went prod-on 2026-09-01 after the dev/Beta bake; the calendar
context read and OCR context flags are still dev-only pending their own bakes. The dev
environment doubles as the Beta ring: the `mobile_beta` profile and the beta desktop bundle
are pinned to the dev backend (`api.omiapi.com`) while authenticating against the production
Firebase project, so a flag still dark in prod reaches Beta users by turning dev on.

Keeps this file import-light so the fast-unit duration guard stays honest.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[2]

ROLLOUT_FLAGS = (
    'CONVERSATION_NOTES_V2_ENABLED',
    'CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED',
    'CONVERSATION_OCR_CONTEXT_ENABLED',
)

# backend-listen finalizes a live conversation; gke/pusher hosts the same
# process_conversation path after 2026-08-30; cloud_run/backend runs it inline
# for POST /v1/conversations/{id}/reprocess. All three must agree or a captured
# conversation and a regenerate/pusher finalization produce different pipelines.
SUMMARY_PIPELINE_SCOPES = ('gke/backend-listen', 'gke/pusher', 'cloud_run/backend')


@functools.cache
def _composed() -> dict:
    return yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))


def _env_maps(environment: dict) -> dict[str, dict]:
    return {
        'gke/backend-listen': environment['gke']['backend-listen']['env'],
        'gke/pusher': environment['gke']['pusher']['env'],
        'cloud_run/backend': environment['cloud_run']['services']['backend']['env'],
    }


def _value(env_map: dict, key: str) -> str:
    entry = env_map.get(key) or {}
    return (entry.get('value') or '').strip().lower()


def test_dev_enables_every_rollout_flag_on_every_summary_pipeline_service():
    env_maps = _env_maps(_composed()['environments']['dev'])
    for scope in SUMMARY_PIPELINE_SCOPES:
        for flag in ROLLOUT_FLAGS:
            assert _value(env_maps[scope], flag) == 'true', f'{scope}:{flag}'


def test_prod_enables_conversation_notes_v2_on_every_summary_pipeline_service():
    """Notes v2 went prod-on 2026-09-01 after the dev/Beta bake."""
    env_maps = _env_maps(_composed()['environments']['prod'])
    for scope in SUMMARY_PIPELINE_SCOPES:
        assert _value(env_maps[scope], 'CONVERSATION_NOTES_V2_ENABLED') == 'true', f'{scope}'


def test_prod_keeps_calendar_and_ocr_context_flags_dark():
    """Calendar context read and OCR context stay dev-only until their own bakes."""
    env_maps = _env_maps(_composed()['environments']['prod'])
    for scope in SUMMARY_PIPELINE_SCOPES:
        for flag in ('CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED', 'CONVERSATION_OCR_CONTEXT_ENABLED'):
            assert _value(env_maps[scope], flag) == 'false', f'{scope}:{flag}'


def test_reprocess_cannot_disagree_with_live_finalization():
    """The defect this guards is silent: flags declared on only one service.

    Live capture would produce a v2 note and "regenerate" would quietly fall back to the
    legacy pipeline, which reads as a model regression rather than a config gap.
    """
    for environment in _composed()['environments'].values():
        env_maps = _env_maps(environment)
        for flag in ROLLOUT_FLAGS:
            values = {scope: _value(env_maps[scope], flag) for scope in SUMMARY_PIPELINE_SCOPES}
            assert len(set(values.values())) == 1, f'{flag}: {values}'
            assert values['gke/backend-listen'] != '', flag
            assert values['gke/pusher'] != '', flag


def test_the_deployed_chart_values_match_the_composed_manifest():
    """Helm reads the values file, not runtime_env.yaml, so drift here is what actually ships."""
    composed = _composed()
    for environment, chart_dir, chart, scope in (
        ('dev', 'backend-listen', 'dev_omi_backend_listen_values.yaml', 'gke/backend-listen'),
        ('prod', 'backend-listen', 'prod_omi_backend_listen_values.yaml', 'gke/backend-listen'),
        ('dev', 'pusher', 'dev_omi_pusher_values.yaml', 'gke/pusher'),
        ('prod', 'pusher', 'prod_omi_pusher_values.yaml', 'gke/pusher'),
    ):
        values = yaml.safe_load((BACKEND / 'charts' / chart_dir / chart).read_text(encoding='utf-8'))
        rendered = {entry['name']: str(entry.get('value', '')).strip().lower() for entry in values['env']}
        expected = _env_maps(composed['environments'][environment])[scope]
        for flag in ROLLOUT_FLAGS:
            assert rendered.get(flag) == _value(expected, flag), f'{environment}:{scope}:{flag}'
