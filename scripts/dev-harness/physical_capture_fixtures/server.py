"""Synthetic capture acknowledgment API. No transcription or full backend support."""

import argparse, base64, hashlib, http.server, ipaddress, json, os, re, time, urllib.parse, urllib.request, uuid
from pathlib import Path
from email.parser import BytesParser
from email.policy import default

UID = "omi-physical-fixture-20260922"
WEARABLE_UID = "omi-physical-fixture-wearable-20260922"
PROJECT = "demo-omi-local"
MAX_BODY = 32 * 1024 * 1024


def private_host(host):
    ip = ipaddress.ip_address(host)
    if ip.version != 4 or not any(
        ip in ipaddress.ip_network(n)
        for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8")
    ):
        raise ValueError("explicit private IPv4 required")
    return host


def custom_token(uid=UID):
    def enc(x):
        return base64.urlsafe_b64encode(json.dumps(x).encode()).rstrip(b"=").decode()

    now = int(time.time())
    return (
        enc({"alg": "none", "typ": "JWT"})
        + "."
        + enc(
            {
                "uid": uid,
                "iat": now,
                "exp": now + 3600,
                "aud": "https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1.IdentityToolkit",
                "iss": "fixture@demo-omi-local.iam.gserviceaccount.com",
                "sub": "fixture@demo-omi-local.iam.gserviceaccount.com",
            }
        )
        + "."
    )


def parse_files(content_type, body):
    if len(body) > MAX_BODY or not content_type.startswith("multipart/form-data;"):
        raise ValueError("multipart required")
    msg = BytesParser(policy=default).parsebytes(
        ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode()
        + body
    )
    if not msg.is_multipart() or msg.defects:
        raise ValueError("invalid multipart")
    files = []
    for part in msg.iter_parts():
        name = part.get_filename()
        if (
            part.defects
            or part.is_multipart()
            or part.get_param("name", header="content-disposition") != "files"
            or not name
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,240}\.bin", name)
        ):
            raise ValueError("invalid part")
        data = part.get_payload(decode=True)
        if not data or len(files) >= 64:
            raise ValueError("empty or excessive files")
        files.append(
            {
                "name": name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    if not files:
        raise ValueError("no files")
    return files


def validate_scan(event):
    scan_id = event.get("scan_id")
    candidates = event.get("candidates")
    if not isinstance(scan_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_.:-]{1,160}", scan_id
    ):
        raise ValueError("invalid scan id")
    if not isinstance(candidates, list) or len(candidates) > 64:
        raise ValueError("invalid candidates")
    seen = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != {
            "peripheral_id",
            "name",
            "rssi",
        }:
            raise ValueError("invalid candidate shape")
        peripheral = candidate["peripheral_id"]
        if (
            not isinstance(peripheral, str)
            or not re.fullmatch(r"[A-Za-z0-9:-]{1,128}", peripheral)
            or peripheral in seen
        ):
            raise ValueError("invalid or duplicate peripheral")
        if not isinstance(candidate["name"], str) or len(candidate["name"]) > 128:
            raise ValueError("invalid candidate name")
        if type(candidate["rssi"]) is not int or not -150 <= candidate["rssi"] <= 20:
            raise ValueError("invalid RSSI")
        seen.add(peripheral)
    return {"scan_id": scan_id, "candidates": candidates}


def selected_wearable(receipts, run_id, fixture_uid, scan):
    path = receipts / "host-wearable-selected.json"
    if (
        not scan
        or len(scan["candidates"]) != 1
        or not path.is_file()
        or path.is_symlink()
    ):
        return None
    expected = {
        "command": "select_wearable",
        "run_id": run_id,
        "fixture_uid": fixture_uid,
        "scan_id": scan["scan_id"],
        "peripheral_id": scan["candidates"][0]["peripheral_id"],
    }
    try:
        return expected if json.loads(path.read_text()) == expected else None
    except (OSError, ValueError):
        return None


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code, "emulator redirect refused", headers, fp
        )


def emulator_opener():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), RejectRedirects()
    )


