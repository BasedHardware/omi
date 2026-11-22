#!/usr/bin/env python3
"""Run the CV1 simulator scenario suite (and optional fuzz batch) and write
sim-report.json. Builds and boots in the release workflow's digest-pinned
Linux/amd64 image; never touches devices, keys or the network beyond the
pinned SDK clones. See README.md ("Scenario suite").

  python3 omi/firmware/omi/sim/scenario_runner.py --cache /abs/scratch/dir
  python3 omi/firmware/omi/sim/scenario_runner.py --cache ... --only 'safe/*'
  python3 omi/firmware/omi/sim/scenario_runner.py --cache ... --baseline

--baseline checks each scenario's recorded 3.0.23 behaviour (baseline_bug)
instead of the current expectation, skips `fix`-only scenarios and runs guards
unchanged; use it on the 3.0.23 tree to prove the simulator reproduces the
field bugs.
"""
import argparse
import concurrent.futures
import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid

SIM = Path(__file__).resolve().parent
sys.path.insert(0, str(SIM))
import power_model  # noqa: E402
import run as spike  # noqa: E402  (pinned image/SDK helpers)

SCENARIOS = SIM / "scenarios"
BUILDS = SIM / "builds"
REPORT_SCHEMA = 1
BOOT_WALL_TIMEOUT = 300  # emulated amd64 on Apple Silicon runs ~1x real time


def build_names(scenarios):
    return sorted({s["build"] for s in scenarios} | {"default"})


def build(cache, sdk, name, jobs):
    out = cache / "builds" / name
    command = ["cmake", "-S", SIM, "-B", out, "-GNinja", "-DBOARD=native_sim/native/64",
               f"-DZEPHYR_MODULES={sdk / 'zephyr'}", f"-DUSER_CACHE_DIR={cache / 'cache'}"]
    if name != "default":
        conf = BUILDS / f"{name}.conf"
        if not conf.is_file():
            raise RuntimeError(f"unknown build {name!r}: add sim/builds/{name}.conf")
        if conf.read_text().startswith("# dev-build"):
            command += ["-DOMI_DEVELOPMENT_BUILD=ON", "-DCMAKE_BUILD_TYPE=Debug"]
        command.append(f"-DEXTRA_CONF_FILE={conf}")
    spike.checked(command, timeout=300)
    spike.checked(["cmake", "--build", out, "--parallel", str(jobs)], timeout=1200)
    return out / "zephyr/zephyr.exe"


