"""Loopback-only stats capability for Infinity. Uses GKE Workload Identity, no keys.

Only GET stats routes are forwarded. Tokens, upstream bodies and request details
are never logged. Each path coalesces and caches on its own (15m settled, 15s while
the admin reports `refreshing`). Once a path has answered, an expired or failed
refresh serves that last good body (up to MAX_STALE) while one background refresh
per path runs, so a slow or cold admin never blanks the board; the admin body
carries its own freshness ("Data through", cacheStale). Only a path that has never
answered blocks, and a failure there is shared briefly, never retried per panel.
"""

import base64
import json
from datetime import datetime
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

AUDIENCE = "https://admin.omi.me/api/omi/stats"
READER = "omi-stats-reader@based-hardware.iam.gserviceaccount.com"
METADATA = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
MINT = f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{READER}:generateIdToken"
MAX_BODY = 8 * 1024 * 1024
MAX_CACHE_BYTES = 32 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# The private board requests exactly these routes (see
# web/admin/grafana/dashboards/omi-tv-v2.json and SERIES_NAMES in
# web/admin/lib/wall-series.ts). Anything else — other stats routes, query
# strings, fragments — is rejected before parsing so unique attacker URLs cannot
# each become a distinct 360-second cache/slot entry. The set is fixed and small.
WALL_PATH = "/api/omi/stats/wall"
SERIES_NAMES = ("headline", "growth", "activation", "retention", "revenue", "health")
ALLOWED_PATHS = frozenset([WALL_PATH] + [f"{WALL_PATH}/series/{name}" for name in SERIES_NAMES])
# A cold admin response returns within its 5 s bound while the fill continues
# (`"refreshing": true`). Cache that body only briefly so the next panel refresh
# picks up the filled result instead of pinning the empty one for 15 minutes.
REFRESHING_TTL = 15
SETTLED_TTL = 900
FAILURE_TTL = 5
UNAVAILABLE = b'{"error":"stats upstream unavailable"}'
# The admin keeps stale-good legs for 24h and labels them; the proxy never holds a
# body longer than that.
MAX_STALE = 24 * 3600


def allowed_path(path):
    if path not in ALLOWED_PATHS:
        return False
    parsed = urlsplit(path)
    return (
        not parsed.scheme
        and not parsed.netloc
        and not parsed.query
        and not parsed.fragment
        and not any(ord(c) < 32 or ord(c) == 127 for c in path)
    )


def stale_until(body):
    """The admin's `staleUntil` (ISO time its oldest served value turns 24h old),
    or None when the body carries no valid bound."""
    try:
        value = json.loads(body).get("staleUntil")
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


