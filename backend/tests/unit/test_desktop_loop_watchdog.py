import inspect
import logging
import threading
import time

from fastapi.testclient import TestClient

import desktop_backend
from utils.desktop_loop_watchdog import DesktopLoopWatchdog, _stack_path


def test_stack_path_is_capped_at_40_locations():
    def recurse(depth):
        if depth == 0:
            return _stack_path(inspect.currentframe())
        return recurse(depth - 1)

    assert recurse(50).count("@") == 40


def test_stall_warning_is_once_per_stall_and_contains_only_stack_locations(caplog):
    watchdog = DesktopLoopWatchdog()
    watchdog._loop_thread_id = threading.get_ident()
    watchdog.last_heartbeat = 100
    secret_payload = "private-user-payload"
    watchdog.request_started()
    with caplog.at_level(logging.WARNING):
        watchdog.check(now=110)
        watchdog.check(now=131)
        watchdog.check(now=101)
        watchdog.check(now=111)
    records = [record for record in caplog.records if "desktop_event_loop_stall" in record.message]
    assert len(records) == 2
    assert "delay_ms=10000" in records[0].message
    assert "db_active=" in records[0].message
    assert "db_queue=" in records[0].message
    assert "in_flight=1" in records[0].message
    assert "test_stall_warning_is_once_per_stall_and_contains_only_stack_locations@" in records[0].message
    assert secret_payload not in records[0].message
    assert len(records[0].message) < 5000
    watchdog.request_finished()
    assert watchdog.in_flight == 0


def test_liveness_reports_stale_heartbeat_and_kill_switch(monkeypatch):
    monkeypatch.delenv("DESKTOP_LOOP_WATCHDOG_ENABLED", raising=False)
    app = desktop_backend._build_app()
    watchdog = app.state.loop_watchdog
    watchdog.last_heartbeat = time.monotonic() - 31
    assert TestClient(app).get("/healthz/live").status_code == 503
    watchdog.last_heartbeat = time.monotonic()
    assert TestClient(app).get("/healthz/live").status_code == 200

    monkeypatch.setenv("DESKTOP_LOOP_WATCHDOG_ENABLED", "false")
    disabled_app = desktop_backend._build_app()
    disabled_app.state.loop_watchdog.last_heartbeat = time.monotonic() - 31
    assert TestClient(disabled_app).get("/healthz/live").status_code == 200
