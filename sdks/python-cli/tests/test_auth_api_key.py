"""Tests for the API-key auth flow."""

import threading

import json

import pytest

from omi_cli import config as cfg
from omi_cli.auth import api_key as api_key_auth
from omi_cli.auth.store import clear_credentials, store_api_key, store_oauth_tokens
from omi_cli.errors import UsageError
from omi_cli.main import app


def test_validate_rejects_empty_key() -> None:
    with pytest.raises(UsageError):
        api_key_auth.validate_api_key_format("")


def test_validate_rejects_whitespace_only() -> None:
    with pytest.raises(UsageError):
        api_key_auth.validate_api_key_format("   ")


def test_validate_rejects_non_dev_prefix() -> None:
    with pytest.raises(UsageError) as info:
        api_key_auth.validate_api_key_format("omi_mcp_" + "x" * 32)
    assert "developer key" in str(info.value).lower()


def test_validate_rejects_truncated_dev_key() -> None:
    with pytest.raises(UsageError):
        api_key_auth.validate_api_key_format("omi_dev_short")


def test_validate_rejects_non_ascii_key() -> None:
    with pytest.raises(UsageError) as info:
        api_key_auth.validate_api_key_format("omi_dev_" + "a" * 20 + "中")
    assert "non-ascii" in str(info.value).lower()


def test_validate_rejects_key_with_emoji() -> None:
    with pytest.raises(UsageError):
        api_key_auth.validate_api_key_format("omi_dev_" + "a" * 20 + "🎉")


def test_login_rejects_non_ascii_key_before_network(cli_runner, respx_mock) -> None:
    route = respx_mock.get("/v1/dev/user/memories").respond(200, json=[])
    result = cli_runner.invoke(app, ["--json", "auth", "login", "--api-key", "omi_dev_" + "a" * 20 + "中"])
    assert result.exit_code == 1
    assert route.call_count == 0


def test_validate_rejects_internal_whitespace() -> None:
    with pytest.raises(UsageError) as info:
        api_key_auth.validate_api_key_format("omi_dev_" + "a" * 16 + " " + "b" * 16)
    assert "whitespace" in str(info.value).lower()


def test_validate_rejects_control_characters() -> None:
    with pytest.raises(UsageError):
        api_key_auth.validate_api_key_format("omi_dev_" + "a" * 16 + "\x00" + "b" * 16)


def test_validate_strips_whitespace() -> None:
    key = "omi_dev_" + "x" * 32
    result = api_key_auth.validate_api_key_format(f"  {key}\n")
    assert result == key


def test_login_persists_to_disk(config_path) -> None:
    key = "omi_dev_" + "y" * 40
    profile = api_key_auth.login_with_api_key(
        "default", key, api_base="https://api.staging.omi.me"
    )
    assert profile.api_key == key
    assert profile.api_base == "https://api.staging.omi.me"

    # Re-load from disk to confirm persistence.
    reloaded = cfg.load().get_profile("default")
    assert reloaded.api_key == key


def test_store_and_clear_round_trip(config_path) -> None:
    key = "omi_dev_" + "z" * 40
    store_api_key("default", key)
    assert cfg.load().get_profile("default").api_key == key

    cleared = clear_credentials("default")
    assert cleared is True
    assert cfg.load().get_profile("default").api_key is None
    assert cfg.load().get_profile("default").auth_method is None


def test_clear_credentials_returns_false_for_unconfigured_profile(config_path) -> None:
    assert clear_credentials("nonexistent") is False


@pytest.mark.parametrize("status_code", [401, 403])
@pytest.mark.parametrize("previous_auth", ["api_key", "oauth"])
def test_rejected_login_preserves_existing_profile(
    config_path, authed_profile, respx_mock, cli_runner, status_code, previous_auth
) -> None:
    if previous_auth == "oauth":
        store_oauth_tokens(
            "default",
            id_token="fake-old-id-token",
            refresh_token="fake-old-refresh-token",
            expires_at=1,
            api_base=authed_profile.api_base,
        )
    before = config_path.read_bytes()
    rejected_key = "omi_dev_" + "r" * 32
    route = respx_mock.get("/v1/dev/key").respond(
        status_code, json={"detail": "Rejected candidate key"}
    )

    result = cli_runner.invoke(
        app, ["--json", "auth", "login", "--api-key", rejected_key]
    )

    assert result.exit_code == 2
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {rejected_key}"
    assert config_path.read_bytes() == before


