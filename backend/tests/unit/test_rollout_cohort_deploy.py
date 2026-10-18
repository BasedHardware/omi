"""No serving platform receives private identity bindings from public manifests."""

from pathlib import Path
import re
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def private_key(name):
    return name.endswith('_UID_ALLOWLIST') or name in {'MOBILE_STANDARD_BATCH_UIDS', 'OMI_MESSAGING_CHANNELS_UIDS'}


def assert_private_bindings_absent(value):
    if isinstance(value, dict):
        for key, child in value.items():
            assert not private_key(key), key
            if key == 'name' and isinstance(child, str):
                assert not private_key(child), child
            assert_private_bindings_absent(child)
    elif isinstance(value, list):
        for child in value:
            assert_private_bindings_absent(child)


def test_manifest_and_source_overlays_have_no_uid_binding_exceptions():
    files = [ROOT / 'backend/deploy/runtime_env.yaml', *sorted((ROOT / 'backend/deploy/runtime_env').glob('*.yaml'))]
    for path in files:
        text = path.read_text()
        assert_private_bindings_absent(yaml.load(text, Loader=yaml.CSafeLoader))
        # Firebase-style UID literals must not be hidden inside a JSON policy.
        assert not re.search(r'\b[A-Za-z0-9]{28}\b', text), path


@pytest.mark.parametrize('component', ['backend-listen', 'pusher'])
@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_helm_replace_leaves_cohort_keys_absent(component, stage):
    path = ROOT / f'backend/charts/{component}/{stage}_omi_{component.replace("-", "_")}_values.yaml'
    # pusher's filenames have the same stage_omi_component form.
    assert_private_bindings_absent(yaml.load(path.read_text(), Loader=yaml.CSafeLoader))


def test_no_secret_manager_cohort_provisioning_remains():
    path = ROOT / 'backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml'
    assert_private_bindings_absent(yaml.load(path.read_text(), Loader=yaml.CSafeLoader))
    assert not (ROOT / 'backend/scripts/private_cohort_secrets.py').exists()


def test_cloud_run_merge_and_helm_replace_are_paired_with_cohort_aware_runtime():
    # Cloud Run merge may retain a legacy literal; runtime supports it only for
    # an absent Firestore field. Helm replaces the env list; absent keys deny.
    from config.batch_pipeline import enabled_for
    from database import rollout_cohorts

    assert callable(enabled_for) and callable(rollout_cohorts.in_rollout_cohort)
    source = (ROOT / 'backend/config/summary_guarantee.py').read_text()
    assert "'FIRST_SUMMARY_UID_ALLOWLIST' in os.environ" in source
    listen = (ROOT / 'backend/routers/transcribe.py').read_text()
    assert listen.index('await warm_rollout_cohorts(request.uid)') < listen.index('run_listen_session(request)')
