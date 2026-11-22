#!/usr/bin/env python3
"""Build and boot real main() in Linux/amd64 Docker; never access devices/keys."""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time
import uuid

IMAGE = (
    "ghcr.io/zephyrproject-rtos/ci:v0.26.13@sha256:"
    "b0ac6334d1926cd0971a0a444f7adc6dd020e88ee3ce865aa070b6475a3ac4eb"
)
NCS_SHA = "7787b264984022cda64d9629278942053e6462a5"
ZEPHYR_SHA = "1f8f3dc291420c70cd39e77a5cdc954561d4a08f"
ALIVE = "SIM: main loop alive (2 watchdog feeds)"


def checked(argv, *, timeout, **kwargs):
    print("+", " ".join(map(str, argv)), flush=True)
    # Own the process group, including compilers. No orphan build on timeout.
    proc = subprocess.Popen(list(map(str, argv)), start_new_session=True, **kwargs)
    try:
        code = proc.wait(timeout=timeout)
        if code:
            raise RuntimeError(f"command exited {code}: {argv[0]}")
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)


def clone(url, branch, dest, timeout):
    """Publish only a finished clone, so an interrupted one can't pass as present."""
    if dest.exists():
        return
    partial = dest.with_name(dest.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    checked(["git", "clone", "--depth=1", "--branch", branch, url, partial], timeout=timeout)
    partial.rename(dest)


def prepare_sdk(cache):
    """Shallow, SHA-checked NCS manifest + Zephyr trees under cache; sets build env."""
    # Deliberately no .west workspace: NCS's full manifest imports BabbleSim
    # metadata even when only native_sim is requested. These two shallow trees
    # are the exact NCS manifest and Zephyr revisions, without unrelated modules.
    sdk = cache / "ncs-v2.9.0-standalone"
    sdk.mkdir(exist_ok=True)
    os.environ.update(
        XDG_CACHE_HOME=str(cache / "cache"),
        CCACHE_DIR=str(cache / "ccache"),
        ZEPHYR_TOOLCHAIN_VARIANT="host",
        ZEPHYR_BASE=str(sdk / "zephyr"),
    )
    clone("https://github.com/nrfconnect/sdk-nrf", "v2.9.0", sdk / "nrf", 300)
    checked(["git", "-C", sdk / "nrf", "diff", "--exit-code", "HEAD"], timeout=120)
    if subprocess.check_output(["git", "-C", sdk / "nrf", "rev-parse", "HEAD"], text=True).strip() != NCS_SHA:
        raise RuntimeError("NCS manifest is not the expected v2.9.0 revision")
    # Only the pinned NCS Zephyr tree is needed. No radio, bootloader, Nordic
    # binary libraries, signing dependencies or unrelated SDK modules fetched.
    clone("https://github.com/nrfconnect/sdk-zephyr", "v3.7.99-ncs2", sdk / "zephyr", 600)
    if subprocess.check_output(["git", "-C", sdk / "zephyr", "rev-parse", "HEAD"], text=True).strip() != ZEPHYR_SHA:
        raise RuntimeError("unexpected Zephyr revision")
    checked(["git", "-C", sdk / "zephyr", "diff", "--exit-code", "HEAD"], timeout=120)
    return sdk


def inside(cache):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("native_sim/native/64 needs Linux x86_64 in this runner")
    sim = Path(__file__).resolve().parent
    kit = sim.parents[1] / "tools/cv1"
    sys.path.insert(0, str(kit))
    from startup_replay import observe

    for name in ("boot.log", "observation.json"):
        (cache / name).unlink(missing_ok=True)
    sdk = prepare_sdk(cache)
    build = cache / "build"
    checked(["cmake", "-S", sim, "-B", build, "-GNinja",
             "-DBOARD=native_sim/native/64", f"-DZEPHYR_MODULES={sdk / 'zephyr'}",
             f"-DUSER_CACHE_DIR={cache / 'cache'}", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"], timeout=180)
    checked(["cmake", "--build", build, "--parallel", "4"], timeout=600)
    runtime = cache / "runtime-boot"
    shutil.rmtree(runtime, ignore_errors=True)
    runtime.mkdir()
    log = cache / "boot.log"
    # Fresh flash, cold RAM, no boot.cfg: a plain power-on with nothing pressed.
    with log.open("w") as output:
        checked([build / "zephyr/zephyr.exe", "-stop_at=5"], cwd=runtime,
                stdout=output, stderr=subprocess.STDOUT, timeout=30)
    text = log.read_text()
    print(text, flush=True)
    report = observe(text)
    report.update(
        evidence_category="simulated_startup",
        real_main_loop_observed=ALIVE in text,
        stubbed=["battery", "SD", "storage", "BLE transport", "microphone", "codec", "LED",
                 "SPI flash", "IMU", "SMP callback delivery"],
        simulated=["watchdog (simulated time)", "reset register", "button/charger pins (gpio_emul)"],
        ncs_revision=NCS_SHA, zephyr_revision=ZEPHYR_SHA,
    )
    if report["state"] != "initialization_reported" or not report["real_main_loop_observed"]:
        raise RuntimeError("startup milestones/errors/main loop check failed; see boot.log")
    (cache / "observation.json").write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True,
                        help="dedicated scratch directory outside the checkout")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="whole container deadline in seconds (default: 1800)")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    cache = args.cache.expanduser().resolve()
    if args.inside:
        cache.mkdir(parents=True, exist_ok=True)
        inside(cache)
        return
    repo = Path(__file__).resolve().parents[4]
    if cache == repo or repo in cache.parents:
        parser.error("--cache must be outside the checkout")
    cache.mkdir(parents=True, exist_ok=True)
    name = "omi-cv1-sim-" + uuid.uuid4().hex[:12]
    started = time.monotonic()
    try:
        checked(["docker", "run", "--rm", "--name", name,
                 "--platform", "linux/amd64", "--cpus", "4", "--memory", "8g",
                 "--mount", f"type=bind,src={repo},dst=/src,readonly",
                 "--mount", f"type=bind,src={cache},dst=/cache",
                 "-e", "PYTHONDONTWRITEBYTECODE=1", IMAGE,
                 "python3", "/src/omi/firmware/omi/sim/run.py", "--inside", "--cache", "/cache"],
                timeout=args.timeout)
    finally:
        # A killed docker client alone would leave its container running.
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15)
        print(f"Elapsed: {time.monotonic() - started:.1f}s; evidence: {cache}", flush=True)


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
