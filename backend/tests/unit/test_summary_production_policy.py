"""Keep the first-summary budget consistent across its real production hosts."""

from pathlib import Path

import yaml


def test_production_producers_and_workers_share_the_first_summary_deadline():
    manifest = yaml.load((Path(__file__).parents[2] / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    prod = manifest['environments']['prod']
    hosts = {**prod['gke'], **prod['cloud_run']['services']}
    for name in ('backend-listen', 'pusher', 'backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        env = hosts[name]['env']
        assert env['FIRST_SUMMARY_DEADLINE_ENABLED']['value'] == 'true', name
        assert env['FIRST_SUMMARY_DEADLINE_PERCENT']['value'] == '100', name
    assert hosts['backend-sync']['env']['SUMMARY_DEBT_REPAIR_ENABLED']['value'] == 'true'
