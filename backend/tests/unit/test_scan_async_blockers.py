import importlib.util
import textwrap
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCANNER_PATH = BACKEND_DIR / "scripts" / "scan_async_blockers.py"


@pytest.fixture
def scanner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scan_async_blockers_interprocedural_test", SCANNER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scan_source(scanner: ModuleType, tmp_path: Path, source: str):
    source_path = tmp_path / "sample.py"
    source_path.write_text(textwrap.dedent(source), encoding="utf-8")
    return source_path, scanner.scan_dirs([str(tmp_path)])


def _scan_agent_proxy_source(scanner: ModuleType, tmp_path: Path, source: str):
    service_dir = tmp_path / "backend" / "agent-proxy"
    service_dir.mkdir(parents=True)
    source_path = service_dir / "main.py"
    source_path.write_text(textwrap.dedent(source), encoding="utf-8")
    return source_path, scanner.scan_dirs([str(service_dir)])


def test_direct_local_sync_wrapper_is_reported_at_async_call_site(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def read_payload():
            return open("payload.json").read()

        @router.get("/payload")
        async def endpoint():
            await asyncio.sleep(0)
            return read_payload()
        """,
    )

    assert len(results["medium_file_io"]) == 1
    call = results["medium_file_io"][0]["calls"][0]
    assert call["call"] == "read_payload() -> open()"
    assert call["via"] == ["read_payload"]
    assert call["line"] != call["sink_line"]


def test_transitive_local_sync_wrappers_preserve_full_blocking_path(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio
        import requests

        def request_remote():
            return requests.get("https://example.test")

        def load_remote():
            return request_remote()

        @router.get("/remote")
        async def endpoint():
            await asyncio.sleep(0)
            return load_remote()
        """,
    )

    assert len(results["high_network_io"]) == 1
    call = results["high_network_io"][0]["calls"][0]
    assert call["call"] == "load_remote() -> request_remote() -> requests.get()"
    assert call["via"] == ["load_remote", "request_remote"]
    assert len(call["chain_lines"]) == 3


def test_safe_local_sync_helper_does_not_create_a_finding(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def normalize(value):
            return value.strip().lower()

        @router.get("/normalize")
        async def endpoint():
            await asyncio.sleep(0)
            return normalize(" Safe ")
        """,
    )

    assert results["high_network_io"] == []
    assert results["medium_file_io"] == []
    assert results["time_sleep"] == []
    assert results["mixed_await_sync_db"] == []
    assert results["async_helpers_with_blocking"] == []


def test_recursive_helper_cycle_reaches_blocking_sink_without_looping(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def first(depth):
            if depth:
                return second(depth - 1)
            return open("payload.json").read()

        def second(depth):
            return first(depth - 1) if depth else "done"

        @router.get("/recursive")
        async def endpoint():
            await asyncio.sleep(0)
            return second(2)
        """,
    )

    call = results["medium_file_io"][0]["calls"][0]
    assert call["call"] == "second() -> first() -> open()"
    assert call["via"] == ["second", "first"]


def test_safe_recursive_helper_cycle_has_no_effect(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def first(depth):
            return second(depth - 1) if depth else "done"

        def second(depth):
            return first(depth - 1) if depth else "done"

        @router.get("/recursive")
        async def endpoint():
            await asyncio.sleep(0)
            return first(2)
        """,
    )

    assert results["high_network_io"] == []
    assert results["medium_file_io"] == []
    assert results["async_helpers_with_blocking"] == []


def test_local_sync_helper_passed_to_run_blocking_is_safe(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        def read_payload():
            return open("payload.json").read()

        async def helper():
            return await run_blocking(storage_executor, read_payload)
        """,
    )

    assert results["async_helpers_with_blocking"] == []


def test_direct_credentials_refresh_is_reported_as_sync_network_io(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        async def refresh_token():
            creds.refresh(request)
        """,
    )

    finding = results["async_helpers_with_blocking"][0]
    assert finding["function"] == "refresh_token"
    assert finding["network_io"] == [{"line": 3, "call": "creds.refresh() [sync HTTP]"}]


def test_agent_proxy_transitive_credentials_refresh_is_selected(scanner, tmp_path):
    source_path, results = _scan_agent_proxy_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def _refresh_credentials():
            creds.refresh(request)

        def _get_gce_access_token():
            _refresh_credentials()
            return creds.token

        async def _check_gce_status():
            await asyncio.sleep(0)
            return _get_gce_access_token()
        """,
    )

    finding = results["async_helpers_with_blocking"][0]
    call = finding["network_io"][0]
    assert finding["file"] == str(source_path)
    assert call["call"] == "_get_gce_access_token() -> _refresh_credentials() -> creds.refresh() [sync HTTP]"
    assert call["via"] == ["_get_gce_access_token", "_refresh_credentials"]


