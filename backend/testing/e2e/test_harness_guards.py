"""
Harness self-tests.

These tests verify that the e2e harness guardrails fail closed before any
scenario depends on them.
"""

import os
import socket
import subprocess
import sys
import time

import dotenv
import pytest

from conftest import HERMETIC_SHUTDOWN_BUDGET_SECONDS, E2E_DIR, _set_e2e_env


def test_dotenv_loading_is_disabled(tmp_path):
    """Local .env files must not rehydrate real credentials during e2e runs."""
    env_file = tmp_path / ".env"
    env_file.write_text("SERVICE_ACCOUNT_JSON=real-looking-secret\nPINECONE_API_KEY=real-looking-key\n")

    assert dotenv.load_dotenv(env_file, override=True) is False
    assert os.environ.get("SERVICE_ACCOUNT_JSON") is None
    assert os.environ.get("PINECONE_API_KEY") is None


def test_e2e_environment_clears_firebase_auth_credential_path(monkeypatch):
    monkeypatch.setenv("FIREBASE_AUTH_CREDENTIALS_PATH", "/tmp/inherited-firebase-auth.json")

    _set_e2e_env()

    assert "FIREBASE_AUTH_CREDENTIALS_PATH" not in os.environ


def test_network_guard_blocks_external_dns_lookup():
    """External DNS resolution should fail before a client can connect."""
    with pytest.raises(AssertionError, match="blocked DNS lookup"):
        socket.getaddrinfo("example.com", 443)


def test_network_guard_resolves_reserved_test_tld_hermetically():
    """RFC 6761 reserves .test so it can never resolve on real DNS; the guard
    answers it deterministically (no packet leaves the process) so config-time
    validators — e.g. the developer-webhook SSRF check — stay exercisable."""
    expected = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]
    assert socket.getaddrinfo("webhook.test", None) == expected
    assert socket.getaddrinfo(b"webhook.test", None) == expected


def test_network_guard_test_tld_answer_satisfies_public_url_validation():
    """The synthesized .test answer must pass the webhook SSRF validator's
    public-address class, or the route under test 400s before its logic runs."""
    from utils.http_client import assert_public_http_url

    assert assert_public_http_url("https://webhook.test/realtime") == "8.8.8.8"


def test_network_guard_still_blocks_connect_after_test_tld_resolution():
    """A synthesized .test resolution must not open a real-socket path: connecting
    to the synthesized public IP still fails closed."""
    socket.getaddrinfo("webhook.test", None)
    with pytest.raises(AssertionError, match="blocked outbound network connection"):
        socket.create_connection(("8.8.8.8", 443), timeout=0.1)


def test_network_guard_blocks_external_create_connection():
    """External TCP connections should fail closed."""
    with pytest.raises(AssertionError, match="blocked outbound network connection"):
        socket.create_connection(("93.184.216.34", 80), timeout=0.1)


def test_network_guard_blocks_sendto_two_arg_form():
    """UDP sendto(data, address) should fail closed for non-local hosts."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(AssertionError, match="blocked outbound network connection"):
            sock.sendto(b"payload", ("93.184.216.34", 80))
    finally:
        sock.close()


def test_network_guard_blocks_sendto_three_arg_form():
    """UDP sendto(data, flags, address) should fail closed, not TypeError."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(AssertionError, match="blocked outbound network connection"):
            sock.sendto(b"payload", 0, ("93.184.216.34", 80))
    finally:
        sock.close()


def test_backend_storage_client_is_fake_after_app_import(client):
    """The backend storage module should hold the fake GCS client, not google's real client."""
    from fakes.storage import FakeStorageClient
    import utils.other.storage as storage_helpers

    assert isinstance(storage_helpers._get_storage_client(), FakeStorageClient)


def test_backend_database_globals_are_fake_after_app_import(client, fake_firestore, fake_redis):
    """Already-imported backend modules must not retain real Firestore/Redis clients."""

    import database._client as db_client
    import database.redis_db as redis_db
    import database.webhook_health as webhook_health
    import utils.fair_use as fair_use

    assert db_client.db is fake_firestore
    assert redis_db.r is fake_redis
    assert webhook_health.r is fake_redis
    assert fair_use.redis_client is fake_redis


