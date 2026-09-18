"""Subprocess fixture for the V2 simulator smoke machine wire.

Emits the same event names as Flutter 3.44.5 `--machine`, with the real-app
controls profile `local_dev` and signedIn=false.
"""
import json
import os
from pathlib import Path
import sys

mode, transcript, app_id, device_id = sys.argv[1:]


def emit(value):
    print(json.dumps([value]), flush=True)


emit({"event": "daemon.connected", "params": {"version": "0.6.1", "pid": os.getpid()}})
emit(
    {
        "event": "app.start",
        "params": {
            "appId": app_id,
            "deviceId": device_id,
            "directory": str(Path.cwd()),
            "supportsRestart": True,
            "launchMode": "run",
            "mode": "debug",
        },
    }
)
emit({"event": "app.debugPort", "params": {"appId": app_id, "port": 12345, "wsUri": "ws://127.0.0.1:12345/redacted/ws"}})
emit({"event": "app.started", "params": {"appId": app_id}})
for line in sys.stdin:
    request, = json.loads(line)
    with Path(transcript).open("a") as out:
        out.write(json.dumps(request) + "\n")
    method, params = request["method"], request.get("params", {})
    if params.get("appId") != app_id:
        emit({"id": request["id"], "error": "wrong appId"})
        continue
    if method == "app.callServiceExtension":
        name = params["methodName"]
        if name == "ext.omi.controls.capabilities":
            result = {
                "contract_version": "semantic-controls/v1",
                "capabilities": ["capabilities", "state", "wait_ready", "navigate", "fault"],
            }
        elif name == "ext.omi.controls.state":
            signed_in = mode == "signed-in"
            result = {
                "contract_version": "semantic-controls/v1",
                "profile": "local_dev" if mode != "wrong-profile" else "mobile_beta",
                "readiness": {"signedIn": signed_in, "routed": mode != "unrouted", "captureIdle": True},
                "principal": {"uid": "fixture-user" if signed_in else "", "signed_in": signed_in},
                "route": "/home",
            }
        else:
            emit({"id": request["id"], "error": "unknown extension"})
            continue
        emit({"id": request["id"], "result": result})
    elif method == "app.stop":
        emit({"id": request["id"], "result": True})
        sys.exit(0)
    else:
        emit({"id": request["id"], "error": "unknown method"})
