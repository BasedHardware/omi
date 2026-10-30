#!/usr/bin/env python3
"""Plan an approved physical/profile smoke run; collect its driver response offline.

This tool never launches Flutter, installs an app, or submits a cloud test.
It does not certify seeded product scenarios or authenticate device provenance.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import shlex
import sys
import uuid

APP = Path(__file__).resolve().parents[1]
TARGET = "integration_test/perf/device_smoke_main.dart"
SCHEMA = "omi-perf-device-smoke/v1"


def load(path):
    return json.loads(Path(path).read_text())


def physical_device(inventory, device_id):
    """Accept only an exact, connected Flutter --machine mobile entry."""
    if not isinstance(inventory, list) or not all(
        isinstance(d, dict) for d in inventory
    ):
        raise ValueError(
            "inventory must be the JSON array from flutter devices --machine"
        )
    matches = [d for d in inventory if d.get("id") == device_id]
    if len(matches) != 1:
        raise ValueError("device ID must match exactly one connected inventory entry")
    device = matches[0]
    platform = device.get("targetPlatform", "")
    if not isinstance(platform, str) or (
        platform != "ios" and not platform.startswith("android-")
    ):
        raise ValueError("only physical iOS/Android devices are supported")
    if device.get("emulator") is not False or device.get("isSupported") is not True:
        raise ValueError("device must be supported and explicitly emulator=false")
    if device.get("isConnected", True) is not True:
        raise ValueError("device is disconnected")
    return {
        "id": device_id,
        "name": device.get("name"),
        "platform": "ios" if platform == "ios" else "android",
    }


def plan(
    inventory,
    device_id,
    output_dir,
    target="smoke",
    mode="profile",
    flavor="dev",
    profile="local_dev",
):
    if target != "smoke":
        raise ValueError(
            "seeded perf_main.dart is debug-only: fixture auth trust and host filesystem prerequisites"
        )
    if mode != "profile" or (flavor, profile) != ("dev", "local_dev"):
        raise ValueError("requires --mode profile --flavor dev --profile local_dev")
    device = physical_device(inventory, device_id)
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise ValueError("output directory must be new; stale reports cannot be reused")
    run_id = str(uuid.uuid4())
    validator = [
        "bash",
        "scripts/validate_mobile_build_config.sh",
        "--flavor",
        "dev",
        "--profile",
        "local_dev",
    ]
    drive = [
        "flutter",
        "drive",
        "--no-pub",
        "--profile",
        "--no-dds",
        "--flavor",
        "dev",
        "--driver=test_driver/integration_test_driver.dart",
        f"--target={TARGET}",
        "--dart-define=OMI_APP_PROFILE=local_dev",
        f"--dart-define=PERF_DEVICE_RUN_ID={run_id}",
        "-d",
        device_id,
    ]
    command = (
        f"cd {shlex.quote(str(APP))} && "
        f"OMI_APP_PROFILE=local_dev {shlex.join(validator)} && "
        f"mkdir {shlex.quote(str(output))} && "
        f"OMI_PERF_DEVICE_OUTPUT_DIR={shlex.quote(str(output))} {shlex.join(drive)}"
    )
    return {
        "schema": "omi-perf-device-plan/v1",
        "scope": "standalone_shell_smoke",
        "approval": "pending_specific_device_access",
        "run_id": run_id,
        "device": device,
        "mode": mode,
        "flavor": flavor,
        "profile": profile,
        "target": TARGET,
        "output_dir": str(output),
        "command": command,
        "limitations": "Inventory is caller-supplied. Refresh before approval/execution. No production shell or seeded scenarios.",
    }


def collect(run_plan, response, drive_exit_code):
    if drive_exit_code != 0:
        raise ValueError(
            "flutter drive failed; retain response/logs for diagnosis, not a successful smoke"
        )
    if (
        run_plan.get("schema") != "omi-perf-device-plan/v1"
        or run_plan.get("target") != TARGET
    ):
        raise ValueError("expected a standalone smoke plan")
    if (run_plan.get("mode"), run_plan.get("flavor"), run_plan.get("profile")) != (
        "profile",
        "dev",
        "local_dev",
    ):
        raise ValueError("plan must specify profile/dev/local_dev")
    report = response.get("perf_device_smoke") if isinstance(response, dict) else None
    if not isinstance(report, dict):
        raise ValueError(
            "missing perf_device_smoke; seeded/host scorecards are not accepted"
        )
    expected = {
        "schema": SCHEMA,
        "scope": "standalone_shell_smoke",
        "build_mode": "profile",
        "run_id": run_plan["run_id"],
        "platform": run_plan["device"]["platform"],
        "complete": True,
    }
    for key, value in expected.items():
        if type(report.get(key)) is not type(value) or report.get(key) != value:
            raise ValueError(f"response {key} does not match plan")
    count = report.get("frame_count")
    if type(count) is not int or count < 10:
        raise ValueError("need at least 10 genuine engine FrameTiming samples")
    for key in ("build_us", "raster_us", "total_us"):
        values = report.get(key)
        if not isinstance(values, list) or len(values) != count:
            raise ValueError(f"{key} must have frame_count samples")
        if any(
            type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values
        ):
            raise ValueError(f"{key} contains invalid durations")
    if not any(v > 0 for v in report["raster_us"]):
        raise ValueError(
            "no nonzero raster samples; cannot verify engine raster capture"
        )
    if any(
        t < max(b, r)
        for b, r, t in zip(report["build_us"], report["raster_us"], report["total_us"])
    ):
        raise ValueError("total duration is shorter than a constituent phase")
    return {
        "schema": "omi-perf-device-collection/v1",
        "scope": "standalone_shell_smoke",
        "run_id": run_plan["run_id"],
        "device": run_plan["device"],
        "report": report,
        "claim": "profile smoke artifact validated; no product-scenario performance verdict",
        "provenance": "caller-supplied inventory, exit code and driver response; not a signed device attestation",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    planner = sub.add_parser(
        "plan", help="offline dry run only; never executes printed commands"
    )
    planner.add_argument("--inventory", required=True, type=Path)
    planner.add_argument("--device-id", required=True)
    planner.add_argument("--output-dir", required=True, type=Path)
    planner.add_argument("--plan-file", required=True, type=Path)
    planner.add_argument("--target", choices=("smoke", "seeded"), default="smoke")
    planner.add_argument("--mode", default="profile")
    planner.add_argument("--flavor", default="dev")
    planner.add_argument("--profile", default="local_dev")
    collector = sub.add_parser(
        "collect", help="validate and copy a response after a separately approved run"
    )
    collector.add_argument("--plan-file", required=True, type=Path)
    collector.add_argument("--drive-exit-code", required=True, type=int)
    collector.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            result = plan(
                load(args.inventory),
                args.device_id,
                args.output_dir,
                args.target,
                args.mode,
                args.flavor,
                args.profile,
            )
            result["inventory_sha256"] = hashlib.sha256(
                args.inventory.read_bytes()
            ).hexdigest()
            with args.plan_file.open("x") as destination:
                json.dump(result, destination, indent=2)
            print("DRY RUN. Device access approval required before executing:")
            print(result["command"])
        else:
            run_plan = load(args.plan_file)
            source = Path(run_plan["output_dir"]) / "integration_response_data.json"
            result = collect(run_plan, load(source), args.drive_exit_code)
            result["response_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            with args.output.open("x") as destination:
                json.dump(result, destination, indent=2)
            print(f"Validated standalone smoke only: {args.output}")
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
