"""Loopback-only stats capability for Infinity. Uses GKE Workload Identity, no keys.

Only GET stats routes are forwarded. Tokens, upstream bodies and request details
are never logged. Successful GETs coalesce/cache for 15m; failures never serve stale.
"""

import base64
import json
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


class StatsProxy:
    def __init__(self, opener=None, clock=time.time):
        self.opener = opener or build_opener(ProxyHandler({}), NoRedirect())
        self.clock = clock
        self.token = ""
        self.expiry = 0
        self.token_lock = threading.Lock()
        self.cache_lock = threading.Lock()
        self.cache = {}

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

    def remember(self, path, status, body, ttl):
        stamp = self.clock()
        self.cache = {k: v for k, v in self.cache.items() if stamp < v[0]}
        while self.cache and (
            len(self.cache) >= 32 or sum(len(v[2]) for v in self.cache.values()) + len(body) > MAX_CACHE_BYTES
        ):
            del self.cache[next(iter(self.cache))]
        self.cache[path] = (min(stamp + ttl, (int(stamp) // 86400 + 1) * 86400), status, body)
        return status, body

    def fetch(self, path):
        if not allowed_path(path):
            return 404, b'{"error":"not found"}'
        # Share failures briefly too: waiters must not each retry a 360s timeout.
        with self.cache_lock:
            cached = self.cache.get(path)
            if cached and self.clock() < cached[0]:
                return cached[1], cached[2]
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
                    return self.remember(path, 200, body, REFRESHING_TTL if refreshing else SETTLED_TTL)
                except HTTPError as exc:
                    exc.close()
                    if exc.code == 401 and attempt == 0:
                        with self.token_lock:
                            self.token, self.expiry = "", 0
                        continue
                    break
                except Exception:
                    break
            return self.remember(path, 502, b'{"error":"stats upstream unavailable"}', 5)


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
        self.slots = threading.BoundedSemaphore(8)

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
