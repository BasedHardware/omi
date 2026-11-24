"""A disposable fixture must never reinitialize its caller's repository."""

import os
import subprocess
from pathlib import Path

from scripts.git_test_env import clean_git_env


def test_nested_init_preserves_outer_config(tmp_path: Path, monkeypatch) -> None:
    outer = tmp_path / "outer"
    # Bootstrap independently of the helper under test so a regression cannot
    # reinitialize the real caller before we have installed the throwaway one.
    local_vars = subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).split()
    bootstrap_env = {name: value for name, value in os.environ.items() if name not in [*local_vars, "GIT_NAMESPACE"]}
    subprocess.run(["git", "init", "-q", str(outer)], env=bootstrap_env, check=True)
    config = outer / ".git/config"
    before = config.read_bytes()
    monkeypatch.setenv("GIT_DIR", str(outer / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(outer))
    monkeypatch.setenv("GIT_COMMON_DIR", str(outer / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(outer / ".git/index"))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(outer / ".git/objects"))
    monkeypatch.setenv("GIT_NAMESPACE", "outer")
    monkeypatch.setenv("GIT_PREFIX", "outer/")
    monkeypatch.setenv("FIXTURE_ORDINARY_SETTING", "keep")

    env = clean_git_env()
    local_vars = subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True).split()
    assert not set([*local_vars, "GIT_NAMESPACE"]).intersection(env)
    assert env["FIXTURE_ORDINARY_SETTING"] == "keep"
    # The helper must not mutate the caller's environment.
    assert os.environ["GIT_DIR"] == str(outer / ".git")
    nested = tmp_path / "nested"
    subprocess.run(["git", "init", "-q", str(nested)], env=env, check=True)
    assert (nested / ".git").is_dir()
    assert config.read_bytes() == before
