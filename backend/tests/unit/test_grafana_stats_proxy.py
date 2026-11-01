"""Keyless stats proxy capability boundary and token/cache lifecycle."""

import base64
import io
import json
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

import pytest
from charts.monitoring.grafana.stats_proxy import (
    AUDIENCE,
    METADATA,
    MINT,
    READER,
    Handler,
    Server,
    StatsProxy,
    MAX_STALE,
    REFRESHING_TTL,
    SERIES_NAMES,
    allowed_path,
)


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/api/omi/users",
        "/api/omi/stats/../users",
        "/api/omi/stats/%2e%2e/users",
        "https://evil/api/omi/stats/wall",
        "//evil/api/omi/stats/wall",
        "/api/omi/stats/wall#foo",
        "/api/omi/stats/wall\nInjected: yes",
        "/api/omi/stats/wall?nonce=1",
        "/api/omi/stats/walls",
        "/api/omi/stats/wall/",
        "/API/OMI/STATS/WALL",
        "/api/omi/stats/wall ",
        "/api/omi/stats/wall/series/",
        "/api/omi/stats/wall/series/unknown",
        "/api/omi/stats/wall/series/growth/",
        "/api/omi/stats/wall/series/growth?x=1",
        "/api/omi/stats/wall/series/../../users",
    ],
)
def test_only_literal_stats_paths(path):
    assert not allowed_path(path)


def test_the_wall_route_and_named_series_are_the_only_admitted_paths():
    assert allowed_path("/api/omi/stats/wall")
    for name in ("headline", "growth", "activation", "retention", "revenue", "health"):
        assert allowed_path(f"/api/omi/stats/wall/series/{name}")


def test_series_names_match_the_admin_route():
    source = (Path(__file__).resolve().parents[3] / "web/admin/lib/wall-series.ts").read_text()
    block = source.split("export const SERIES_NAMES = [", 1)[1].split("]", 1)[0]
    names = tuple(part.strip().strip('"') for part in block.split(",") if part.strip())
    assert names == SERIES_NAMES


def token(exp):
    payload = (
        base64.urlsafe_b64encode(json.dumps({"aud": AUDIENCE, "email": READER, "exp": exp}).encode())
        .decode()
        .rstrip("=")
    )
    return "header." + payload + ".signature"


