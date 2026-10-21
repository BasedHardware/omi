"""Exercise complete config mutations, including real competing processes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from omi_cli import config as cfg
from omi_cli.auth import store
from omi_cli.main import app

# Both old and new implementations use save(). Pausing immediately before it
# forces the old load/mutate/save callers to overwrite an acknowledged second
# write; it does not fail merely because the new transaction API is absent.
_WRITER = r"""
import json
import sys
import time
from pathlib import Path

from typer.testing import CliRunner
from omi_cli import config as cfg
from omi_cli.auth import store
from omi_cli.main import app

action = json.loads(sys.argv[1])
role = sys.argv[2]
barriers = Path(sys.argv[3])
original_save = cfg.save

def controlled_save(config):
    (barriers / (role + '.saving')).write_text('ready')
    if role == 'first':
        deadline = time.monotonic() + 15
        while not (barriers / 'release').exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('parent did not release the writer')
            time.sleep(0.01)
    original_save(config)

cfg.save = controlled_save
(barriers / (role + '.entered')).write_text('ready')
kind = action[0]
if kind == 'api-key':
    profile_name = action[1] if len(action) > 1 else 'default'
    api_key = action[2] if len(action) > 2 else 'omi_dev_replacement'
    store.store_api_key(profile_name, api_key)
elif kind == 'oauth':
    store.store_oauth_tokens(
        'default', id_token='new-id', refresh_token='new-refresh',
        expires_at=2000000000.0, api_key='omi_dev_oauth',
    )
elif kind == 'refresh':
    store.update_oauth_id_token('default', id_token='refreshed-id', expires_at=2000000001.0)
elif kind == 'clear':
    assert store.clear_credentials('default') is True
elif kind == 'save-failure':
    def refuse_save(config):
        raise OSError('synthetic write failure')
    cfg.save = refuse_save
    try:
        store.store_api_key('uncommitted', 'omi_dev_uncommitted')
    except OSError as exc:
        assert str(exc) == 'synthetic write failure'
    else:
        raise AssertionError('write failure was swallowed')
    cfg.save = controlled_save
    store.store_api_key('recovered', 'omi_dev_recovered')
elif kind == 'cli':
    result = CliRunner().invoke(app, ['--profile', 'default', *action[1:]])
    if result.exit_code:
        raise AssertionError((result.exit_code, result.output, repr(result.exception)))
else:
    raise AssertionError('unknown test action: ' + kind)
