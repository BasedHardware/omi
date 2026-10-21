import hashlib
import unittest
from server import parse_files, private_host


class Boundaries(unittest.TestCase):
    def test_private_bind(self):
        self.assertEqual(private_host("172.16.1.2"), "172.16.1.2")
        for host in ["0.0.0.0", "8.8.8.8", "api.omi.me", "169.254.1.1", "::"]:
            with self.assertRaises(ValueError):
                private_host(host)

    def test_hash_exact_bytes(self):
        raw = b"\x00\xffsynthetic\r\n"
        body = (
            b'--bound\r\nContent-Disposition: form-data; name="files"; filename="audio_fixture.bin"\r\nContent-Type: application/octet-stream\r\n\r\n'
            + raw
            + b"\r\n--bound--\r\n"
        )
        self.assertEqual(
            parse_files("multipart/form-data; boundary=bound", body),
            [
                {
                    "name": "audio_fixture.bin",
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            ],
        )
        with self.assertRaises(ValueError):
            parse_files(
                "multipart/form-data; boundary=bound",
                body.replace(b"audio_fixture.bin", b"../escape.bin"),
            )

    def test_malformed(self):
        for body in [b"", b"--bound\r\ninvalid"]:
            with self.assertRaises(ValueError):
                parse_files("multipart/form-data; boundary=bound", body)


class Protocol(unittest.TestCase):
    def test_upload_ack_retains_only_hash_and_waits_for_uploaded_event(self):
        import http.server, json, tempfile, threading, urllib.request, urllib.error
        from pathlib import Path
        from server import Handler, UID

        class AuthenticatedHandler(Handler):
            def authenticated(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            server = http.server.HTTPServer(("127.0.0.1", 0), AuthenticatedHandler)
            server.receipts = Path(directory)
            server.run_id = "test-run"
            server.recovered = False
            server.complete = False
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            base = "http://127.0.0.1:" + str(server.server_port)

            def request(path, data=None, typ="application/json"):
                with urllib.request.urlopen(
                    urllib.request.Request(
                        base + path, data=data, headers={"Content-Type": typ}
                    )
                ) as r:
                    return r.status, json.load(r)

            def event(phase):
                return request(
                    "/physical-capture/events",
                    json.dumps(
                        {"phase": phase, "fixture_uid": UID, "files": []}
                    ).encode(),
                )

            try:
                raw = b"actual framed test bytes"
                body = (
                    b'--b\r\nContent-Disposition: form-data; name="files"; filename="audio_test.bin"\r\n\r\n'
                    + raw
                    + b"\r\n--b--\r\n"
                )
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request(
                        "/v2/sync-local-files", body, "multipart/form-data; boundary=b"
                    )
                self.assertEqual(error.exception.code, 503)
                event("recovered")
                self.assertEqual(
                    request("/physical-capture/control")[1]["command"], "wait"
                )
                (Path(directory) / "host-upload-approved.json").write_text(
                    json.dumps(
                        {"command": "upload", "fixture_uid": UID, "run_id": "stale-run"}
                    )
                )
                self.assertEqual(
                    request("/physical-capture/control")[1]["command"], "wait"
                )
                (Path(directory) / "host-upload-approved.json").write_text(
                    json.dumps(
                        {
                            "command": "upload",
                            "fixture_uid": UID,
                            "run_id": server.run_id,
                        }
                    )
                )
                code, ack = request(
                    "/v2/sync-local-files", body, "multipart/form-data; boundary=b"
                )
                self.assertEqual(code, 202)
                self.assertEqual(
                    request("/v2/sync-local-files/" + ack["job_id"])[1]["status"],
                    "queued",
                )
                stored = json.loads(
                    (Path(directory) / (ack["job_id"] + ".json")).read_text()
                )
                self.assertEqual(
                    stored["files"][0]["sha256"], hashlib.sha256(raw).hexdigest()
                )
                self.assertNotIn(raw.decode(), json.dumps(stored))
                event("uploaded")
                self.assertEqual(
                    request("/v2/sync-local-files/" + ack["job_id"])[1]["status"],
                    "completed",
                )
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request("/unknown")
                self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()


class TransportIsolation(unittest.TestCase):
    def test_proxy_environment_is_ignored_and_redirect_is_not_followed(self):
        import http.server, threading, urllib.request, urllib.error
        from unittest.mock import patch
        from server import emulator_opener

        hits = []

        class Endpoint(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                hits.append(self.path)
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/escaped")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"direct")

        server = http.server.HTTPServer(("127.0.0.1", 0), Endpoint)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            base = "http://127.0.0.1:" + str(server.server_port)
            with patch.dict(
                "os.environ",
                {
                    "http_proxy": "http://127.0.0.1:1",
                    "HTTP_PROXY": "http://127.0.0.1:1",
                    "no_proxy": "",
                    "NO_PROXY": "",
                },
                clear=True,
            ):
                with emulator_opener().open(base + "/direct", timeout=2) as response:
                    self.assertEqual(response.read(), b"direct")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    emulator_opener().open(base + "/redirect", timeout=2)
                self.assertEqual(error.exception.code, 302)
            self.assertEqual(hits, ["/direct", "/redirect"])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


class WearableSelection(unittest.TestCase):
    def test_run_scan_identity_ambiguity_and_auth(self):
        import http.server, json, tempfile, threading, urllib.request, urllib.error
        from pathlib import Path
        from server import Handler, WEARABLE_UID

        class FixtureAuth(Handler):
            def authenticated(self):
                return self.headers.get("Authorization") == "Bearer test-wearable"

        with tempfile.TemporaryDirectory() as directory:
            receipts = Path(directory)
            server = http.server.HTTPServer(("127.0.0.1", 0), FixtureAuth)
            server.receipts = receipts
            server.fixture_uid = WEARABLE_UID
            server.run_id = "wearable-run"
            server.recovered = False
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            base = "http://127.0.0.1:" + str(server.server_port)

            def request(path, data=None, authenticated=True):
                headers = {"Content-Type": "application/json"}
                if authenticated:
                    headers["Authorization"] = "Bearer test-wearable"
                with urllib.request.urlopen(
                    urllib.request.Request(
                        base + path,
                        data=json.dumps(data).encode() if data is not None else None,
                        headers=headers,
                    ),
                    timeout=2,
                ) as r:
                    return json.load(r)

            def scan(scan_id, candidates):
                return request(
                    "/physical-capture/events",
                    {
                        "phase": "wearable_candidates",
                        "fixture_uid": WEARABLE_UID,
                        "process": "boot-1",
                        "scan_id": scan_id,
                        "candidates": candidates,
                    },
                )

            candidate = {"peripheral_id": "AA-BB", "name": "Omi", "rssi": -50}
            approval = {
                "command": "select_wearable",
                "fixture_uid": WEARABLE_UID,
                "run_id": "wearable-run",
                "scan_id": "scan-1",
                "peripheral_id": "AA-BB",
            }

            def write_approval(value):
                (receipts / "host-wearable-selected.json").write_text(json.dumps(value))

            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request("/physical-capture/control", authenticated=False)
                self.assertEqual(error.exception.code, 401)
                scan("scan-1", [candidate])
                self.assertEqual(
                    request("/physical-capture/control"), {"command": "wait"}
                )
                for wrong in [
                    {**approval, "run_id": "stale"},
                    {**approval, "scan_id": "old-scan"},
                    {**approval, "peripheral_id": "OTHER"},
                ]:
                    write_approval(wrong)
                    self.assertEqual(
                        request("/physical-capture/control"), {"command": "wait"}
                    )
                write_approval(approval)
                self.assertEqual(request("/physical-capture/control"), approval)
                request(
                    "/physical-capture/events",
                    {
                        "phase": "wearable_connected",
                        "fixture_uid": WEARABLE_UID,
                        "scan_id": "scan-1",
                        "peripheral_id": "AA-BB",
                    },
                )
                with self.assertRaises(urllib.error.HTTPError):
                    request(
                        "/physical-capture/events",
                        {
                            "phase": "wearable_connected",
                            "fixture_uid": WEARABLE_UID,
                            "scan_id": "scan-1",
                            "peripheral_id": "OTHER",
                        },
                    )
                scan("scan-2", [candidate])
                self.assertEqual(
                    request("/physical-capture/control"), {"command": "wait"}
                )
                scan("scan-1", [candidate, {**candidate, "peripheral_id": "CC-DD"}])
                self.assertEqual(
                    request("/physical-capture/control"), {"command": "wait"}
                )
                with self.assertRaises(urllib.error.HTTPError):
                    scan("scan-3", [candidate, candidate])
            finally:
                server.shutdown()
                thread.join()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