class Transport:
    def __init__(self, now):
        self.now, self.calls, self.fail_once = now, [], False

    def open(self, request, timeout):
        self.calls.append(request)
        if request.full_url == METADATA:
            assert request.get_header("Metadata-flavor") == "Google"
            return io.BytesIO(b'{"access_token":"access-secret"}')
        if request.full_url == MINT:
            assert request.get_header("Authorization") == "Bearer access-secret"
            assert json.loads(request.data) == {"audience": AUDIENCE, "includeEmail": True}
            return io.BytesIO(json.dumps({"token": token(self.now[0] + 3600)}).encode())
        assert request.full_url.startswith("https://admin.omi.me/api/omi/stats/")
        assert set(request.headers) == {"Authorization", "Accept"}
        if self.fail_once:
            self.fail_once = False
            raise HTTPError(request.full_url, 401, "auth", {}, io.BytesIO())
        return io.BytesIO(b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')


def inline(work):
    work()


def test_cache_coalesces_panel_requests_and_refreshes_tokens_early():
    now = [10000]
    transport = Transport(now)
    proxy = StatsProxy(transport, lambda: now[0], spawn=inline)
    assert proxy.fetch("/api/omi/stats/wall") == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')
    for _ in range(24):
        assert proxy.fetch("/api/omi/stats/wall")[0] == 200
    assert len(transport.calls) == 3
    now[0] += 900
    proxy.fetch("/api/omi/stats/wall")
    assert len(transport.calls) == 4  # still-valid ID token reused
    now[0] += 2500  # within five minutes of expiration
    proxy.fetch("/api/omi/stats/wall")
    assert len(transport.calls) == 7


def test_401_discards_identity_and_retries_once():
    now = [10000]
    transport = Transport(now)
    transport.fail_once = True
    proxy = StatsProxy(transport, lambda: now[0])
    assert proxy.fetch("/api/omi/stats/wall")[0] == 200
    assert len(transport.calls) == 6


def test_failed_refresh_serves_last_good_until_max_stale_and_never_follows_redirect():
    now = [10000]
    transport = Transport(now)
    proxy = StatsProxy(transport, lambda: now[0], spawn=inline)
    proxy.fetch("/api/omi/stats/wall")
    now[0] += 900
    attempts = []

    def fail(*args, **kwargs):
        attempts.append(1)
        raise HTTPError("https://admin.omi.me/api/omi/stats/wall", 302, "redirect", {}, io.BytesIO())

    transport.open = fail
    # The board keeps the last good body; the admin body carries its own freshness.
    assert proxy.fetch("/api/omi/stats/wall") == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')
    assert len(attempts) == 1
    assert proxy.fetch("/api/omi/stats/wall") == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')
    assert len(attempts) == 1  # the failure cools down before the next refresh
    now[0] += MAX_STALE
    assert proxy.fetch("/api/omi/stats/wall")[0] == 502  # never older than MAX_STALE
    # A path that never answered has nothing to serve.
    assert proxy.fetch("/api/omi/stats/wall/series/health")[0] == 502


def test_http_rejects_mutations_and_does_not_forward_headers(monkeypatch):
    now = [10000]
    transport = Transport(now)
    monkeypatch.setattr(Handler, "proxy", StatsProxy(transport, lambda: now[0]))
    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for method, path, expected in [
            ("POST", "/api/omi/stats/wall", 501),
            ("GET", "/api/omi/users", 404),
            ("GET", "/api/omi/stats/wall", 200),
        ]:
            connection = HTTPConnection(*server.server_address, timeout=3)
            connection.request(
                method,
                path,
                headers={"Cookie": "private", "Authorization": "Bearer attacker", "X-Forwarded-Host": "evil"},
            )
            response = connection.getresponse()
            assert response.status == expected
            response.read()
            assert response.getheader("Set-Cookie") is None
            connection.close()
        assert len(transport.calls) == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_timeout_is_shared_by_all_waiters_then_retried_after_backoff():
    now = [10000]
    proxy = StatsProxy(clock=lambda: now[0])
    entered, release = threading.Event(), threading.Event()
    attempts = []

    def timeout(*args, **kwargs):
        attempts.append(1)
        entered.set()
        assert release.wait(2)
        raise TimeoutError("synthetic upstream timeout")

    proxy.identity_token = lambda: "synthetic"
    proxy.request = timeout
    with ThreadPoolExecutor(max_workers=8) as pool:
        waiting = [pool.submit(proxy.fetch, "/api/omi/stats/wall") for _ in range(8)]
        assert entered.wait(2)
        release.set()
        assert all(future.result(timeout=2)[0] == 502 for future in waiting)
    assert len(attempts) == 1
    now[0] += 5
    assert proxy.fetch("/api/omi/stats/wall")[0] == 502
    assert len(attempts) == 2


@pytest.mark.parametrize("active_org,role", [(1, "Viewer"), (2, "Editor")])
def test_viewer_acceptance_rejects_wrong_scope_before_permission_reads(active_org, role):
    from charts.monitoring.grafana.verify_business import verify_viewer

    viewer_calls = []

    class WrongOrg:
        def call(self, method, path):
            viewer_calls.append(path)
            if path != "/api/user":
                raise RuntimeError("Viewer permission read before scope admission")
            return {"orgId": active_org, "isGrafanaAdmin": False, "login": "sa-negative"}

    class Admin:
        def call(self, method, path):
            if path != "/api/serviceaccounts/search?perpage=1000":
                raise RuntimeError("Unexpected Admin API request")
            return {"serviceAccounts": [{"orgId": 2, "login": "sa-negative", "role": role}]}

    with pytest.raises(AssertionError):
        verify_viewer(WrongOrg(), 2, Admin())
    assert viewer_calls == ["/api/user"]


def test_viewer_acceptance_requires_same_org_viewer_and_both_denials():
    from charts.monitoring.grafana.verify_business import verify_viewer

    class Viewer:
        def __init__(self):
            self.denied = []

        def call(self, method, path):
            if path == "/api/user":
                return {"orgId": 2, "isGrafanaAdmin": False, "login": "sa-negative", "id": 0}
            self.denied.append(path)
            raise HTTPError("https://fixture" + path, 403, "denied", {}, io.BytesIO())

    class Admin:
        def call(self, method, path):
            assert path == "/api/serviceaccounts/search?perpage=1000"
            return {"serviceAccounts": [{"orgId": 2, "login": "sa-negative", "role": "Viewer"}]}

    viewer = Viewer()
    verify_viewer(viewer, 2, Admin())
    assert viewer.denied == ["/api/folders/business", "/api/dashboards/uid/omi-tv-v2"]


def test_http_cold_wall_burst_queues_every_panel_and_coalesces_upstream(monkeypatch):
    now = [10000]
    proxy = StatsProxy(clock=lambda: now[0])
    entered, release, queued = threading.Event(), threading.Event(), threading.Event()
    upstream_calls = []

    def upstream(*args, **kwargs):
        upstream_calls.append(1)
        entered.set()
        assert release.wait(10)
        return b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}'

    class BurstServer(Server):
        admitted = 0

        def process_request(self, request, address):
            self.admitted += 1
            if self.admitted == 9:
                queued.set()
            super().process_request(request, address)

    proxy.identity_token = lambda: "synthetic"
    proxy.request = upstream
    monkeypatch.setattr(Handler, "proxy", proxy)
    server = BurstServer(("127.0.0.1", 0), Handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    start = threading.Barrier(24)

    def panel():
        start.wait(timeout=10)
        connection = HTTPConnection(*server.server_address, timeout=10)
        try:
            connection.request("GET", "/api/omi/stats/wall")
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=24) as pool:
            panels = [pool.submit(panel) for _ in range(24)]
            try:
                assert entered.wait(10)
                assert queued.wait(10)
            finally:
                release.set()
            assert all(
                result.result(timeout=10) == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')
                for result in panels
            )
        assert len(upstream_calls) == 1
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        serving.join(timeout=10)


