#!/usr/bin/env python3
"""Check local prerequisites for Omi desktop agent verification."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PORT = 47777


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    required: bool = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=None, help="Repository root. Defaults to this script's inferred root.")
    parser.add_argument("--require-bridge", action="store_true", help="Require the automation bridge to answer /state.")
    parser.add_argument("--port", default=os.environ.get("OMI_AUTOMATION_PORT", str(DEFAULT_PORT)))
    parser.add_argument("--require-auth-seed", action="store_true", help="Require a dumped dev auth seed file.")
    parser.add_argument(
        "--auth-file",
        default=None,
        help="Auth seed file. Defaults to desktop/macos/tmp/desktop-auth.json.",
    )
    parser.add_argument("--skip-agent-swift", action="store_true", help="Skip the agent-swift availability check.")
    parser.add_argument("--skip-node", action="store_true", help="Skip Node/npm checks.")
    return parser.parse_args()


def repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parents[3]


def command_output(command: list[str], timeout: float = 10.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "not found"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    output = result.stdout.strip().splitlines()
    detail = output[0] if output else f"exit {result.returncode}"
    return result.returncode == 0, detail


def check_tool(name: str, command: list[str], required: bool = True) -> CheckResult:
    if shutil.which(command[0]) is None:
        return CheckResult(name, "FAIL" if required else "SKIP", f"{command[0]} not found on PATH", required)
    ok, detail = command_output(command)
    return CheckResult(name, "PASS" if ok else "FAIL", detail, required)


def check_pyyaml() -> CheckResult:
    ok, detail = command_output([sys.executable, "-c", "import yaml; print(yaml.__version__)"])
    if ok:
        return CheckResult("PyYAML", "PASS", detail)
    return CheckResult(
        "PyYAML",
        "SKIP",
        "optional; install with `python3 -m pip install PyYAML` for YAML-backed helper scripts",
        required=False,
    )


def node_is_relevant(root: Path) -> bool:
    return any(
        path.exists()
        for path in (
            root / "desktop/macos/agent/package.json",
            root / "desktop/macos/pi-mono-extension/package.json",
            root / "desktop/macos/agent-cloud/package.json",
        )
    )


def parse_port(raw_port: str) -> int | None:
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        return None
    if port < 1 or port > 65535:
        return None
    return port


def automation_token(port: int) -> str | None:
    token = os.environ.get("OMI_AUTOMATION_TOKEN", "").strip()
    if token:
        return token
    token_file = Path(
        os.environ.get("OMI_AUTOMATION_TOKEN_FILE")
        or os.path.join(os.environ.get("TMPDIR", "/tmp"), f"omi-automation-{port}.token")
    )
    try:
        token = token_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return token or None


def check_bridge(raw_port: str, required: bool) -> CheckResult:
    if not required:
        return CheckResult("automation bridge", "SKIP", "pass --require-bridge to check reachability", required=False)
    port = parse_port(raw_port)
    if port is None:
        return CheckResult("automation bridge", "FAIL", f"invalid automation port: {raw_port!r}")
    token = automation_token(port)
    if not token:
        return CheckResult(
            "automation bridge",
            "FAIL",
            f"missing automation token for port {port}; launch a non-prod bundle or set OMI_AUTOMATION_TOKEN",
        )
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/state",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return CheckResult("automation bridge", "FAIL", f"port {port} not reachable: {exc.reason}")
    except TimeoutError:
        return CheckResult("automation bridge", "FAIL", f"port {port} timed out")
    result = bridge_payload_result(payload, port)
    if result is not None:
        return result
    return CheckResult("automation bridge", "PASS", f"reachable on 127.0.0.1:{port}")


def bridge_payload_result(payload: str, port: int) -> CheckResult | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return CheckResult("automation bridge", "FAIL", "bridge returned non-JSON response")
    if data.get("ok") is not True:
        return CheckResult(
            "automation bridge",
            "FAIL",
            f"bridge did not return ok=true: {data.get('error', 'unknown error')}",
        )
    return None


def default_auth_file(root: Path) -> Path:
    return root / "desktop/macos/tmp/desktop-auth.json"


def auth_value(data: dict, key: str):
    value = data.get(key)
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def check_auth_seed(path: Path, required: bool) -> CheckResult:
    if not required:
        return CheckResult("auth seed", "SKIP", "pass --require-auth-seed to require desktop auth seed", required=False)
    if not path.exists():
        return CheckResult("auth seed", "FAIL", f"missing {path}; run `cd desktop/macos && ./scripts/omi-auth-dump.sh`")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult("auth seed", "FAIL", f"could not parse {path}: {exc}")
    signed_in = str(auth_value(data, "auth_isSignedIn")).lower() in {"1", "true", "yes"}
    has_token = bool(auth_value(data, "auth_idToken"))
    if not signed_in or not has_token:
        return CheckResult("auth seed", "FAIL", f"{path} does not contain signed-in auth_idToken data")
    email = auth_value(data, "auth_userEmail") or "unknown email"
    return CheckResult("auth seed", "PASS", f"{path} signed in as {email}")


def collect_checks(args: argparse.Namespace, root: Path) -> list[CheckResult]:
    checks = [
        check_tool("xcrun SwiftPM", ["xcrun", "swift", "--version"]),
        check_tool("cargo", ["cargo", "--version"]),
        check_pyyaml(),
    ]
    if args.skip_node:
        checks.append(CheckResult("node", "SKIP", "--skip-node was passed", required=False))
        checks.append(CheckResult("npm", "SKIP", "--skip-node was passed", required=False))
    elif node_is_relevant(root):
        checks.append(check_tool("node", ["node", "--version"]))
        checks.append(check_tool("npm", ["npm", "--version"]))
    else:
        checks.append(CheckResult("node/npm", "SKIP", "no desktop Node package.json found", required=False))

    if args.skip_agent_swift:
        checks.append(CheckResult("agent-swift", "SKIP", "--skip-agent-swift was passed", required=False))
    else:
        checks.append(check_tool("agent-swift", ["agent-swift", "--version"]))

    auth_file = Path(args.auth_file).expanduser() if args.auth_file else default_auth_file(root)
    checks.append(check_bridge(args.port, args.require_bridge))
    checks.append(check_auth_seed(auth_file, args.require_auth_seed))
    return checks


def print_results(checks: list[CheckResult]) -> int:
    for check in checks:
        print(f"{check.status:4} {check.name}: {check.detail}")
    failures = [check for check in checks if check.status == "FAIL" and check.required]
    if failures:
        print(f"FAIL: {len(failures)} required desktop verification prerequisite(s) failed.", file=sys.stderr)
        return 1
    print("OK: desktop verification preflight passed.")
    return 0


def main() -> int:
    args = parse_args()
    root = repo_root(args.root)
    return print_results(collect_checks(args, root))


if __name__ == "__main__":
    sys.exit(main())