def test_backend_registered_redis_scripts_are_rebound_to_fake(client, fake_redis):
    """Lua-backed boundaries must not retain the localhost client from import."""
    import database.redis_db as redis_db

    redis_db._RATE_LIMIT_LUA(keys=['e2e:script-client-guard'], args=[60])

    assert fake_redis.get('e2e:script-client-guard') == b'1'


def test_firestore_root_delete_preserves_children_without_recreating_root(fake_firestore):
    user = fake_firestore.collection('users').document('root-delete-harness-check')
    child = user.collection('conversations').document('kept')
    user.set({'id': user.id})
    child.set({'status': 'completed'})
    user.delete()
    assert not user.get().exists
    assert child.get().to_dict() == {'status': 'completed'}
    user.delete()  # Repeat deletion still preserves children without a root.
    assert not user.get().exists
    assert child.get().to_dict() == {'status': 'completed'}
    child.delete()
    user.delete()


def test_process_exit_is_prompt_after_hermetic_shutdown(tmp_path):
    """A process that used the hermetic pub/sub machinery must exit promptly.

    The CI wrapper (E2E_PYTEST_TIMEOUT) budgets python startup + suite +
    interpreter shutdown together; green run 40513231489 (job 122220618067,
    PR #23807) spent ~3s exiting after its report and was SIGTERMed at 120s.
    Replay the harness's session-end shutdown recipe in a child interpreter
    and bound the wall time from "shutdown done" to process exit, so a
    reintroduced slow atexit hook or leaked non-daemon thread fails here
    instead of silently eating the wrapper budget.
    """
    child = tmp_path / "child_shutdown_probe.py"
    child.write_text(
        "import faulthandler, sys, time\n"
        f"sys.path.insert(0, {str(E2E_DIR)!r})\n"
        "import conftest  # hermetic env + socket guard, no pytest involved\n"
        "from fakes.redis import setup_fake_redis, patch_redis_client\n"
        "setup_fake_redis()\n"
        "patch_redis_client()\n"
        "import database.cache as cache\n"
        "cache.get_memory_cache()  # starts the Redis pub/sub subscriber thread\n"
        "import utils.executors as executors\n"
        "executors.db_executor.submit(int).result()  # spawn one idle pool worker\n"
        "from conftest import _teardown_hermetic_process_state\n"
        f"elapsed = _teardown_hermetic_process_state()  # asserts its own {HERMETIC_SHUTDOWN_BUDGET_SECONDS}s budget\n"
        "print(f'TEARDOWN {time.time():.3f} {elapsed:.3f}', flush=True)\n"
        # The enforced bound lives here, on the child's monotonic clock: a
        # slower-than-8s interpreter exit dumps all thread stacks and aborts
        # the child, immune to runner wall-clock jumps between the processes.
        "faulthandler.dump_traceback_later(8.0, exit=True)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-I", str(child)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # communicate() bounds the child's whole lifetime (imports, teardown,
        # interpreter exit) and waits for EOF on both pipes, so a hung child
        # fails here with the bound instead of blocking the outer suite.
        stdout, stderr = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        pytest.fail("child did not exit within 60s of the hermetic shutdown probe")
    teardown_lines = [line.strip() for line in stdout.splitlines() if line.startswith("TEARDOWN")]
    assert teardown_lines, f"child never reported teardown completion:\n{stderr[-2000:]}"
    # returncode 0 proves the child exited before its 8s faulthandler abort
    # (the abort dumps all thread stacks into stderr for the failure message).
    assert proc.returncode == 0, (
        "child failed after hermetic shutdown (faulthandler abort means interpreter "
        f"exit exceeded 8s):\n{stderr[-2000:]}"
    )
    # Informational only (wall clock can jump between processes); the bound
    # itself is enforced by the child's faulthandler timer above.
    teardown_epoch = float(teardown_lines[-1].split()[1])
    exit_seconds = time.time() - teardown_epoch