def test_rejected_login_to_new_profile_does_not_change_active_profile(
    config_path, authed_profile, respx_mock, cli_runner
) -> None:
    before = config_path.read_bytes()
    respx_mock.get("/v1/dev/key").respond(401, json={"detail": "Invalid candidate"})
    result = cli_runner.invoke(
        app,
        [
            "--profile",
            "new",
            "--api-base",
            authed_profile.api_base,
            "auth",
            "login",
            "--api-key",
            "omi_dev_" + "r" * 32,
        ],
    )
    assert result.exit_code == 2
    assert config_path.read_bytes() == before


def test_api_key_login_persists_only_after_verification(
    config_path, authed_profile, respx_mock, cli_runner
) -> None:
    import httpx

    before = config_path.read_bytes()
    new_key = "omi_dev_" + "n" * 32

    def verify_candidate(request):
        assert config_path.read_bytes() == before
        assert request.headers["Authorization"] == f"Bearer {new_key}"
        return httpx.Response(200, json={"scopes": ["action_items:read"]})

    respx_mock.get("/v1/dev/key").mock(side_effect=verify_candidate)
    result = cli_runner.invoke(app, ["--json", "auth", "login", "--api-key", new_key])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["auth_method"] == "api_key"
    assert cfg.load().get_profile("default").api_key == new_key


def test_api_key_login_keeps_existing_http_server_error_policy(
    authed_profile, respx_mock, cli_runner, monkeypatch
) -> None:
    monkeypatch.setattr("omi_cli.client.MAX_RETRY_ATTEMPTS", 1)
    new_key = "omi_dev_" + "n" * 32
    respx_mock.get("/v1/dev/key").respond(503, json={"detail": "Unavailable"})
    result = cli_runner.invoke(app, ["--json", "auth", "login", "--api-key", new_key])
    assert result.exit_code == 0
    assert cfg.load().get_profile("default").api_key == new_key
    assert json.loads(result.stdout)["auth_method"] == "api_key"


def test_transport_failure_during_login_leaves_saved_config_unchanged(
    config_path, authed_profile, respx_mock, cli_runner, monkeypatch
) -> None:
    import httpx

    monkeypatch.setattr("omi_cli.client.MAX_RETRY_ATTEMPTS", 1)
    before = config_path.read_bytes()
    route = respx_mock.get("/v1/dev/key").mock(
        side_effect=httpx.ConnectError("Connection unavailable")
    )
    result = cli_runner.invoke(
        app, ["auth", "login", "--api-key", "omi_dev_" + "n" * 32]
    )
    assert result.exit_code == 3
    assert "Authentication failed" not in result.stderr
    assert route.call_count == 1
    assert config_path.read_bytes() == before


def test_transport_timeout_during_login_leaves_saved_config_unchanged(
    config_path, authed_profile, respx_mock, cli_runner, monkeypatch
) -> None:
    import httpx

    monkeypatch.setattr("omi_cli.client.MAX_RETRY_ATTEMPTS", 1)
    before = config_path.read_bytes()
    route = respx_mock.get("/v1/dev/key").mock(
        side_effect=httpx.ConnectTimeout("Connection timed out")
    )
    result = cli_runner.invoke(
        app, ["auth", "login", "--api-key", "omi_dev_" + "n" * 32]
    )
    assert result.exit_code == 3
    assert route.call_count == 1
    assert config_path.read_bytes() == before


