"""Scenario commands' host root: the env var, else the lab host's volume when present, else a user cache."""

from pathlib import Path

from testing.pipeline_lab.scenario import paths
from testing.pipeline_lab.stack import config


def test_env_var_wins(tmp_path):
    target = tmp_path / 'not-yet'
    assert paths.scenario_lab_root({config.LAB_ROOT_ENV: str(target)}) == target


def test_lab_host_volume_when_it_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DEFAULT_LAB_ROOT', str(tmp_path))
    assert paths.scenario_lab_root({}) == tmp_path


def test_user_cache_when_the_lab_volume_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DEFAULT_LAB_ROOT', str(tmp_path / 'missing-volume'))
    assert paths.scenario_lab_root({'XDG_CACHE_HOME': str(tmp_path / 'cache')}) == tmp_path / 'cache' / 'pipeline-lab'
    assert paths.scenario_lab_root({}) == Path.home() / '.cache' / 'pipeline-lab'


def test_day_replay_default_is_unchanged():
    assert config.DEFAULT_LAB_ROOT == '/Volumes/Ephemeral/pipeline-lab'