def test_agent_proxy_credentials_refresh_passed_to_run_blocking_is_safe(scanner, tmp_path):
    _source_path, results = _scan_agent_proxy_source(
        scanner,
        tmp_path,
        """
        def _get_gce_access_token():
            creds.refresh(request)
            return creds.token

        async def _check_gce_status():
            return await run_blocking(critical_executor, _get_gce_access_token)
        """,
    )

    assert results["high_network_io"] == []
    assert results["async_helpers_with_blocking"] == []


def test_firebase_auth_and_firestore_helpers_are_detected_transitively(scanner, tmp_path):
    _source_path, results = _scan_agent_proxy_source(
        scanner,
        tmp_path,
        """
        from firebase_admin import auth, firestore

        def _get_firestore_db():
            return firestore.client()

        def _get_user_context():
            return _get_firestore_db().collection("users")

        async def websocket_handler(token):
            auth.verify_id_token(token)
            return _get_user_context()
        """,
    )

    finding = results["async_helpers_with_blocking"][0]
    assert {call["call"] for call in finding["network_io"]} == {"verify_id_token() [sync HTTP]"}
    assert {call["call"] for call in finding["db_calls"]} == {
        "_get_user_context() -> _get_firestore_db() -> firestore.client"
    }


def test_firebase_auth_and_firestore_helpers_are_safe_on_owned_executors(scanner, tmp_path):
    _source_path, results = _scan_agent_proxy_source(
        scanner,
        tmp_path,
        """
        from firebase_admin import auth, firestore

        def _verify(token):
            return auth.verify_id_token(token)

        def _get_firestore_db():
            return firestore.client()

        def _get_user_context():
            return _get_firestore_db().collection("users")

        async def websocket_handler(token):
            decoded = await run_blocking(critical_executor, _verify, token)
            context = await run_blocking(db_executor, _get_user_context)
            return decoded, context
        """,
    )

    assert results["high_network_io"] == []
    assert results["async_helpers_with_blocking"] == []


def test_prerecorded_stt_and_storage_lifecycle_calls_are_network_io(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        from utils.other.storage import (
            get_syncing_file_temporal_signed_url,
            schedule_syncing_temporal_file_deletion,
        )
        from utils.stt.pre_recorded import prerecorded, prerecorded_from_bytes

        async def stream_voice_message():
            await checkpoint()
            url = get_syncing_file_temporal_signed_url("audio.wav")
            schedule_syncing_temporal_file_deletion("audio.wav")
            prerecorded(url)
            prerecorded_from_bytes(b"audio")
        """,
    )

    calls = results["async_helpers_with_blocking"][0]["network_io"]
    assert {call["call"] for call in calls} == {
        "get_syncing_file_temporal_signed_url",
        "schedule_syncing_temporal_file_deletion",
        "prerecorded() [sync STT]",
        "prerecorded_from_bytes() [sync STT]",
    }


def test_prerecorded_stt_and_storage_helpers_are_safe_on_managed_executors(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        from utils.other.storage import (
            get_syncing_file_temporal_signed_url,
            schedule_syncing_temporal_file_deletion,
        )
        from utils.stt.pre_recorded import prerecorded

        def _prepare_url(path):
            url = get_syncing_file_temporal_signed_url(path)
            schedule_syncing_temporal_file_deletion(path)
            return url

        def _transcribe(url):
            return prerecorded(url)

        async def stream_voice_message():
            url = await run_blocking(storage_executor, _prepare_url, "audio.wav")
            return await run_blocking(sync_executor, _transcribe, url)
        """,
    )

    assert results["high_network_io"] == []
    assert results["async_helpers_with_blocking"] == []


def test_sync_app_and_subscription_imports_are_db_blockers_with_aliases(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        from utils.apps import get_available_apps as load_apps
        from utils.subscription import is_trial_paywalled

        async def realtime_coordinator(uid, source):
            await checkpoint()
            if is_trial_paywalled(uid, source):
                return []
            return load_apps(uid)
        """,
    )

    finding = results["async_helpers_with_blocking"][0]
    assert {call["call"] for call in finding["db_calls"]} == {"is_trial_paywalled", "load_apps"}


def test_sync_notification_import_is_detected_through_local_helper(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        from utils.notifications import send_notification

        def send_app_notification(uid, message):
            send_notification(uid, "App says", message)

        async def realtime_coordinator(uid):
            await checkpoint()
            send_app_notification(uid, "hello")
        """,
    )

    finding = results["async_helpers_with_blocking"][0]
    call = finding["network_io"][0]
    assert call["call"] == "send_app_notification() -> send_notification() [sync notification]"
    assert call["via"] == ["send_app_notification"]