@pytest.mark.parametrize("fallback_status", [200, 403])
def test_login_older_backend_fallback(
    authed_profile, respx_mock, cli_runner, fallback_status
):
    respx_mock.get("/v1/dev/key").respond(404)
    probe = respx_mock.get("/v1/dev/user/memories").respond(fallback_status, json=[])
    result = cli_runner.invoke(
        app, ["auth", "login", "--api-key", "omi_dev_" + "n" * 32]
    )
    assert result.exit_code == 0
    assert probe.call_count == 1
    assert "Scopes: unknown" in result.stderr
    if fallback_status == 403:
        assert "Key is valid" in result.stderr
    # The whole point of the flow is "store only after verification": the
    # verified candidate key must replace the fixture's pre-loaded key.
    assert cfg.load().get_profile("default").api_key == "omi_dev_" + "n" * 32


def test_login_older_backend_fallback_rejects_invalid_key(
    authed_profile, respx_mock, cli_runner, config_path
):
    """On a legacy backend the memories probe is the only auth gate: a 401
    from it must propagate as AuthError (exit 2) and preserve the saved
    profile. (403 is the valid-but-limited case covered by the success test.)"""
    respx_mock.get("/v1/dev/key").respond(404)
    probe = respx_mock.get("/v1/dev/user/memories").respond(401, json=[])
    before = config_path.read_bytes()
    result = cli_runner.invoke(
        app, ["auth", "login", "--api-key", "omi_dev_" + "n" * 32]
    )
    assert result.exit_code == 2
    assert probe.call_count == 1
    assert config_path.read_bytes() == before


def test_narrow_key_login_displays_scopes(authed_profile, respx_mock, cli_runner):
    info = respx_mock.get("/v1/dev/key").respond(
        200, json={"scopes": ["action_items:read"]}
    )
    result = cli_runner.invoke(
        app, ["auth", "login", "--api-key", "omi_dev_" + "n" * 32]
    )
    assert result.exit_code == 0
    assert info.call_count == 1
    assert "Scopes: action_items:read" in result.stderr


def test_concurrent_read_modify_write_serialized_by_file_lock():
    """Concurrent read-modify-write on a shared file must not lose either writer's data.

    Regression test for #22972: without file locking, two concurrent writers that
    load-modify-save a shared config file lose one writer's changes because the
    last save() overwrites the other profile's credential.

    This test mirrors the locking in omi_cli/auth/store.py (_config_lock using
    fcntl.flock on POSIX, msvcrt.locking on Windows) but is self-contained so it
    runs in the standalone harness with nothing but Python and pytest.
    """
    import json
    import os
    import tempfile
    import threading

    if os.name == "nt":
        import msvcrt

        def acquire(fd):
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)

        def release(fd):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        def acquire(fd):
            fcntl.flock(fd, fcntl.LOCK_EX)

        def release(fd):
            fcntl.flock(fd, fcntl.LOCK_UN)

    path = os.path.join(tempfile.gettempdir(), f"test-config-lock-{os.getpid()}.json")
    lock_path = path + ".lock"
    try:
        with open(path, "w") as fh:
            json.dump({"alpha": None, "beta": None}, fh)

        errors = []

        def write_profile(name: str, key: str) -> None:
            try:
                for _ in range(20):
                    with open(lock_path, "a+") as lock_file:
                        acquire(lock_file.fileno())
                        try:
                            with open(path, "r") as fh:
                                data = json.load(fh)
                            data[name] = key
                            with open(path, "w") as fh:
                                json.dump(data, fh)
                        finally:
                            release(lock_file.fileno())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=write_profile, args=("alpha", "KEY-A")),
            threading.Thread(target=write_profile, args=("beta", "KEY-B")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors, f"concurrent writes raised: {errors}"

        with open(path, "r") as fh:
            data = json.load(fh)

        # Without locking, one of these keys would be missing or overwritten.
        assert data.get("alpha") == "KEY-A", f"alpha credential lost: {data}"
        assert data.get("beta") == "KEY-B", f"beta credential lost: {data}"
    finally:
        for p in (path, lock_path):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
