#!/usr/bin/env python3
"""
Chaos test for app integration timeout blocking.

Minimal standalone reproduction of:
- trigger_external_integrations (timeout 30s -> 10s)
- trigger_realtime_audio_bytes (timeout 15s -> 5s)
- trigger_realtime_integrations (timeout 10s -> 5s)

Runs a local HTTP server that delays responses (5s, 12s, 20s, 35s),
spawns one thread per app, and measures wall-clock blocking time.
"""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

import requests

DELAYS = [5, 12, 20, 35]

TIMEOUTS_BY_MODE = {
    "vulnerable": {
        "external": 30,
        "audio": 15,
        "realtime": 10,
    },
    "fixed": {
        "external": 10,
        "audio": 5,
        "realtime": 5,
    },
}


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class DelayedHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        delay = 0
        path = urlparse(self.path).path
        parts = [p for p in path.split("/") if p]
        if len(parts) == 2 and parts[0] == "delay":
            try:
                delay = float(parts[1])
            except ValueError:
                delay = 0
        time.sleep(delay)
        payload = {
            "ok": True,
            "delay": delay,
            "message": f"ok after {delay}s",
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class ExternalIntegrationStub:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url


class AppStub:
    def __init__(self, app_id: str, webhook_url: str):
        self.id = app_id
        self.uid = None
        self.enabled = True
        self.external_integration = ExternalIntegrationStub(webhook_url)

    def triggers_on_conversation_creation(self) -> bool:
        return True

    def triggers_realtime_audio_bytes(self) -> bool:
        return True

    def triggers_realtime(self) -> bool:
        return True

    def has_capability(self, _cap: str) -> bool:
        return False


class ConversationStub:
    def __init__(self):
        self.discarded = False
        self.source = "normal"
        self.id = "conv-1"

    def as_dict_cleaned_dates(self):
        return {"id": self.id, "text": "hello", "external_data": None}


RESULT_LOCK = threading.Lock()


def _record_result(results, func_name, app_id, status, elapsed, timeout_used):
    with RESULT_LOCK:
        func = results.setdefault(func_name, {"apps": {}, "wall_time": None})
        func["apps"][app_id] = {
            "status": status,
            "elapsed": round(elapsed, 3),
            "timeout": timeout_used,
        }


def _threaded_requests(apps, func_name, make_request, results):
    threads = []

    def _single(app):
        start = time.perf_counter()
        try:
            response, timeout_used = make_request(app)
            status = "ok" if response.status_code == 200 else f"http_{response.status_code}"
        except requests.exceptions.Timeout:
            timeout_used = make_request.timeout_used
            status = "timeout"
        except Exception:
            timeout_used = make_request.timeout_used
            status = "error"
        elapsed = time.perf_counter() - start
        _record_result(results, func_name, app.id, status, elapsed, timeout_used)

    for app in apps:
        threads.append(threading.Thread(target=_single, args=(app,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()


def trigger_external_integrations(uid: str, conversation: ConversationStub, apps, timeouts, results):
    if not conversation or conversation.discarded:
        return []

    filtered_apps = [app for app in apps if app.triggers_on_conversation_creation() and app.enabled]
    if not filtered_apps:
        return []

    def _request(app):
        url = app.external_integration.webhook_url
        if "?" in url:
            url += "&uid=" + uid
        else:
            url += "?uid=" + uid
        payload = conversation.as_dict_cleaned_dates()
        _request.timeout_used = timeouts["external"]
        response = requests.post(url, json=payload, timeout=timeouts["external"])
        return response, timeouts["external"]

    _request.timeout_used = timeouts["external"]
    _threaded_requests(filtered_apps, "trigger_external_integrations", _request, results)
    return []


async def trigger_realtime_audio_bytes(uid: str, sample_rate: int, data: bytearray, apps, timeouts, results):
    filtered_apps = [app for app in apps if app.triggers_realtime_audio_bytes() and app.enabled]
    if not filtered_apps:
        return {}

    def _request(app):
        url = app.external_integration.webhook_url
        url += f"?sample_rate={sample_rate}&uid={uid}"
        _request.timeout_used = timeouts["audio"]
        response = requests.post(
            url,
            data=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=timeouts["audio"],
        )
        return response, timeouts["audio"]

    _request.timeout_used = timeouts["audio"]
    _threaded_requests(filtered_apps, "trigger_realtime_audio_bytes", _request, results)
    return {}


async def trigger_realtime_integrations(
    uid: str, segments: list[dict], conversation_id: str | None, apps, timeouts, results
):
    filtered_apps = [app for app in apps if app.triggers_realtime() and app.enabled]
    if not filtered_apps:
        return {}

    def _request(app):
        url = app.external_integration.webhook_url
        if "?" in url:
            url += "&uid=" + uid
        else:
            url += "?uid=" + uid
        _request.timeout_used = timeouts["realtime"]
        response = requests.post(
            url,
            json={"session_id": uid, "segments": segments},
            timeout=timeouts["realtime"],
        )
        return response, timeouts["realtime"]

    _request.timeout_used = timeouts["realtime"]
    _threaded_requests(filtered_apps, "trigger_realtime_integrations", _request, results)
    return {}


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), DelayedHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _run_mode(mode: str):
    if mode not in TIMEOUTS_BY_MODE:
        raise ValueError(f"unknown mode: {mode}")

    timeouts = TIMEOUTS_BY_MODE[mode]
    server, port = _start_server()

    try:
        apps = [AppStub(f"app-{delay}", f"http://127.0.0.1:{port}/delay/{delay}") for delay in DELAYS]

        results = {}

        conversation = ConversationStub()
        uid = "user-123"
        segments = [{"text": "hello", "start": 0.0, "end": 1.0}]
        data = bytearray(b"0" * 256)

        timings = {}

        start = time.perf_counter()
        trigger_external_integrations(uid, conversation, apps, timeouts, results)
        timings["trigger_external_integrations"] = round(time.perf_counter() - start, 3)

        start = time.perf_counter()
        import asyncio

        asyncio.run(trigger_realtime_audio_bytes(uid, 16000, data, apps, timeouts, results))
        timings["trigger_realtime_audio_bytes"] = round(time.perf_counter() - start, 3)

        start = time.perf_counter()
        asyncio.run(trigger_realtime_integrations(uid, segments, "conv-1", apps, timeouts, results))
        timings["trigger_realtime_integrations"] = round(time.perf_counter() - start, 3)

        total_blocking = round(sum(timings.values()), 3)

        for func_name, wall_time in timings.items():
            results.setdefault(func_name, {"apps": {}})["wall_time"] = wall_time

        output = {
            "mode": mode,
            "timeouts": timeouts,
            "delays": DELAYS,
            "timings": timings,
            "total_blocking_time": total_blocking,
            "results": results,
        }
        return output
    finally:
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Chaos test for app integration timeouts")
    parser.add_argument("--mode", choices=sorted(TIMEOUTS_BY_MODE.keys()), required=True)
    args = parser.parse_args()

    output = _run_mode(args.mode)

    print("Mode:", output["mode"])
    print("Timeouts:", output["timeouts"])
    print("Delays:", output["delays"])
    print("Timings (seconds):")
    for name, wall in output["timings"].items():
        print(f"  {name}: {wall}")
    print("Total blocking time (seconds):", output["total_blocking_time"])

    print("App outcomes:")
    for func_name, data in output["results"].items():
        apps = data.get("apps", {})
        print(f"  {func_name}:")
        for app_id, info in apps.items():
            print(f"    {app_id}: {info['status']} (elapsed={info['elapsed']}s, timeout={info['timeout']}s)")

    print("RESULT:", json.dumps(output))


if __name__ == "__main__":
    main()
