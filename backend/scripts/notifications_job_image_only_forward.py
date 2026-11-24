#!/usr/bin/env python3
"""Load the runtime manifest for notifications image validation and apply."""

from notifications_job_image_only import BLANK, ENDPOINT, require, run_cli
from render_backend_runtime_env import DEFAULT_MANIFEST, _load_yaml, _render_env_entries


def load_expected_env():
    env = _load_yaml(DEFAULT_MANIFEST)['environments']['prod']['cloud_run']['jobs']['notifications-job']['env']
    expected = {
        entry['name']: entry['value'] for entry in _render_env_entries({name: env[name] for name in (ENDPOINT, BLANK)})
    }
    require(expected[ENDPOINT] and expected[ENDPOINT] != 'http://127.0.0.1:9', 'Missing verified gateway endpoint')
    return expected


if __name__ == '__main__':
    run_cli(load_expected_env)