def test_app_boundaries_are_clean_on_owned_executor_and_async_notification_seam(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        from utils.apps import get_available_apps
        from utils.subscription import is_trial_paywalled
        from utils.notifications import send_notification_async

        async def realtime_coordinator(uid, source):
            if await run_blocking(db_executor, is_trial_paywalled, uid, source):
                return []
            apps = await run_blocking(db_executor, get_available_apps, uid)
            await send_notification_async(uid, "App says", "hello")
            return apps
        """,
    )

    assert results["high_network_io"] == []
    assert results["mixed_await_sync_db"] == []
    assert results["async_helpers_with_blocking"] == []


def test_asyncio_to_thread_is_reported_as_unmanaged_offload(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        async def legacy_helper():
            return await asyncio.to_thread(blocking_call)
        """,
    )

    assert results["unmanaged_thread_offload"] == [
        {
            "file": str(_source_path),
            "line": 4,
            "end_line": 5,
            "function": "legacy_helper",
            "calls": [{"line": 5, "call": "asyncio.to_thread() [unmanaged executor]"}],
        }
    ]


@pytest.mark.parametrize(
    ("import_statement", "offload_call"),
    [
        ("import asyncio as aio", "aio.to_thread(blocking_call)"),
        ("from asyncio import to_thread", "to_thread(blocking_call)"),
        ("from asyncio import to_thread as offload", "offload(blocking_call)"),
    ],
)
def test_asyncio_to_thread_import_aliases_are_reported_as_unmanaged_offloads(
    scanner,
    tmp_path,
    import_statement,
    offload_call,
):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        f"""
        {import_statement}

        async def legacy_helper():
            return await {offload_call}
        """,
    )

    assert results["unmanaged_thread_offload"] == [
        {
            "file": str(_source_path),
            "line": 4,
            "end_line": 5,
            "function": "legacy_helper",
            "calls": [{"line": 5, "call": "asyncio.to_thread() [unmanaged executor]"}],
        }
    ]


def test_unrelated_to_thread_import_is_not_reported_as_an_asyncio_offload(scanner, tmp_path):
    _source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        from workers import to_thread

        async def helper():
            return await to_thread(blocking_call)
        """,
    )

    assert results["unmanaged_thread_offload"] == []


def test_explicit_python_file_path_is_scanned(scanner, tmp_path):
    source_path = tmp_path / "dependencies.py"
    source_path.write_text(
        textwrap.dedent("""
            async def auth_dependency():
                creds.refresh(request)
            """),
        encoding="utf-8",
    )

    results = scanner.scan_dirs([str(source_path)])

    assert results["summary"]["files_scanned"] == 1
    assert results["high_network_io"][0]["endpoint"] == "auth_dependency"


def test_dependency_module_async_without_await_is_structural_finding(scanner, tmp_path):
    source_path = tmp_path / "dependencies.py"
    source_path.write_text(
        textwrap.dedent("""
            async def pure_dependency():
                return "uid"
            """),
        encoding="utf-8",
    )

    results = scanner.scan_dirs([str(source_path)])

    assert results["no_await_should_be_def"][0]["endpoint"] == "pure_dependency"


def test_changed_scope_preserves_hyphenated_agent_proxy_path(scanner, monkeypatch):
    diff = """\
diff --git a/backend/agent-proxy/main.py b/backend/agent-proxy/main.py
--- a/backend/agent-proxy/main.py
+++ b/backend/agent-proxy/main.py
@@ -8,0 +9 @@ async def _check_gce_status():
+    creds.refresh(request)
"""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(stdout=diff)

    monkeypatch.setattr(scanner.subprocess, "run", fake_run)

    scope = scanner.changed_scope("origin/main", ["backend/agent-proxy"])

    assert captured["cmd"][-2:] == ["--", "backend/agent-proxy"]
    assert scope["ranges"] == {"backend/agent-proxy/main.py": [(9, 9)]}


def test_diff_scope_includes_changed_transitive_helper_lines(scanner, tmp_path):
    source_path, results = _scan_source(
        scanner,
        tmp_path,
        """
        import asyncio

        def read_payload():
            return open("payload.json").read()

        @router.get("/payload")
        async def endpoint():
            await asyncio.sleep(0)
            return read_payload()
        """,
    )
    finding = results["medium_file_io"][0]
    sink_line = finding["calls"][0]["sink_line"]
    scope = {
        "ranges": {str(source_path): [(sink_line, sink_line)]},
        "import_changed_files": set(),
    }

    assert scanner.finding_in_changed_scope(finding, scope)
