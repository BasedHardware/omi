from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
FLAG = 'MEETING_RECEIPT_RECONCILER_ENABLED'


def test_meeting_receipt_reconciler_flag_is_off_on_both_code_path_cohosts():
    manifest = yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text())

    for environment_name, environment in manifest['environments'].items():
        listen_flag = environment['gke']['backend-listen']['env'][FLAG]
        backend_flag = environment['cloud_run']['services']['backend']['env'][FLAG]
        assert listen_flag == {'value': 'false', 'category': 'rollout'}, environment_name
        assert backend_flag == {'value': 'false', 'category': 'rollout'}, environment_name