def test_refreshing_body_is_cached_briefly_then_refetched_in_the_background():
    now = [10000]
    transport = Transport(now)
    bodies = [
        b'{"refreshing":true,"frames":{},"staleUntil":"2100-01-01T00:00:00Z"}',
        b'{"refreshing":false,"frames":{"weekly":[1]},"staleUntil":"2100-01-01T00:00:00Z"}',
    ]
    original = transport.open

    def open_(request, timeout):
        if urlsplit(request.full_url).netloc == "admin.omi.me":
            transport.calls.append(request.full_url)
            return io.BytesIO(bodies.pop(0))
        return original(request, timeout)

    transport.open = open_
    proxy = StatsProxy(transport, lambda: now[0], spawn=inline)
    path = "/api/omi/stats/wall/series/growth"
    assert proxy.fetch(path) == (200, b'{"refreshing":true,"frames":{},"staleUntil":"2100-01-01T00:00:00Z"}')
    now[0] += 5
    assert (
        proxy.fetch(path)[1] == b'{"refreshing":true,"frames":{},"staleUntil":"2100-01-01T00:00:00Z"}'
    )  # coalesced within the short TTL
    now[0] += REFRESHING_TTL
    # Expired: answered from the last good body at once, refreshed behind it.
    assert proxy.fetch(path)[1] == b'{"refreshing":true,"frames":{},"staleUntil":"2100-01-01T00:00:00Z"}'
    assert proxy.fetch(path)[1] == b'{"refreshing":false,"frames":{"weekly":[1]},"staleUntil":"2100-01-01T00:00:00Z"}'
    now[0] += REFRESHING_TTL + 60
    assert (
        proxy.fetch(path)[1] == b'{"refreshing":false,"frames":{"weekly":[1]},"staleUntil":"2100-01-01T00:00:00Z"}'
    )  # settled body cached 900s


