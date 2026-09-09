"""D2 (plan-source-of-truth): the plan catalog is the only source of plan quotas.

Before D2 the ``BASIC_TIER_*`` env overlays outranked ``config/plan_catalog.json``
at runtime (``utils.subscription._basic_transcription_overlay``), so the prod API
plane advertised 600 free minutes while the listen plane enforced 300. D2 deletes
the overlays from every serving identity: both backend-listen charts, both pusher
charts, and the Cloud Run services (via the manifest's ``forbidden_env`` contract,
which the runtime-env validator turns into a required ``--remove-env-vars`` entry
at deploy time and an absence check against the live service afterwards).

Automatic-or-dead: re-adding an overlay to any chart fails the chart scan here;
dropping a name from the deploy actions' ``--remove-env-vars`` fails the real
workflow validator (driven below over the repository's own manifest and actions);
deleting the manifest ``forbidden_env`` fails the manifest pin. The chart scan and
the manifest pin are static checkers of declared configuration; the workflow
validator run is behavioral (it is the code the deploy action executes).
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest
import yaml

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
VALIDATOR = BACKEND / 'scripts/validate-backend-runtime-env.py'
MANIFEST = BACKEND / 'deploy/runtime_env.yaml'

RETIRED_PLAN_QUOTA_ENV = frozenset(
    {
        'BASIC_TIER_MINUTES_LIMIT_PER_MONTH',
        'BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH',
        'BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH',
        # Never read by code; still present on the live Cloud Run services.
        'BASIC_TIER_MEMORIES_CREATED_LIMIT_PER_MONTH',
    }
)

SERVING_CHARTS = (
    'backend/charts/backend-listen/dev_omi_backend_listen_values.yaml',
    'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml',
    'backend/charts/pusher/dev_omi_pusher_values.yaml',
    'backend/charts/pusher/prod_omi_pusher_values.yaml',
)

CLOUD_RUN_CONVERSATION_SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')

DEPLOY_ACTIONS = (
    '.github/actions/deploy-backend-stack/action.yml',
    '.github/actions/sync-backfill-lifecycle/action.yml',
)


def _chart_env_names(path: Path) -> set[str]:
    return set(re.findall(r'^\s*- name:\s+([A-Z0-9_]+)\s*$', path.read_text(encoding='utf-8'), re.MULTILINE))


@pytest.mark.parametrize('chart', SERVING_CHARTS)
def test_no_plan_quota_overlay_on_any_gke_serving_identity(chart: str) -> None:
    names = _chart_env_names(REPO / chart)
    assert not (names & RETIRED_PLAN_QUOTA_ENV), f'{chart} still declares a plan quota overlay'
    assert not {name for name in names if name.startswith('BASIC_TIER_')}, chart


@pytest.mark.parametrize('env', ('dev', 'prod'))
def test_manifest_forbids_plan_quota_overlays_on_every_cloud_run_conversation_service(env: str) -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))
    services = manifest['environments'][env]['cloud_run']['services']
    for service in CLOUD_RUN_CONVERSATION_SERVICES:
        config = services[service]
        assert RETIRED_PLAN_QUOTA_ENV <= set(config.get('forbidden_env') or ()), f'{env}/{service}'
        declared = set(config.get('env') or {}) | set(config.get('secrets') or {})
        assert not (declared & RETIRED_PLAN_QUOTA_ENV), f'{env}/{service} declares a retired overlay'


def _load_validator():
    spec = importlib.util.spec_from_file_location('validate_backend_runtime_env_d2', VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('env', ('dev', 'prod'))
def test_deploy_actions_strip_the_overlays_from_every_cloud_run_service(env: str) -> None:
    """Drive the real workflow validator over the repository's manifest and actions."""
    validator = _load_validator()
    manifest = validator._load_yaml(MANIFEST)
    errors = validator._validate_cloud_run_workflows(
        env,
        validator._get_env_config(manifest, env),
        strict_provisional=False,
        manifest_path=MANIFEST,
        manifest=manifest,
        workflow_root=REPO,
    )
    overlay_errors = [error for error in errors if 'BASIC_TIER_' in str(error)]
    assert overlay_errors == [], overlay_errors


@pytest.mark.parametrize('name', sorted(RETIRED_PLAN_QUOTA_ENV))
def test_workflow_validator_rejects_a_missing_removal(name: str) -> None:
    from scripts.runtime_env_validation import workflows as validator

    flags = {'--remove-env-vars': ','.join(sorted(RETIRED_PLAN_QUOTA_ENV - {name}))}
    errors = validator._validate_forbidden_workflow_removals(
        scope='cloud_run_workflow/backend',
        forbidden=sorted(RETIRED_PLAN_QUOTA_ENV),
        flags=flags,
    )
    assert [str(error) for error in errors] == [
        str(
            validator.ValidationError(
                'cloud_run_workflow/backend', f'forbidden env {name} must be listed in --remove-env-vars'
            )
        )
    ]


@pytest.mark.parametrize('action', DEPLOY_ACTIONS)
def test_deploy_action_remove_lists_name_every_overlay(action: str) -> None:
    """Static tripwire over the composite actions the manifest validator expands."""
    text = (REPO / action).read_text(encoding='utf-8')
    lists = re.findall(r'--remove-env-vars=([A-Z0-9_,]+)', text)
    assert lists, action
    for entry in lists:
        assert RETIRED_PLAN_QUOTA_ENV <= set(entry.split(',')), (action, entry)


@pytest.mark.slow  # per-test fresh reload of utils.subscription (~1 s CPU); slow-guardrail lane
def test_catalog_is_the_only_source_when_no_overlay_is_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the overlays gone, Free transcription is the catalog's 300 minutes on every plane."""
    for name in RETIRED_PLAN_QUOTA_ENV:
        monkeypatch.delenv(name, raising=False)
    from config.plan_catalog import PlanType, allocation_limit
    from utils import subscription as sub_mod

    sub_mod = importlib.reload(sub_mod)
    try:
        assert allocation_limit(PlanType.basic, 'transcription') == 18000
        assert sub_mod.BASIC_TIER_MONTHLY_SECONDS_LIMIT == 18000
        assert sub_mod.BASIC_TIER_MINUTES_LIMIT_PER_MONTH == 300
        # Catalog "unlimited" is None; the legacy zero sentinel is no longer consulted.
        assert sub_mod.BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH is None
        assert sub_mod.BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH is None
    finally:
        monkeypatch.undo()
        importlib.reload(sub_mod)
