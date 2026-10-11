#!/usr/bin/env python3
"""Loopback MCP/OAuth QA fixture; inert tokens, static data, no external calls or file I/O."""

import base64
import hashlib
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit


MAX_BODY = 65536
MAX_RECORDS = 32
TTL_SECONDS = 300
ACCESS_TOKEN = "qa-ok"
REFRESH_TOKEN = "qa-refresh-stub"


def loopback_redirect(value):
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and parsed.port is not None
            and 0 < parsed.port < 65536
            and parsed.username is None
            and parsed.password is None
            and parsed.path == "/callback"
            and not parsed.query
            and not parsed.fragment
        )
    except (ValueError, TypeError):
        return False


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self):
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.resource = f"{self.origin}/mcp"
        self.lock = threading.Lock()
        self.clients = {}
        self.codes = {}
        self.authorized_clients = set()
        self.next_client = 1
        self.next_code = 1

    def trim(self):
        now = time.monotonic()
        self.clients = {key: value for key, value in self.clients.items() if value["expires"] > now}
        self.codes = {key: value for key, value in self.codes.items() if value["expires"] > now}
        self.authorized_clients.intersection_update(self.clients)


class FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "OmiQA"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        # Never emit paths, query parameters, callback states, credentials, or tokens.
        pass

    def reply(self, status, payload=None, headers=None):
        body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def error(self, code="invalid_request", status=400):
        self.reply(status, {"error": code})

    def body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
                self.error(status=413)
                return None
            body = self.rfile.read(length)
            if len(body) != length:
                self.error()
                return None
            return body.decode("utf-8")
        except (ValueError, UnicodeError, OSError):
            self.error()
            return None

    def json_body(self):
        body = self.body()
        if body is None:
            return None
        try:
            value = json.loads(body)
            if isinstance(value, dict):
                return value
        except ValueError:
            pass
        self.error()
        return None

    def do_GET(self):
        parsed = urlsplit(self.path)
        origin = self.server.origin
        if parsed.path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
            self.reply(200, {"resource": self.server.resource, "authorization_servers": [f"{origin}/issuer"],
                             "scopes_supported": ["qa.read"]})
        elif parsed.path in (
            "/.well-known/oauth-authorization-server", "/.well-known/oauth-authorization-server/issuer",
            "/issuer/.well-known/oauth-authorization-server", "/.well-known/openid-configuration",
            "/.well-known/openid-configuration/issuer", "/issuer/.well-known/openid-configuration",
        ):
            self.reply(200, {"issuer": f"{origin}/issuer", "authorization_endpoint": f"{origin}/authorize",
                             "token_endpoint": f"{origin}/token", "registration_endpoint": f"{origin}/register",
                             "response_types_supported": ["code"],
                             "grant_types_supported": ["authorization_code", "refresh_token"],
                             "token_endpoint_auth_methods_supported": ["none"],
                             "code_challenge_methods_supported": ["S256"], "scopes_supported": ["qa.read"]})
        elif parsed.path == "/authorize":
            self.authorize(parsed.query)
        elif parsed.path == "/mcp":
            self.reply(405, {"error": "read_only_json_rpc_post_required"}, {"Allow": "POST"})
        else:
            self.error("not_found", 404)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/register":
            self.register()
        elif path == "/token":
            self.token()
        elif path == "/mcp":
            self.mcp()
        else:
            self.error("not_found", 404)

    def register(self):
        payload = self.json_body()
        if payload is None:
            return
        redirects = payload.get("redirect_uris")
        if (not isinstance(redirects, list) or len(redirects) != 1 or not loopback_redirect(redirects[0])
                or payload.get("token_endpoint_auth_method", "none") != "none"):
            self.error()
            return
        with self.server.lock:
            self.server.trim()
            if len(self.server.clients) >= MAX_RECORDS:
                self.error("fixture_capacity", 429)
                return
            client = f"qa-client-{self.server.next_client}"
            self.server.next_client += 1
            self.server.clients[client] = {"redirect": redirects[0], "expires": time.monotonic() + TTL_SECONDS}
        self.reply(201, {"client_id": client, "redirect_uris": redirects,
                         "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
                         "response_types": ["code"]})

    def authorize(self, query):
        fields = parse_qs(query, keep_blank_values=True)
        if any(len(values) != 1 for values in fields.values()):
            self.error()
            return
        fields = {key: values[0] for key, values in fields.items()}
        client, redirect, state, challenge = (fields.get(key, "") for key in
                                              ("client_id", "redirect_uri", "state", "code_challenge"))
        if (not loopback_redirect(redirect) or not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", state)
                or not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge)
                or fields.get("response_type") != "code" or fields.get("code_challenge_method") != "S256"
                or fields.get("resource") != self.server.resource):
            self.error()
            return
        with self.server.lock:
            self.server.trim()
            registered = self.server.clients.get(client)
            if registered is None or registered["redirect"] != redirect:
                self.error("invalid_client")
                return
            if len(self.server.codes) >= MAX_RECORDS:
                self.error("fixture_capacity", 429)
                return
            code = f"qa-inert-code-{self.server.next_code}"
            self.server.next_code += 1
            self.server.codes[code] = {"client": client, "redirect": redirect, "challenge": challenge,
                                       "resource": self.server.resource, "expires": time.monotonic() + TTL_SECONDS}
        self.reply(302, headers={"Location": f"{redirect}?{urlencode({'code': code, 'state': state})}"})

    def token(self):
        body = self.body()
        if body is None:
            return
        fields = parse_qs(body, keep_blank_values=True)
        if any(len(values) != 1 for values in fields.values()):
            self.error()
            return
        fields = {key: values[0] for key, values in fields.items()}
        client = fields.get("client_id", "")
        with self.server.lock:
            self.server.trim()
            if client not in self.server.clients:
                self.error("invalid_client")
                return
            if fields.get("grant_type") == "refresh_token":
                if client not in self.server.authorized_clients or fields.get("refresh_token") != REFRESH_TOKEN:
                    self.error("invalid_grant")
                    return
            elif fields.get("grant_type") == "authorization_code":
                code = fields.get("code", "")
                record = self.server.codes.get(code)
                verifier = fields.get("code_verifier", "")
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
                if (record is None or record["client"] != client or record["redirect"] != fields.get("redirect_uri")
                        or record["resource"] != fields.get("resource") or record["challenge"] != challenge
                        or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)):
                    self.error("invalid_grant")
                    return
                del self.server.codes[code]
                self.server.authorized_clients.add(client)
            else:
                self.error("unsupported_grant_type")
                return
        self.reply(200, {"access_token": ACCESS_TOKEN, "token_type": "Bearer", "expires_in": 3600,
                         "refresh_token": REFRESH_TOKEN, "scope": "qa.read"})

    def mcp(self):
        payload = self.json_body()
        if payload is None:
            return
        if self.headers.get("Authorization") != f"Bearer {ACCESS_TOKEN}":
            self.reply(401, {"error": "fixture_sign_in_required"},
                       {"WWW-Authenticate": f'Bearer resource_metadata="{self.server.origin}/.well-known/oauth-protected-resource"'})
            return
        method = payload.get("method")
        request_id = payload.get("id")
        if method == "notifications/initialized":
            self.reply(202)
            return
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            self.reply(200, {"jsonrpc": "2.0", "id": request_id,
                             "error": {"code": -32602, "message": "Invalid fixture parameters"}})
            return
        if method == "initialize":
            version = params.get("protocolVersion", "2025-03-26")
            if version not in ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"):
                version = "2025-03-26"
            result = {"protocolVersion": version, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "Omi marketplace QA (read-only fixture)", "version": "1.0"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "qa_read", "description": "Read a static QA fixture string; no external data",
                                  "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                                  "annotations": {"readOnlyHint": True, "destructiveHint": False,
                                                  "idempotentHint": True, "openWorldHint": False}}]}
        elif method == "tools/call" and params.get("name") == "qa_read":
            result = {"content": [{"type": "text", "text": "Omi marketplace QA read-only fixture connected successfully"}],
                      "isError": False}
        elif method == "ping":
            result = {}
        else:
            self.reply(200, {"jsonrpc": "2.0", "id": request_id,
                             "error": {"code": -32601, "message": "Unknown read-only fixture method"}})
            return
        self.reply(200, {"jsonrpc": "2.0", "id": request_id, "result": result})


if __name__ == "__main__":
    server = FixtureServer()
    print(server.resource, flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
