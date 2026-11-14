"""Source overlays must compose exactly to the checked-in deploy manifest."""

import runpy
from pathlib import Path

import yaml
import pytest

ROOT = Path(__file__).resolve().parents[3]
SAFE_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
COMPOSER = runpy.run_path(str(ROOT / 'backend/deploy/compose_runtime_env.py'))


def test_checked_in_manifest_matches_sources():
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=SAFE_LOADER)
    assert COMPOSER['compose_manifest']() == manifest


def test_docket_retirements_have_no_source_bindings():
    registry = yaml.load((ROOT / 'config/feature-flags.yaml').read_text(), Loader=SAFE_LOADER)
    retired = {row['key'] for row in registry['retired'] if 'David flag docket 2026-11-09' in row.get('reason', '')}
    assert retired

    def mapping_keys(value):
        if isinstance(value, dict):
            yield from value
            for child in value.values():
                yield from mapping_keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from mapping_keys(child)

    for name in ('_base.yaml', 'dev.overlay.yaml', 'prod.overlay.yaml'):
        source = yaml.load((ROOT / 'backend/deploy/runtime_env' / name).read_text(), Loader=SAFE_LOADER)
        assert retired.isdisjoint(mapping_keys(source)), name


@pytest.mark.parametrize(
    'mapping',
    [
        "AUDIO_ARCHIVE_STOP_PCM_PERCENT:\n  value: '0'\n  value: '0'\n",
        "AUDIO_ARCHIVE_STOP_PCM_PERCENT:\n  category: rollout\n  category: rollout\n",
        "AUDIO_ARCHIVE_STOP_PCM_PERCENT: {value: '0', value: '1'}\n",
    ],
)
def test_runtime_env_composer_rejects_duplicate_mapping_keys(tmp_path, mapping):
    composer = runpy.run_path(str(ROOT / 'backend/deploy/compose_runtime_env.py'))
    source = tmp_path / 'duplicate.yaml'
    source.write_text(mapping)
    with pytest.raises(ValueError, match='duplicate YAML mapping key'):
        composer['_load_yaml'](source)
