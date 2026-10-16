"""Keyless stats proxy capability boundary and token/cache lifecycle."""

import base64
import io
import json
import threading
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
        return io.BytesIO(b'{"ok":true}')


def test_cache_coalesces_panel_requests_and_refreshes_tokens_early():
    now = [10000]
    transport = Transport(now)
    proxy = StatsProxy(transport, lambda: now[0])
    assert proxy.fetch("/api/omi/stats/wall") == (200, b'{"ok":true}')
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


def test_failure_never_returns_stale_or_follows_redirect():
    now = [10000]
    transport = Transport(now)
    proxy = StatsProxy(transport, lambda: now[0])
    proxy.fetch("/api/omi/stats/wall")
    now[0] += 900

    def fail(*args, **kwargs):
        raise HTTPError("https://admin.omi.me/api/omi/stats/wall", 302, "redirect", {}, io.BytesIO())

    transport.open = fail
    assert proxy.fetch("/api/omi/stats/wall")[0] == 502


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
        return b'{"ok":true}'

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
            assert all(result.result(timeout=10) == (200, b'{"ok":true}') for result in panels)
        assert len(upstream_calls) == 1
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        serving.join(timeout=10)


def test_refreshing_body_is_cached_briefly_then_refetched():
    now = [10000]
    transport = Transport(now)
    bodies = [b'{"refreshing":true,"frames":{}}', b'{"refreshing":false,"frames":{"weekly":[1]}}']
    original = transport.open

    def open_(request, timeout):
        if urlsplit(request.full_url).netloc == "admin.omi.me":
            transport.calls.append(request.full_url)
            return io.BytesIO(bodies.pop(0))
        return original(request, timeout)

    transport.open = open_
    proxy = StatsProxy(transport, lambda: now[0])
    path = "/api/omi/stats/wall/series/growth"
    assert proxy.fetch(path) == (200, b'{"refreshing":true,"frames":{}}')
    now[0] += 5
    assert proxy.fetch(path)[1] == b'{"refreshing":true,"frames":{}}'  # coalesced within the short TTL
    now[0] += REFRESHING_TTL
    assert proxy.fetch(path)[1] == b'{"refreshing":false,"frames":{"weekly":[1]}}'
    now[0] += REFRESHING_TTL + 60
    assert proxy.fetch(path)[1] == b'{"refreshing":false,"frames":{"weekly":[1]}}'  # settled body cached 900s