def run_scenario(scenario, exe, cache, mode):
    run_dir = cache / "runs" / scenario["id"].replace("/", "__")
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    logs = []

    def execute(index, cfg, stop_ms, warm):
        (run_dir / "boot.cfg").write_text(cfg)
        (run_dir / f"boot-{index}.cfg").write_text(cfg)
        if not warm:
            (run_dir / "retained.bin").unlink(missing_ok=True)
        log_path = run_dir / f"boot-{index}.log"
        with log_path.open("w") as output:
            proc = subprocess.run([exe, f"-stop_at={stop_ms / 1000:.3f}"], cwd=run_dir, stdout=output,
                                  stderr=subprocess.STDOUT, timeout=BOOT_WALL_TIMEOUT)
        text = log_path.read_text(errors="replace")
        if proc.returncode != 0:
            raise power_model.ScenarioError(f"boot {index}: zephyr.exe exited {proc.returncode}")
        result = power_model.parse_boot_log(text)
        result["log"] = text
        logs.append(str(log_path.relative_to(cache)))
        return result

    started = time.monotonic()
    expect = scenario["expect"]
    if mode == "baseline" and "baseline_bug" in scenario:
        expect = scenario["baseline_bug"]["expect"]
    elif mode == "baseline" and "fix" in scenario["tags"]:
        return None  # new 3.0.24 behaviour with no 3.0.23 counterpart
    try:
        outcome = power_model.run_power_model(scenario, execute)
        failures = power_model.check(expect, outcome)
    except (power_model.ScenarioError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        outcome, failures = {"boots": [], "final": "error"}, [f"error: {exc}"]
    row = {
        "id": scenario["id"],
        "summary": scenario["summary"],
        "tags": scenario["tags"],
        "committee": scenario.get("committee", []),
        "build": scenario["build"],
        "mode": mode,
        "verdict": "fail" if failures else "pass",
        "failures": failures,
        "final": outcome["final"],
        "boots": [{k: b[k] for k in ("index", "start_ms", "reset", "warm", "exit", "uptime_ms")}
                  | {"safe": b["state"].get("safe"), "latch_reason": b["state"].get("latch_reason"),
                     "muted": b["state"].get("muted")} for b in outcome["boots"]],
        "logs": logs,
        "wall_seconds": round(time.monotonic() - started, 2),
    }
    return row


def inside(args):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("native_sim/native/64 needs Linux x86_64 in this runner")
    cache = args.cache
    sdk = spike.prepare_sdk(cache)
    files = power_model.discover(SCENARIOS, args.only)
    scenarios = [power_model.load_scenario(f, SCENARIOS) for f in files]
    if not scenarios:
        raise RuntimeError("no scenarios selected")
    exes = {name: build(cache, sdk, name, args.jobs) for name in build_names(scenarios)}
    modes = ["baseline"] if args.baseline else ["current"]
    rows = []
    lock = threading.Lock()

    def one(scenario):
        row = run_scenario(scenario, exes[scenario["build"]], cache, modes[0])
        if row:
            with lock:
                print(f"{row['verdict'].upper():4} {row['id']}" +
                      "".join(f"\n       {f}" for f in row["failures"]), flush=True)
        return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        rows = [r for r in pool.map(one, scenarios) if r]
    fuzz = None
    if args.fuzz_seeds:
        import fuzz as fuzz_lane

        fuzz = fuzz_lane.run_batch(args.fuzz_seeds, args.fuzz_start, exes, cache, run_scenario, args.jobs)
    failed = [r["id"] for r in rows if r["verdict"] != "pass"]
    if fuzz and fuzz["verdict"] != "pass":
        failed.append("fuzz")
    report = {
        "schema_version": REPORT_SCHEMA,
        "kind": "omi-cv1-sim-report",
        "evidence_category": "simulated",
        "verdict": "fail" if failed else "pass",
        "mode": modes[0],
        "source_sha": args.source_sha,
        "firmware_version": args.firmware_version,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "runner_image": spike.IMAGE,
        "ncs_revision": spike.NCS_SHA,
        "zephyr_revision": spike.ZEPHYR_SHA,
        "lanes": ["fast"],
        "selection": args.only or ["*"],
        "counts": {"scenarios": len(rows), "passed": len(rows) - len([r for r in rows if r["verdict"] != "pass"]),
                   "failed": len([r for r in rows if r["verdict"] != "pass"])},
        "failed": failed,
        "scenarios": rows,
        "fuzz": fuzz,
        "not_covered": ["RF/PHY and the BLE controller", "MCUboot and image signing", "network core",
                        "real SD card timing", "current draw", "audio codec correctness"],
    }
    out = cache / "sim-report.json"
    out.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(f"{report['counts']['passed']}/{report['counts']['scenarios']} scenarios passed; "
          f"fuzz={fuzz['verdict'] if fuzz else 'not run'}; report: {out}", flush=True)
    if failed:
        raise RuntimeError("simulator gate failed: " + ", ".join(failed))


def firmware_version(repo):
    for line in (repo / "omi/firmware/omi/omi.conf").read_text().splitlines():
        if line.startswith("CONFIG_BT_DIS_FW_REV_STR="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=Path, required=True, help="dedicated scratch directory outside the checkout")
    parser.add_argument("--only", action="append", help="scenario id glob (repeatable), e.g. 'safe/*'")
    parser.add_argument("--baseline", action="store_true", help="check recorded 3.0.23 behaviour instead")
    parser.add_argument("--fuzz-seeds", type=int, default=0, help="number of fuzz chains to run")
    parser.add_argument("--fuzz-start", type=int, default=1, help="first fuzz seed")
    parser.add_argument("--jobs", type=int, default=2, help="parallel builds/boots (default 2)")
    parser.add_argument("--timeout", type=int, default=3600, help="whole container deadline, seconds")
    parser.add_argument("--report", type=Path, help="copy sim-report.json here when done")
    parser.add_argument("--source-sha", help=argparse.SUPPRESS)
    parser.add_argument("--firmware-version", help="version to record (default: omi.conf)")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    cache = args.cache.expanduser().resolve()
    args.cache = cache
    if args.inside:
        cache.mkdir(parents=True, exist_ok=True)
        inside(args)
        return
    repo = Path(__file__).resolve().parents[4]
    if cache == repo or repo in cache.parents:
        parser.error("--cache must be outside the checkout")
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "sim-report.json").unlink(missing_ok=True)
    sha = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    # omi.conf is excluded: the release workflow's prepare step stamps the build
    # version there, and the simulator app never reads it (sim/prj.conf only).
    dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--", "omi/firmware",
                            ":!omi/firmware/omi/omi.conf"], capture_output=True, text=True).stdout.strip()
    source = (sha or "unknown") + ("-dirty" if dirty else "")
    version = args.firmware_version or firmware_version(repo) or "unknown"
    name = "omi-cv1-scen-" + uuid.uuid4().hex[:12]
    forward = ["--jobs", str(args.jobs), "--fuzz-seeds", str(args.fuzz_seeds), "--fuzz-start", str(args.fuzz_start),
               "--source-sha", source, "--firmware-version", version]
    for pattern in args.only or []:
        forward += ["--only", pattern]
    if args.baseline:
        forward.append("--baseline")
    started = time.monotonic()
    try:
        spike.checked(["docker", "run", "--rm", "--name", name, "--platform", "linux/amd64",
                       "--cpus", str(max(2, args.jobs)), "--memory", "8g",
                       "--mount", f"type=bind,src={repo},dst=/src,readonly",
                       "--mount", f"type=bind,src={cache},dst=/cache",
                       "-e", "PYTHONDONTWRITEBYTECODE=1", spike.IMAGE,
                       "python3", "/src/omi/firmware/omi/sim/scenario_runner.py", "--inside", "--cache", "/cache"]
                      + forward, timeout=args.timeout)
    finally:
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=15)
        print(f"Elapsed: {time.monotonic() - started:.1f}s; evidence: {cache}", flush=True)
        if args.report and (cache / "sim-report.json").exists():
            shutil.copyfile(cache / "sim-report.json", args.report)


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt

    import signal

    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt, power_model.ScenarioError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