class Handler(http.server.BaseHTTPRequestHandler):
    @property
    def fixture_uid(self):
        return getattr(self.server, "fixture_uid", UID)

    def log_message(self, *args):
        pass

    def respond(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self, limit=MAX_BODY):
        if (
            self.headers.get("Transfer-Encoding")
            or len(self.headers.get_all("Content-Length", [])) != 1
        ):
            raise ValueError("length required")
        size = int(self.headers["Content-Length"])
        if not 0 <= size <= limit:
            raise ValueError("body too large")
        self.connection.settimeout(15)
        data = self.rfile.read(size)
        if len(data) != size:
            raise ValueError("truncated")
        return data

    def authenticated(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or len(auth) > 8192:
            return False
        req = urllib.request.Request(
            self.server.auth_url
            + "/identitytoolkit.googleapis.com/v1/accounts:lookup?key=fake-api-key",
            data=json.dumps({"idToken": auth[7:]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with emulator_opener().open(req, timeout=5) as r:
                users = json.load(r).get("users", [])
            return len(users) == 1 and users[0].get("localId") == self.fixture_uid
        except Exception:
            return False

    def upload_permitted(self):
        control = self.server.receipts / "host-upload-approved.json"
        if not self.server.recovered or not control.is_file() or control.is_symlink():
            return False
        try:
            return json.loads(control.read_text()) == {
                "command": "upload",
                "fixture_uid": self.fixture_uid,
                "run_id": self.server.run_id,
            }
        except (ValueError, OSError):
            return False

    def save(self, name, obj):
        with (self.server.receipts / name).open("x") as f:
            json.dump(obj, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/v1/auth/local-dev/custom-token":
                if urllib.parse.parse_qs(self.body(1024).decode()) != {
                    "uid": [self.fixture_uid]
                }:
                    return self.respond(403, {"error": "fixture_uid_required"})
                return self.respond(
                    200, {"custom_token": custom_token(self.fixture_uid)}
                )
            if path not in ("/v2/sync-local-files", "/physical-capture/events"):
                return self.respond(404, {"error": "unsupported_fixture_route"})
            if not self.authenticated():
                return self.respond(401, {"error": "fixture_auth_required"})
            if path == "/physical-capture/events":
                event = json.loads(self.body(65536))
                if (
                    set(event)
                    - {
                        "phase",
                        "fixture_uid",
                        "process",
                        "files",
                        "at_ms",
                        "source",
                        "duration_seconds",
                        "scan_id",
                        "candidates",
                        "peripheral_id",
                    }
                    or event.get("fixture_uid") != self.fixture_uid
                    or event.get("phase")
                    not in (
                        "boot",
                        "capturing",
                        "awaiting_termination",
                        "recovered",
                        "uploaded",
                        "completed",
                        "wearable_candidates",
                        "wearable_connected",
                    )
                ):
                    raise ValueError("invalid event")
                if event["phase"].startswith("wearable_"):
                    if self.fixture_uid != WEARABLE_UID:
                        raise ValueError("wearable event requires wearable fixture")
                    if event["phase"] == "wearable_candidates":
                        scan = validate_scan(event)
                    else:
                        selected = selected_wearable(
                            self.server.receipts,
                            self.server.run_id,
                            self.fixture_uid,
                            getattr(self.server, "latest_scan", None),
                        )
                        if (
                            not selected
                            or event.get("scan_id") != selected["scan_id"]
                            or event.get("peripheral_id") != selected["peripheral_id"]
                        ):
                            raise ValueError(
                                "connected wearable differs from approved scan"
                            )
                for f in event.get("files", []):
                    if set(f) - {
                        "wal_id",
                        "filename",
                        "bytes",
                        "sha256",
                        "status",
                        "job_id",
                    } or not re.fullmatch("[0-9a-f]{64}", f.get("sha256", "")):
                        raise ValueError("invalid file metadata")
                self.save(
                    "event-" + uuid.uuid4().hex + ".json",
                    {**event, "run_id": self.server.run_id},
                )
                if event["phase"] == "wearable_candidates":
                    self.server.latest_scan = scan
                if event["phase"] == "recovered":
                    self.server.recovered = True
                if event["phase"] == "uploaded":
                    self.server.complete = True
                return self.respond(200, {"accepted": True})
            if not self.upload_permitted():
                return self.respond(503, {"error": "awaiting_recovered_snapshot"})
            files = parse_files(self.headers.get("Content-Type", ""), self.body())
            job = "fixture-" + uuid.uuid4().hex
            self.save(
                job + ".json",
                {
                    "schema": "synthetic-upload-ack-v1",
                    "run_id": self.server.run_id,
                    "job_id": job,
                    "uid": self.fixture_uid,
                    "received_at": time.time(),
                    "files": files,
                    "total_bytes": sum(f["bytes"] for f in files),
                    "qualification": "synthetic acknowledgment only; no transcription",
                },
            )
            self.respond(
                202,
                {
                    "job_id": job,
                    "status": "queued",
                    "poll_after_ms": 1000,
                    "total_files": len(files),
                    "total_segments": len(files),
                    "lane": "fresh",
                },
            )
        except (ValueError, UnicodeError, TimeoutError, TypeError):
            self.respond(400, {"error": "invalid_fixture_request"})

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in ("/health", "/v1/health"):
            return self.respond(
                200,
                {"service": "synthetic-physical-capture-fixture", "project": PROJECT},
            )
        if path == "/v4/listen":
            return self.respond(503, {"error": "synthetic_fixture_has_no_streaming"})
        if not self.authenticated():
            return self.respond(401, {"error": "fixture_auth_required"})
        if path == "/v1/users/onboarding":
            return self.respond(200, {"completed": True})
        if path == "/v1/users/language":
            return self.respond(200, {"language": "en"})
        if path == "/v1/account/cutover/control":
            return self.respond(
                200,
                {
                    "state": "legacy",
                    "client_action": "none",
                    "offline_queue_instruction": "none",
                    "account_generation": 0,
                    "ui_generation": 0,
                    "api_generation": 0,
                    "product_traffic_allowed": True,
                    "legacy_writes_allowed": True,
                    "auth_bootstrap_reachable": True,
                    "stranded_new_data": False,
                },
            )
        if path == "/physical-capture/control":
            selected = selected_wearable(
                self.server.receipts,
                self.server.run_id,
                self.fixture_uid,
                getattr(self.server, "latest_scan", None),
            )
            return self.respond(
                200,
                (
                    {"command": "upload"}
                    if self.upload_permitted()
                    else selected or {"command": "wait"}
                ),
            )
        if re.fullmatch(r"/v2/sync-local-files/fixture-[0-9a-f]{32}", path):
            file = self.server.receipts / (path.rsplit("/", 1)[1] + ".json")
            if file.exists():
                receipt = json.loads(file.read_text())
                if receipt.get("run_id") != self.server.run_id:
                    return self.respond(404, {"error": "foreign_fixture_run"})
                count = len(receipt["files"])
                complete = self.server.complete
                completion_path = "completed-" + receipt["job_id"] + ".json"
                if complete and not (self.server.receipts / completion_path).exists():
                    self.save(
                        completion_path,
                        {
                            "run_id": self.server.run_id,
                            "job_id": receipt["job_id"],
                            "status": "completed",
                            "http_status": 202,
                            "files": [
                                {
                                    "filename": f["name"],
                                    "bytes": f["bytes"],
                                    "sha256": f["sha256"],
                                    "job_id": receipt["job_id"],
                                }
                                for f in receipt["files"]
                            ],
                        },
                    )
                return self.respond(
                    200,
                    {
                        "job_id": receipt["job_id"],
                        "status": "completed" if complete else "queued",
                        "total_segments": count,
                        "processed_segments": count if complete else 0,
                        "successful_segments": count if complete else 0,
                        "failed_segments": 0,
                        "result": (
                            {
                                "new_memories": [],
                                "updated_memories": [],
                                "total_segments": count,
                                "failed_segments": 0,
                            }
                            if complete
                            else None
                        ),
                    },
                )
        self.respond(404, {"error": "unsupported_fixture_route"})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", required=True, type=private_host)
    p.add_argument("--port", type=int, default=18765)
    p.add_argument("--fixture-uid", choices=(UID, WEARABLE_UID), default=UID)
    p.add_argument("--auth-port", type=int, default=19099)
    p.add_argument("--receipts", type=Path, required=True)
    p.add_argument("--synthetic-only", action="store_true", required=True)
    a = p.parse_args()
    a.receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = http.server.HTTPServer((a.host, a.port), Handler)
    s.auth_url = f"http://{a.host}:{a.auth_port}"
    s.receipts = a.receipts
    s.fixture_uid = a.fixture_uid
    s.run_id = uuid.uuid4().hex
    (a.receipts / "run.json").write_text(
        json.dumps(
            {
                "run_id": s.run_id,
                "fixture_uid": s.fixture_uid,
                "api_base_url": f"http://{a.host}:{a.port}/",
                "auth_emulator_url": s.auth_url + "/",
                "started_at_ms": time.time_ns() // 1000000,
            }
        )
    )
    s.recovered = False
    s.complete = False
    print(
        json.dumps(
            {
                "api": f"http://{a.host}:{a.port}/",
                "auth": s.auth_url,
                "project": PROJECT,
                "receipts": str(a.receipts),
                "run_id": s.run_id,
            }
        ),
        flush=True,
    )
    s.serve_forever()


if __name__ == "__main__":
    main()