def test_a_slow_path_does_not_hold_other_paths():
    now = [10000]
    proxy = StatsProxy(clock=lambda: now[0])
    entered, release = threading.Event(), threading.Event()

    def upstream(url, *args, **kwargs):
        if url.endswith("/health"):
            entered.set()
            assert release.wait(10)
        return b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}'

    proxy.identity_token = lambda: "synthetic"
    proxy.request = upstream
    with ThreadPoolExecutor(max_workers=2) as pool:
        slow = pool.submit(proxy.fetch, "/api/omi/stats/wall/series/health")
        assert entered.wait(10)
        try:
            fast = pool.submit(proxy.fetch, "/api/omi/stats/wall/series/headline")
            assert fast.result(timeout=5) == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')
            assert not slow.done()
        finally:
            release.set()
        assert slow.result(timeout=10) == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')


def test_background_refresh_is_single_flight_per_path():
    now = [10000]
    spawned = []
    proxy = StatsProxy(clock=lambda: now[0], spawn=spawned.append)
    proxy.identity_token = lambda: "synthetic"
    proxy.request = lambda *args, **kwargs: b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}'
    path = "/api/omi/stats/wall/series/retention"
    proxy.fetch(path)
    now[0] += 901
    for _ in range(13):  # every retention target on one board load
        assert proxy.fetch(path) == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')
    assert len(spawned) == 1
    spawned[0]()
    now[0] += 901
    proxy.fetch(path)
    assert len(spawned) == 2


@pytest.mark.parametrize("code", [401, 403])
def test_a_revoked_reader_drops_the_last_good_body(code):
    now = [10000]
    proxy = StatsProxy(clock=lambda: now[0], spawn=inline)
    proxy.identity_token = lambda: "synthetic"
    proxy.request = lambda *args, **kwargs: b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}'
    path = "/api/omi/stats/wall/series/revenue"
    assert proxy.fetch(path)[0] == 200
    now[0] += 901

    def denied(*args, **kwargs):
        raise HTTPError("https://admin.omi.me" + path, code, "denied", {}, io.BytesIO())

    proxy.request = denied
    proxy.fetch(path)  # the background refresh is denied
    assert proxy.fetch(path)[0] == 502  # finance data leaves the board at once
    now[0] += 6
    assert proxy.fetch(path)[0] == 502


def test_refreshing_answers_do_not_extend_the_stale_bound():
    now = [10000]
    proxy = StatsProxy(clock=lambda: now[0], spawn=inline)
    proxy.identity_token = lambda: "synthetic"
    proxy.request = lambda *args, **kwargs: b'{"refreshing":false,"staleUntil":"2100-01-01T00:00:00Z"}'
    path = "/api/omi/stats/wall/series/growth"
    proxy.fetch(path)
    proxy.request = lambda *args, **kwargs: b'{"refreshing":true,"staleUntil":"2100-01-01T00:00:00Z"}'
    for _ in range(int(MAX_STALE / 900) - 1):
        now[0] += 900
        proxy.fetch(path)
    assert proxy.good[path][0] == 10000  # aged from the last settled answer

    def down(*args, **kwargs):
        raise TimeoutError("synthetic")

    proxy.request = down
    now[0] = 10000 + MAX_STALE  # a day after the last settled answer
    assert proxy.fetch(path)[0] == 502


def test_a_failed_background_start_lets_the_next_request_retry():
    now = [10000]
    calls = []

    def broken(work):
        calls.append(work)
        raise RuntimeError("can't start new thread")

    proxy = StatsProxy(clock=lambda: now[0], spawn=broken)
    proxy.identity_token = lambda: "synthetic"
    proxy.request = lambda *args, **kwargs: b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}'
    path = "/api/omi/stats/wall/series/health"
    proxy.fetch(path)
    now[0] += 901
    assert proxy.fetch(path) == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')
    assert proxy.fetch(path) == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')
    assert len(calls) == 2  # not stuck behind a refresh that never ran


