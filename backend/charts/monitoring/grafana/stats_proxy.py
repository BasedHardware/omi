"""Loopback-only stats capability for Infinity. Uses GKE Workload Identity, no keys.

Only GET stats routes are forwarded. Tokens, upstream bodies and request details
are never logged. Successful GETs coalesce/cache for 15m; failures never serve stale.
"""

import base64
import json
import re
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


def allowed_path(path):
    parsed = urlsplit(path)
    return (
        len(path) <= 2048
        and not parsed.scheme
        and not parsed.netloc
        and not parsed.fragment
        and re.fullmatch(r"/api/omi/stats/[a-z][a-z0-9-]*", parsed.path) is not None
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

    def fetch(self, path):
        if not allowed_path(path):
            return 404, b'{"error":"not found"}'
        # Serializes cache misses, bounding aggregate upstream work and coalescing
        # the 24 Canvas queries. Cache hits do not mint or refresh credentials.
        with self.cache_lock:
            now = self.clock()
            cached = self.cache.get(path)
            if cached and now < cached[0]:
                return 200, cached[1]
            for attempt in range(2):
                token = self.identity_token()
                try:
                    body = self.request(
                        "https://admin.omi.me" + path,
                        {"Authorization": f"Bearer {token}", "Accept": "application/json"},
                        timeout=65,
                    )
                    json.loads(body)  # Never forward HTML, redirects or a login page.
                    stamp = self.clock()
                    self.cache = {k: v for k, v in self.cache.items() if stamp < v[0]}
                    while self.cache and (
                        len(self.cache) >= 32
                        or sum(len(v[1]) for v in self.cache.values()) + len(body) > MAX_CACHE_BYTES
                    ):
                        del self.cache[next(iter(self.cache))]
                    self.cache[path] = (min(stamp + 900, (int(stamp) // 86400 + 1) * 86400), body)
                    return 200, body
                except HTTPError as exc:
                    exc.close()
                    if exc.code == 401 and attempt == 0:
                        with self.token_lock:
                            if self.token == token:
                                self.token, self.expiry = "", 0
                        continue
                    return 502, b'{"error":"stats upstream unavailable"}'
            return 502, b'{"error":"stats upstream unavailable"}'


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
    request_queue_size = 8

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slots = threading.BoundedSemaphore(8)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(110)
        return request, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
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
