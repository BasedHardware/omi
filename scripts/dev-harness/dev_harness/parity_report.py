"""What still differs between this stack and production, in one printout.

``make dev-parity`` compares the stack's configuration with its source: the
production snapshot when one is configured, else this checkout's deploy files.
It says which commit each production service runs and how far this checkout is
from it, how many behaviour settings differ (the target is zero), which
settings were replaced by local infrastructure, which production processes
have no local counterpart, and what can never match. Names and counts only;
no setting value is printed. Exit 0 means nothing above the standing
substitutions differs.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from . import config, local_scheduler, parity_stack, prod_parity

# Substitutions no snapshot can remove. Stated so nobody mistakes them for parity.
STANDING_SUBSTITUTIONS = (
    "speech and speaker models run on this machine's CPU in FP32 (production: GPUs); text, speed and latency can differ",
    "Firestore, Auth and Redis are local emulators; contention, indexes and latency differ",
    "object storage is a local folder (backend/utils/other/local_storage.py)",
    "Cloud Tasks and Cloud Scheduler are the harness's local queue and timer",
    "hosted GPU services (diarization, speaker embedding, VAD, language gate) are unreachable by design",
    "real vendor accounts (speech, LLM) are the developer's own keys, with their own limits",
    "telemetry, payments and messaging channels are switched off",
    "the test account's plan and language are whatever the emulator holds",
)


# Where a code difference can change what happens to a recording.
RECORDING_PATHS = (
    "backend/utils/batch_pipeline",
    "backend/utils/sync",
    "backend/utils/stt",
    "backend/utils/capture",
    "backend/routers/sync.py",
    "backend/routers/batch_pipeline.py",
    "backend/routers/transcribe.py",
    "backend/database",
    "backend/diarizer",
    "backend/pusher",
    "backend/config",
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
    return result.stdout.strip() if result.returncode == 0 else ""


def _age(captured_at: str) -> str:
    try:
        seconds = time.time() - time.mktime(time.strptime(captured_at, "%Y-%m-%dT%H:%M:%SZ")) + time.timezone
    except ValueError:
        return "unknown age"
    hours = max(0, seconds) / 3600
    return f"{hours:.1f} h old" if hours < 48 else f"{hours / 24:.1f} days old"


def _code_lines(cfg: config.HarnessConfig, snapshot) -> tuple[list[str], int]:
    """How far this checkout is from the commit each production service runs."""
    lines: list[str] = []
    findings = 0
    root = cfg.repo_root
    head = _git(root, "rev-parse", "HEAD")
    changed = [line.split(maxsplit=1)[-1] for line in _git(root, "status", "--short", "--", "backend").splitlines()]
    for service in (*prod_parity.SERVICES, "batch-worker"):
        live = snapshot.services.get(service)
        production = live.commit if live else ""
        if not production:
            verdict = "production commit unknown (image published by digest)"
            findings += 1
        elif head.startswith(production) or production.startswith(head):
            verdict = "same commit as production"
        else:
            behind = _git(root, "rev-list", "--count", f"{head}..{production}") or "?"
            ahead = _git(root, "rev-list", "--count", f"{production}..{head}") or "?"
            touched = _git(root, "diff", "--name-only", production, head, "--", *RECORDING_PATHS).splitlines()
            verdict = (
                f"DIFFERENT commit (production is {behind} commits ahead, this checkout {ahead} ahead); "
                f"{len(touched)} recording-path file(s) differ{': ' + ', '.join(touched[:4]) if touched else ''}"
            )
            findings += 1 if touched else 0
        lines.append(f"  {service}: this checkout {head[:10]} vs production {production[:10] or '?'}: {verdict}")
    if changed:
        lines.append(f"  {len(changed)} uncommitted backend file change(s): {', '.join(changed[:6])}")
    return lines, findings


def build(cfg: config.HarnessConfig) -> tuple[str, int]:
    """The report and the number of findings that mean "not production behaviour"."""
    lines: list[str] = []
    findings = 0
    if not parity_stack.enabled():
        return (
            f"This stack does not run the prod-parity profile ({prod_parity.PROFILE_ENV}={prod_parity.PROD_PARITY}): "
            "it is not a production replica.",
            1,
        )
    snapshot = parity_stack.production_snapshot()
    if snapshot is None:
        findings += 1
        lines.append(
            "Settings source: this checkout's deploy files (no production snapshot). They describe this "
            "checkout, which can be days behind what production runs, and they do not hold the load "
            "balancer's rules or the live rollout document."
        )
    else:
        lines.append(f"Settings source: production snapshot of {snapshot.captured_at} ({_age(snapshot.captured_at)})")
        if snapshot.unreadable:
            findings += len(snapshot.unreadable)
            lines.append(f"  could not be read: {', '.join(snapshot.unreadable)}")
        lines.append("")
        lines.append("Code")
        code_lines, code_findings = _code_lines(cfg, snapshot)
        lines.extend(code_lines)
        findings += code_findings

    lines.append("")
    lines.append("Behaviour settings")
    topology = parity_stack.topology(cfg)
    composed = prod_parity.compose(cfg.repo_root, topology)
    declared = prod_parity.declared_production(cfg.repo_root)
    differences = prod_parity.logic_differences(cfg.repo_root, composed)
    findings += len(differences)
    lines.append(f"  settings that differ from the source: {len(differences)}")
    for service, name, problem in differences[:20]:
        lines.append(f"      {service}: {name} ({problem})")
    for service in prod_parity.SERVICES:
        live = declared[service]
        replaced = sum(
            1
            for name, value in live.values.items()
            if prod_parity.is_infrastructure(name) and composed[service].get(name) != value
        )
        lines.append(
            f"  {service}: {len(live.values)} settings, {replaced} replaced by local infrastructure, "
            f"{len(live.bound)} bound from secrets in production"
        )

    lines.append("")
    if snapshot is None:
        lines.append("Routing: built-in path map (websockets to listen, upload routes to sync, the rest to backend)")
        lines.append(f"Rollout document: seeded from {parity_stack.PRODUCTION_RAMP}")
    else:
        lines.append(f"Routing: {len(snapshot.routes)} load-balancer path rules, default {snapshot.default_route}")
        ramp = ((snapshot.rollout_ramp or {}).get("envs") or {}).get("prod") or {}
        lines.append(f"Rollout document: {ramp.get('percents')} legacy_sync={ramp.get('legacy_sync')}")

    lines.append("")
    lines.append("Processes")
    reason = parity_stack.batch_worker_unavailable(cfg)
    if reason is None:
        lines.append(f"  batch speech worker: {parity_stack.batch_worker_count()} CPU process(es)")
    else:
        lines.append(f"  batch speech worker: NOT RUNNING ({reason}); recordings are never transcribed")
        findings += 1
    selected = os.environ.get(local_scheduler.JOBS_ENV, "").strip().lower()
    if snapshot is None:
        lines.append("  record seal worker: not started (its settings are only in a production snapshot)")
        lines.append(
            "  scheduled jobs: "
            + (
                "every backend-service job in the checkout"
                if selected == "all"
                else ", ".join(local_scheduler.RECORDING_JOBS)
            )
        )
    else:
        pump = snapshot.services.get("backend-projection-pump")
        if pump is not None:
            active = pump.values.get("BATCH_PIPELINE_PROJECTION_PUMP_ENABLED", "").lower() == "true"
            lines.append(
                f"  backend-projection-pump: {'ACTIVE in production' if active else 'deployed but switched off'}; "
                "no local counterpart"
            )
            findings += int(active)
        seal = snapshot.services.get("record-seal-worker")
        if seal is not None:
            repairing = seal.values.get("RECORD_SEAL_REPAIR_ENABLED", "").lower() == "true"
            state = "repairing" if repairing else "deployed with repair switched off"
            lines.append(f"  record seal worker: {state} in production; runs here with the same settings")
        live_jobs = {job["name"] for job in snapshot.scheduler_jobs if job.get("state") == "ENABLED"}
        local_jobs = live_jobs if selected == "all" else live_jobs & set(local_scheduler.RECORDING_JOBS)
        lines.append(
            f"  scheduled jobs: production runs {len(live_jobs)}, this stack runs {len(local_jobs)} "
            f"({', '.join(sorted(local_jobs)) or 'none'})"
        )

    lines.append("")
    lines.append("Standing substitutions (cannot match production)")
    lines.extend(f"  - {item}" for item in STANDING_SUBSTITUTIONS)
    lines.append("")
    lines.append(
        "Verdict: "
        + (
            "matches the production snapshot on code and behaviour settings."
            if findings == 0
            else f"{findings} point(s) above differ from production behaviour or could not be verified."
        )
    )
    return "\n".join(lines), findings