class StatsProxy:
    def __init__(self, opener=None, clock=time.time, spawn=None):
        self.opener = opener or build_opener(ProxyHandler({}), NoRedirect())
        self.clock = clock
        self.spawn = spawn or (lambda work: threading.Thread(target=work, daemon=True).start())
        self.token = ""
        self.expiry = 0
        self.token_lock = threading.Lock()
        # state_lock guards the dicts below and is never held across I/O. One
        # fill lock per path: a slow series no longer queues every other path
        # (2026-10-28: one global lock serialized all six behind the slowest).
        self.state_lock = threading.Lock()
        self.cache = {}  # path -> (expires_at, status, body), latest answer
        self.good = {}  # path -> (at, body, serve_until), last 200
        self.fill_locks = {}
        self.refreshing = set()

    def request(self, url, headers=None, data=None, timeout=20):
        request = Request(url, headers=headers or {}, data=data)
        with self.opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise ValueError("response too large")
            return body

    def identity_token(self):
        with self.token_lock:
            if self.token and self.clock() < self.expiry - 300:
                return self.token
            access = json.loads(self.request(METADATA, {"Metadata-Flavor": "Google"}))["access_token"]
            result = json.loads(
                self.request(
                    MINT,
                    {"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
                    json.dumps({"audience": AUDIENCE, "includeEmail": True}).encode(),
                )
            )
            token = result["token"]
            payload = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            # Token came directly from Google's TLS endpoint. Fail closed on an
            # unexpected impersonation result; this is not a public JWT verifier.
            if claims.get("aud") != AUDIENCE or claims.get("email") != READER:
                raise ValueError("unexpected identity")
            expiry = float(claims["exp"])
            if expiry <= self.clock() + 300:
                raise ValueError("short token lifetime")
            self.token, self.expiry = token, expiry
            return token

    def remember(self, path, status, body, ttl, refreshing=False):
        """Record a path's latest answer; caller holds state_lock."""
        stamp = self.clock()
        self.cache = {k: v for k, v in self.cache.items() if stamp < v[0]}
        self.good = {k: v for k, v in self.good.items() if stamp < v[2]}
        while self.cache and (
            len(self.cache) >= 32 or sum(len(v[2]) for v in self.cache.values()) + len(body) > MAX_CACHE_BYTES
        ):
            del self.cache[next(iter(self.cache))]
        expires = stamp + ttl
        if status == 200:
            # A `refreshing` body keeps the age of the last settled answer, so
            # repeated refreshing answers cannot extend MAX_STALE indefinitely.
            prior = self.good.get(path)
            at = prior[0] if refreshing and prior else stamp
            # Fail closed: only a body that states its own data-age bound
            # (admin `staleUntil`) is ever served stale, and never past it.
            bound = stale_until(body)
            if bound is None or bound <= stamp:
                self.good.pop(path, None)
            else:
                serve_until = min(at + MAX_STALE, bound)
                self.good[path] = (at, body, serve_until)
                expires = min(expires, serve_until)
            if bound is not None and bound <= stamp:
                # Already past its own data-age bound: not data the board may show.
                status, body, expires = 502, UNAVAILABLE, stamp + FAILURE_TTL
        self.cache[path] = (expires, status, body)
        return status, body

    def upstream(self, path):
        for attempt in range(2):
            try:
                token = self.identity_token()
                body = self.request(
                    "https://admin.omi.me" + path,
                    {"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    timeout=360,
                )
                parsed = json.loads(body)  # Never forward HTML, redirects or a login page.
                refreshing = isinstance(parsed, dict) and parsed.get("refreshing") is True
                return 200, body, REFRESHING_TTL if refreshing else SETTLED_TTL, refreshing, False
            except HTTPError as exc:
                exc.close()
                if exc.code == 401 and attempt == 0:
                    with self.token_lock:
                        self.token, self.expiry = "", 0
                    continue
                # A definitive denial (reader revoked) must not keep finance data
                # on the board; transport errors and 5xx may serve last good.
                return 502, UNAVAILABLE, FAILURE_TTL, False, exc.code in (401, 403)
            except Exception:
                break
        return 502, UNAVAILABLE, FAILURE_TTL, False, False

    def fill(self, path):
        """One upstream read per path at a time; waiters share its answer."""
        with self.state_lock:
            lock = self.fill_locks.setdefault(path, threading.Lock())
        with lock:
            with self.state_lock:
                cached = self.cache.get(path)
                if cached and self.clock() < cached[0]:
                    return cached[1], cached[2]
            status, body, ttl, refreshing, denied = self.upstream(path)
            with self.state_lock:
                if denied:
                    self.good.pop(path, None)
                elif status != 200 and path in self.good:
                    # Keep serving the last good body; retry after FAILURE_TTL.
                    self.cache[path] = (self.clock() + ttl, status, body)
                    return status, body
                return self.remember(path, status, body, ttl, refreshing)

    def refresh(self, path):
        try:
            self.fill(path)
        except Exception:
            pass
        finally:
            with self.state_lock:
                self.refreshing.discard(path)

    def fetch(self, path):
        if not allowed_path(path):
            return 404, b'{"error":"not found"}'
        now = self.clock()
        start = False
        with self.state_lock:
            cached = self.cache.get(path)
            fresh = cached is not None and now < cached[0]
            if fresh and cached[1] == 200:
                return cached[1], cached[2]
            good = self.good.get(path)
            if not (good and now < good[2]):
                good = None
                if fresh:
                    return cached[1], cached[2]
            elif not fresh and path not in self.refreshing:
                # Stale-while-revalidate: answer now, refresh once in the
                # background (not while a recent failure is cooling down).
                self.refreshing.add(path)
                start = True
        if good is None:
            return self.fill(path)
        if start:
            try:
                self.spawn(lambda: self.refresh(path))
            except Exception:
                # e.g. thread start failed: let the next request try again.
                with self.state_lock:
                    self.refreshing.discard(path)
        return 200, good[1]


class Handler(BaseHTTPRequestHandler):
    proxy: StatsProxy | None = None

    def log_message(self, *_args):
        pass

    def send_error(self, code, message=None, explain=None):
        # BaseHTTPRequestHandler's default error includes attacker input.
        self.reply(code, b'{"error":"request rejected"}')

    def reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):
        try:
            assert self.proxy is not None
            code, body = self.proxy.fetch(self.path)
        except Exception:
            code, body = 502, b'{"error":"stats upstream unavailable"}'
        self.reply(code, body)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # The board fires ~24 Infinity targets at once; every admitted request
    # coalesces behind the proxy's cache_lock, so admission must queue the
    # full burst rather than close connections beyond the upstream budget.
    request_queue_size = 64

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Handler threads, not upstream calls: each path already has at most one
        # upstream read (fill locks), so same-path waiters must not be able to
        # hold every slot while another path's request queues (Luna r2).
        self.slots = threading.BoundedSemaphore(self.request_queue_size)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(430)
        return request, address

    def process_request(self, request, client_address):
        # Bound blocking time by the socket deadline; a queued burst waits
        # here without consuming an upstream slot or being dropped.
        if not self.slots.acquire(timeout=430):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # No tracebacks containing requests, upstream bodies or tokens.


if __name__ == "__main__":
    Handler.proxy = StatsProxy()
    Server(("127.0.0.1", 8899), Handler).serve_forever()
