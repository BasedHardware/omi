"""Reject repeated YAML mapping keys before runtime configuration composition."""

from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    'mapping',
    [
        "AUDIO_ARCHIVE_STOP_PCM_PERCENT:\n  value: '0'\n  value: '0'\n",
        "AUDIO_ARCHIVE_STOP_PCM_PERCENT:\n  category: rollout\n  category: rollout\n",
        "AUDIO_ARCHIVE_STOP_PCM_PERCENT: {value: '0', value: '1'}\n",
    ],
)
def test_runtime_env_composer_rejects_duplicate_mapping_keys(tmp_path, mapping):
    composer = runpy.run_path(str(ROOT / 'deploy/compose_runtime_env.py'))
    source = tmp_path / 'duplicate.yaml'
    source.write_text(mapping)
    with pytest.raises(ValueError, match='duplicate YAML mapping key'):
        composer['_load_yaml'](source)
