"""Where the conversation-notes-v2 rollout is on, and where it is not.

The beta ring is a deployment, not a cohort: the `mobile_beta` profile and the beta desktop
bundle are both pinned to the dev backend (`api.omiapi.com`) while authenticating against the
production Firebase project. Turning the rollout flags on in the dev runtime environment is
therefore how the feature reaches beta users without reaching production users.

Keeps this file import-light so the fast-unit duration guard stays honest.
"""

from __future__ import annotations

from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[2]

ROLLOUT_FLAGS = (
    'CONVERSATION_NOTES_V2_ENABLED',
    'CONVERSATION_CALENDAR_CONTEXT_READ_ENABLED',
    'CONVERSATION_OCR_CONTEXT_ENABLED',
)

# backend-listen finalizes a live conversation; cloud_run/backend runs process_conversation
# inline for POST /v1/conversations/{id}/reprocess. Both must agree or "regenerate" produces
# a different summary pipeline than the one that captured the conversation.
SUMMARY_PIPELINE_SCOPES = ('gke/backend-listen', 'cloud_run/backend')


def _composed() -> dict:
    return yaml.safe_load((BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))


def _env_maps(environment: dict) -> dict[str, dict]:
    return {
        'gke/backend-listen': environment['gke']['backend-listen']['env'],
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


def test_prod_still_ships_every_rollout_flag_dark():
    env_maps = _env_maps(_composed()['environments']['prod'])
    for scope in SUMMARY_PIPELINE_SCOPES:
        for flag in ROLLOUT_FLAGS:
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


def test_the_deployed_chart_values_match_the_composed_manifest():
    """Helm reads the values file, not runtime_env.yaml, so drift here is what actually ships."""
    composed = _composed()
    for environment, chart in (
        ('dev', 'dev_omi_backend_listen_values.yaml'),
        ('prod', 'prod_omi_backend_listen_values.yaml'),
    ):
        values = yaml.safe_load((BACKEND / 'charts/backend-listen' / chart).read_text(encoding='utf-8'))
        rendered = {entry['name']: str(entry.get('value', '')).strip().lower() for entry in values['env']}
        expected = _env_maps(composed['environments'][environment])['gke/backend-listen']
        for flag in ROLLOUT_FLAGS:
            assert rendered.get(flag) == _value(expected, flag), f'{environment}:{flag}'