def test_last_good_is_never_served_past_the_bodys_own_stale_bound():
    now = [1_800_000_000]
    proxy = StatsProxy(clock=lambda: now[0], spawn=inline)
    proxy.identity_token = lambda: "synthetic"
    # The admin says its oldest served value turns 24h old in one hour.
    proxy.request = lambda *args, **kwargs: b'{"staleUntil":"2027-01-15T09:00:00Z"}'
    path = "/api/omi/stats/wall/series/retention"
    proxy.fetch(path)
    bound = proxy.good[path][2]
    assert bound == datetime(2027, 1, 15, 9, tzinfo=timezone.utc).timestamp()

    def down(*args, **kwargs):
        raise TimeoutError("synthetic")

    proxy.request = down
    now[0] = bound - 1
    assert proxy.fetch(path)[0] == 200
    now[0] = bound
    assert proxy.fetch(path)[0] == 502


def test_http_same_path_cold_waiters_do_not_starve_other_paths(monkeypatch):
    now = [10000]
    proxy = StatsProxy(clock=lambda: now[0])
    entered, release = threading.Event(), threading.Event()

    def upstream(url, *args, **kwargs):
        if url.endswith("/headline"):
            entered.set()
            assert release.wait(20)
        return b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}'

    proxy.identity_token = lambda: "synthetic"
    proxy.request = upstream
    monkeypatch.setattr(Handler, "proxy", proxy)
    server = Server(("127.0.0.1", 0), Handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()

    def get(path):
        connection = HTTPConnection(*server.server_address, timeout=20)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            # More cold headline panels than the old 8-slot limit, all waiting.
            headline = [pool.submit(get, "/api/omi/stats/wall/series/headline") for _ in range(18)]
            assert entered.wait(10)
            try:
                health = pool.submit(get, "/api/omi/stats/wall/series/health")
                assert health.result(timeout=5) == (200, b'{"ok":true,"staleUntil":"2100-01-01T00:00:00Z"}')
            finally:
                release.set()
            assert all(f.result(timeout=20)[0] == 200 for f in headline)
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        serving.join(timeout=10)


def test_a_body_without_a_valid_stale_bound_is_never_served_stale():
    now = [10000]
    proxy = StatsProxy(clock=lambda: now[0], spawn=inline)
    proxy.identity_token = lambda: "synthetic"
    proxy.request = lambda *args, **kwargs: b'{"ok":true,"staleUntil":"not-a-time"}'
    path = "/api/omi/stats/wall/series/health"
    assert proxy.fetch(path)[0] == 200
    now[0] += 901

    def down(*args, **kwargs):
        raise TimeoutError("synthetic")

    proxy.request = down
    assert proxy.fetch(path)[0] == 502  # e.g. an older admin revision: fail closed


def test_a_cached_answer_expires_at_its_stale_bound_not_its_ttl():
    now = [datetime(2027, 1, 15, 8, 55, tzinfo=timezone.utc).timestamp()]
    proxy = StatsProxy(clock=lambda: now[0], spawn=inline)
    proxy.identity_token = lambda: "synthetic"
    proxy.request = lambda *args, **kwargs: b'{"staleUntil":"2027-01-15T09:00:00Z"}'
    path = "/api/omi/stats/wall/series/growth"
    proxy.fetch(path)
    assert proxy.cache[path][0] == datetime(2027, 1, 15, 9, tzinfo=timezone.utc).timestamp()


def test_a_body_already_past_its_stale_bound_is_not_served():
    now = [datetime(2027, 1, 15, 9, 1, tzinfo=timezone.utc).timestamp()]
    proxy = StatsProxy(clock=lambda: now[0], spawn=inline)
    proxy.identity_token = lambda: "synthetic"
    proxy.request = lambda *args, **kwargs: b'{"staleUntil":"2027-01-15T09:00:00Z"}'
    path = "/api/omi/stats/wall/series/headline"
    assert proxy.fetch(path)[0] == 502
    assert path not in proxy.good
    assert proxy.fetch(path)[0] == 502  # shared for FAILURE_TTL, not re-forwarded