(barriers / (role + '.done')).write_text('acknowledged')
"""


def _seed_config(config_path: Path) -> None:
    config = cfg.Config(path=config_path, extra={"future": {"keep": "top-level"}})
    config.set_profile(
        cfg.Profile(
            name="default",
            auth_method="oauth",
            api_key="omi_dev_original",
            id_token="original-id",
            refresh_token="original-refresh",
            id_token_expires_at=1900000000.0,
            api_base="https://original.invalid",
            extra={"future_setting": {"keep": "profile-level"}},
        )
    )
    config.set_profile(cfg.Profile(name="obsolete", api_key="omi_dev_obsolete", auth_method="api_key"))
    cfg.save(config)


def _start_writer(action: list[str], role: str, barriers: Path, config_path: Path) -> subprocess.Popen[str]:
    # Use the same source tree as the parent, including when this regression is
    # deliberately run against the unchanged base. Every child has an explicit
    # temporary config path and only runs local storage/configuration operations.
    source = Path(cfg.__file__).resolve().parent.parent
    env = os.environ.copy()
    env[cfg.ENV_CONFIG_PATH] = str(config_path)
    env["PYTHONPATH"] = str(source)
    for name in (cfg.ENV_API_KEY, cfg.ENV_API_BASE, cfg.ENV_LOCAL_API_URL, cfg.ENV_LOCAL_TOKEN, cfg.ENV_PROFILE):
        env.pop(name, None)
    return subprocess.Popen(
        [sys.executable, "-c", _WRITER, json.dumps(action), role, str(barriers)],
        cwd=source,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_marker(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 10
    while not path.exists():
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            pytest.fail(f"writer exited before {path.name}: {process.returncode}\n{stdout}\n{stderr}")
        if time.monotonic() >= deadline:
            pytest.fail(f"writer did not reach {path.name}")
        time.sleep(0.01)


def _finish_writer(process: subprocess.Popen[str]) -> None:
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, f"writer failed: {stdout}\n{stderr}"


def _stop_writers(processes: list[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def _run_competing_mutations(config_path: Path, first_action: list[str], second_action: list[str]) -> None:
    barriers = config_path.parent / "barriers"
    barriers.mkdir()
    processes: list[subprocess.Popen[str]] = []
    try:
        first = _start_writer(first_action, "first", barriers, config_path)
        processes.append(first)
        _wait_for_marker(barriers / "first.saving", first)
        second = _start_writer(second_action, "second", barriers, config_path)
        processes.append(second)
        _wait_for_marker(barriers / "second.entered", second)

        # On the old implementation the second command acknowledges its write
        # while the first still holds an older snapshot. With a transaction it
        # waits for the first instead. Wait for process completion, not a sleep
        # intended to guess which writer won; cap the legitimate lock wait.
        try:
            second.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        else:
            _finish_writer(second)
            assert (barriers / "second.done").exists()
        (barriers / "release").write_text("release")
        _finish_writer(first)
        _finish_writer(second)
        assert (barriers / "first.done").exists()
        assert (barriers / "second.done").exists()
    finally:
        _stop_writers(processes)


def test_concurrent_logins_to_different_profiles_preserve_both_credentials(config_path: Path) -> None:
    _seed_config(config_path)
    _run_competing_mutations(
        config_path,
        ["api-key", "alpha", "omi_dev_alpha"],
        ["api-key", "beta", "omi_dev_beta"],
    )
    config = cfg.load()
    for name in ("alpha", "beta"):
        assert name in config.profiles, "a successfully stored login profile was lost"
        assert config.profiles[name].api_key == f"omi_dev_{name}"
        assert config.profiles[name].auth_method == "api_key"


@pytest.mark.parametrize(
    "first_action,second_action,expected",
    [
        pytest.param(
            ["api-key"],
            ["cli", "config", "set", "local_token", "parallel-local-token"],
            {"auth_method": "api_key", "api_key": "omi_dev_replacement", "id_token": None, "refresh_token": None},
            id="api-key-and-settings",
        ),
        pytest.param(
            ["oauth"],
            ["cli", "config", "set", "local_token", "parallel-local-token"],
            {"auth_method": "oauth", "id_token": "new-id", "refresh_token": "new-refresh"},
            id="oauth-and-settings",
        ),
        pytest.param(
            ["refresh"],
            ["cli", "config", "set", "local_token", "parallel-local-token"],
            {"id_token": "refreshed-id", "id_token_expires_at": 2000000001.0, "refresh_token": "original-refresh"},
            id="refresh-and-settings",
        ),
        pytest.param(
            ["clear"],
            ["cli", "config", "set", "local_token", "parallel-local-token"],
            {"auth_method": None, "api_key": None, "id_token": None, "refresh_token": None},
            id="logout-and-settings",
        ),
        pytest.param(
            ["cli", "config", "set", "api_base", "https://first.invalid"],
            ["cli", "config", "set", "local_token", "parallel-local-token"],
            {"api_base": "https://first.invalid"},
            id="two-settings-on-one-profile",
        ),
        pytest.param(
            ["cli", "config", "profile", "use", "created-profile"],
            ["cli", "config", "set", "local_token", "parallel-local-token"],
            {},
            id="profile-creation-and-settings",
        ),
        pytest.param(
            ["cli", "config", "profile", "delete", "obsolete", "--yes"],
            ["cli", "config", "set", "local_token", "parallel-local-token"],
            {},
            id="profile-deletion-and-settings",
        ),
        pytest.param(
            ["cli", "local", "configure", "--url", "http://127.0.0.1:47778", "--token", "local-test-token"],
            ["cli", "config", "set", "api_base", "https://parallel.invalid"],
            {"local_api_url": "http://127.0.0.1:47778", "local_token": "local-test-token"},
            id="local-configuration-and-settings",
        ),
    ],
)
def test_concurrent_mutations_preserve_both_acknowledged_writes(
    config_path: Path, first_action: list[str], second_action: list[str], expected: dict[str, object]
) -> None:
    _seed_config(config_path)
    _run_competing_mutations(config_path, first_action, second_action)
    loaded = cfg.load()
    profile = loaded.get_profile("default")
    second_key, second_value = second_action[-2:]
    assert getattr(profile, second_key) == second_value, "an acknowledged concurrent update was lost"
    for name, value in expected.items():
        assert getattr(profile, name) == value
    if "created-profile" in first_action:
        assert "created-profile" in loaded.profiles
        assert loaded.active_profile == "created-profile"
    if "obsolete" in first_action:
        assert "obsolete" not in loaded.profiles
    assert loaded.extra == {"future": {"keep": "top-level"}}
    assert profile.extra == {"future_setting": {"keep": "profile-level"}}


def test_process_exit_releases_transaction_without_committing(config_path: Path) -> None:
    _seed_config(config_path)
    barriers = config_path.parent / "barriers"
    barriers.mkdir()
    processes: list[subprocess.Popen[str]] = []
    try:
        first = _start_writer(["api-key"], "first", barriers, config_path)
        processes.append(first)
        _wait_for_marker(barriers / "first.saving", first)
        first.kill()
        first.communicate(timeout=5)
        second = _start_writer(
            ["cli", "config", "set", "local_token", "after-process-exit"], "second", barriers, config_path
        )
        processes.append(second)
        _finish_writer(second)
    finally:
        _stop_writers(processes)
    profile = cfg.load().get_profile("default")
    assert profile.id_token == "original-id"
    assert profile.api_key == "omi_dev_original"
    assert profile.local_token == "after-process-exit"


def test_save_failure_releases_transaction_for_same_process_retry(config_path: Path) -> None:
    _seed_config(config_path)
    barriers = config_path.parent / "barriers"
    barriers.mkdir()
    child = _start_writer(["save-failure"], "retry", barriers, config_path)
    try:
        _finish_writer(child)
    finally:
        _stop_writers([child])
    config = cfg.load()
    assert "uncommitted" not in config.profiles
    assert config.get_profile("recovered").api_key == "omi_dev_recovered"


@pytest.mark.parametrize("use_cli", [False, True], ids=["auth-store", "config-command"])
def test_mutation_preserves_corrupt_config(config_path: Path, cli_runner, use_cli: bool) -> None:
    corrupt = b'active_profile = ["unfinished"\n'
    config_path.write_bytes(corrupt)
    if use_cli:
        result = cli_runner.invoke(app, ["config", "set", "local_token", "synthetic-token"])
        assert result.exit_code != 0
    else:
        with pytest.raises(cfg.ConfigWriteRefused):
            store.store_api_key("default", "omi_dev_synthetic")
    assert config_path.read_bytes() == corrupt


@pytest.mark.parametrize("existing_file", [False, True], ids=["missing-config", "missing-profile"])
def test_logout_of_missing_profile_does_not_write_config(config_path: Path, existing_file: bool) -> None:
    if existing_file:
        _seed_config(config_path)
        original = config_path.read_bytes()
    assert store.clear_credentials("not-configured") is False
    if existing_file:
        assert config_path.read_bytes() == original
    else:
        assert not config_path.exists()
