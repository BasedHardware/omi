"""Prod Cloud Run jobs that were moved off the nik-164 key stay keyless on their runtime identity."""

from pathlib import Path

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[2]
JOBS_RUNTIME_SA = 'backend-jobs-runtime@based-hardware.iam.gserviceaccount.com'
KEY_ENV = ('SERVICE_ACCOUNT_JSON', 'GOOGLE_APPLICATION_CREDENTIALS')

# The 4.7k-line runtime manifest and the workflow file are read+parsed once at
# module import — the fast-unit guard only measures call-phase CPU, so doing it
# per-test pushed this file over the 1s fail limit under a loaded CI runner.
_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
_MANIFEST = yaml.load((BACKEND / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'), Loader=_LOADER)
_NOTIFICATIONS_WORKFLOW = (BACKEND.parent / '.github/workflows/gcp_notifications_job.yml').read_text(encoding='utf-8')


@pytest.mark.parametrize('job', ['notifications-job', 'day3-reengagement-email-job'])
def test_prod_job_runs_as_jobs_runtime_and_drops_the_key(job):
    config = _MANIFEST['environments']['prod']['cloud_run']['jobs'][job]

    assert config['flags']['--service-account'] == JOBS_RUNTIME_SA
    # deploy-cloudrun deploys job secrets with --set-secrets (full replacement), which gcloud refuses
    # to combine with --remove-secrets; the replacement itself drops the undeclared key ref.
    assert '--remove-secrets' not in config['flags']
    assert not set(KEY_ENV) & set(config.get('secrets') or {})
    assert not set(KEY_ENV) & set(config.get('env') or {})


def test_notifications_deploy_strips_the_legacy_key_path_literal():
    assert 'DAILY_SUMMARY_SELECTION_MODE,GOOGLE_APPLICATION_CREDENTIALS,' in _NOTIFICATIONS_WORKFLOW
