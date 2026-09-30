"""Unified mobile verification entrypoint (SCA-490 / C4).

One command surface over the proven mobile lanes:

    mobile-verify select   [--changed-files FILE | --paths P ...]
    mobile-verify doctor   [--platform P] [--min-free-gb N]
    mobile-verify fast     [--changed-files FILE | --paths P ...]
                           [--filter NAME | --all] [--runs N] [--evidence-dir DIR]
    mobile-verify smoke    [--session ID]
    mobile-verify physical

This module owns selection, lane admission, failure classification, receipt
validation and the lane summary — never a second journey runner. Journey
execution is delegated to the one canonical runner
(``app/integration_test/journeys/run_journeys.sh``, SCA-488/C2) and session
infrastructure to the C1 session CLI (``dev_harness.mobile_session``). Both
are consumed exactly as integrated on the parent checkpoint.

Fail-closed semantics (exit codes, mirroring the session CLI):

- 0  — requested lane ran and every selected journey passed with >0 executed
- 1  — executed test failures (or doctor reports degraded)
- 2  — blocked: missing infrastructure/setup, timeout, or an admission gate
       (physical lane, missing simulator). Blocked is NEVER success.
- 64 — usage error
- 65 — selection drift: an explicit filter or rule matched no journey

Every lane writes a ``verify-receipt.json`` lane summary that binds source
identity (git SHA + dirty digest via ``session-evidence-v1`` helpers), runner
versions, the selection decision, per-journey accounting validated against the
session-evidence-v1 accounting rules, totals, and the exact rerun command.
Machine pass results come only from executed test assertions observed in
receipts/logs — this module never authors a pass it did not witness.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import mobile_doctor, session_evidence

CLI_VERSION = "0.1.0"
LANE_RECEIPT_SCHEMA = "mobile-verify/v1"
JOURNEYS_DIR = Path("app") / "integration_test" / "journeys"
RUNNER_RELPATH = JOURNEYS_DIR / "run_journeys.sh"
SESSION_CLI_RELPATH = Path("scripts/dev-harness/mobile-session.sh")

EXIT_OK = 0
EXIT_TEST_FAILURES = 1
EXIT_BLOCKED = 2
EXIT_USAGE = 64
EXIT_SELECTION_DRIFT = 65

DEFAULT_JOURNEY_TIMEOUT_S = 900

# Log markers -> failure class. The runner already retries pure launch-infra
# failures once; whatever still fails is classified here so a contributor can
# tell a code failure from a broken toolchain.
COMPILE_MARKERS = (
    "Failed to compile",
    "Compilation failed",
    "Error: Couldn't resolve",
    "Target of URI doesn't exist",
)
INFRA_MARKERS = (
    "Failed to load",
    "Failed to build bundle",
    "Failed to launch app",
    "No supported devices connected",
    "flutter: command not found",
)
ZERO_EXECUTION_MARKERS = ("No tests ran",)
TEST_FAILURE_MARKERS = ("Some tests failed",)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_evidence_dir(raw: str | None, *, cwd: Path | None = None) -> Path | None:
    """Resolve an evidence directory against the invocation working directory.

    Empty/unset becomes None so the caller can fall back to a temp dir.
    Relative paths are joined to ``cwd`` (default: process cwd) and made
    absolute before they are handed to the journey runner, which ``cd``s into
    ``app/`` — a relative ``--evidence-dir`` would otherwise write receipts
    under ``app/`` while aggregation looks next to the invocation.
    """
    text = (raw or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = (cwd or Path.cwd()) / path
    return path.resolve()


def classify_log_text(text: str) -> str:
    """Classify a runner log tail into compile/infra/zero-execution/test/unknown."""
    if any(marker in text for marker in COMPILE_MARKERS):
        return "compile"
    if any(marker in text for marker in ZERO_EXECUTION_MARKERS):
        return "zero-execution"
    if any(marker in text for marker in INFRA_MARKERS):
        return "infrastructure"
    if any(marker in text for marker in TEST_FAILURE_MARKERS):
        return "test"
    return "unknown"


JOURNEY_FILE_RE = re.compile(r"^j\d+_.*_test\.dart$")


def discover_journeys(repo_root: Path) -> tuple[str, ...]:
    """Discover journey stems mechanically (mirrors the runner's glob).

    A new ``j<N>_<behavior>_test.dart`` joins the suite by existing; the full
    suite (``ALL_JOURNEYS`` marker) is resolved from this discovery at
    selection time so no handwritten list can orphan a new journey.
    """
    journeys_dir = repo_root / JOURNEYS_DIR
    if not journeys_dir.is_dir():
        return ()
    return tuple(sorted(p.name for p in journeys_dir.iterdir() if JOURNEY_FILE_RE.match(p.name)))


ALL_JOURNEYS = "*"  # marker: resolve to the full discovered suite at select time


@dataclass(frozen=True)
class SelectionRule:
    """One path predicate -> the journeys whose behavior it can break."""

    name: str
    prefixes: tuple[str, ...]
    exact: tuple[str, ...] = ()
    journeys: tuple[str, ...] | str = ALL_JOURNEYS
    reason: str = ""


# Narrow rules name journey FAMILIES ("j1_", "j2_", ...) resolved against the
# discovered suite at selection time — never full stems baked at import. The
# discovery contract test fails if a family no longer exists, so a renamed or
# deleted journey cannot silently drop its lane, and a NEW journey family is
# always covered by the full-suite fallback below.
SELECTION_RULES: tuple[SelectionRule, ...] = (
    SelectionRule(
        name="journey-definition",
        prefixes=("app/integration_test/journeys/",),
        reason="a changed journey definition wakes the suite; the runner selects by discovery",
    ),
    SelectionRule(
        name="journey-support",
        prefixes=("app/integration_test/journeys/support/", "app/test/support/capture/"),
        journeys=ALL_JOURNEYS,
        reason="hermetic boot, fixture backend, and the C3 replay world are shared by every journey",
    ),
    SelectionRule(
        name="dev-controls-harness",
        prefixes=("app/lib/services/dev_controls/",),
        journeys=ALL_JOURNEYS,
        reason="semantic controls and named faults are the harness every journey drives",
    ),
    SelectionRule(
        name="http-egress",
        prefixes=("app/lib/backend/http/",),
        journeys=("j2_", "j4_"),
        reason="the client HTTP egress chokepoint carries chat send and blocked-request behavior",
    ),
    SelectionRule(
        name="conversation-detail",
        prefixes=("app/lib/pages/conversation_detail/",),
        exact=("app/lib/providers/conversation_provider.dart", "app/lib/backend/schema/conversation.dart"),
        journeys=("j1_",),
        reason="seeded conversation detail page, provider, and schema",
    ),
    SelectionRule(
        name="chat-page",
        prefixes=("app/lib/pages/chat/",),
        exact=("app/lib/providers/message_provider.dart",),
        journeys=("j2_",),
        reason="chat page and message provider carry the real send path",
    ),
    SelectionRule(
        name="memory-persistence",
        exact=("app/lib/providers/memories_provider.dart",),
        prefixes=("app/lib/pages/memories/",),
        journeys=("j3_",),
        reason="memory create/edit/reload provider path",
    ),
    SelectionRule(
        name="auth-session",
        prefixes=("app/lib/services/auth/", "app/lib/env/", "app/lib/pages/onboarding/"),
        exact=(
            "app/lib/services/auth_service.dart",
            "app/lib/providers/auth_provider.dart",
            "app/lib/flavors.dart",
        ),
        journeys=("j4_", "j2_"),
        reason="token lifecycle, re-mint, env profiles, and sign-in page feed session recovery",
    ),
    SelectionRule(
        name="capture-wal",
        prefixes=("app/lib/services/capture/", "app/lib/services/wals/", "app/lib/services/mic/"),
        journeys=("j5_",),
        reason="capture seams, WAL persistence, and native mic host carry interruption recovery",
    ),
    SelectionRule(
        name="app-shell",
        prefixes=(),
        exact=("app/lib/main.dart", "app/lib/utils/platform/platform_manager.dart"),
        journeys=ALL_JOURNEYS,
        reason="entrypoint wiring and platform identity are shared by every lane",
    ),
    SelectionRule(
        name="verify-surface",
        prefixes=("scripts/dev-harness/",),
        exact=(
            str(RUNNER_RELPATH),
            "contracts/session/session-evidence-v1.schema.json",
        ),
        journeys=ALL_JOURNEYS,
        reason="the runner, this selector, and the evidence contract are lane-wide authorities",
    ),
    # NOTE: no catch-all row for app/lib here — the unknown-impact fallback in
    # select_journeys is a first-class decision, not one more table entry.
)


def runner_list(repo_root: Path, *, bash: str = "bash") -> tuple[str, ...]:
    """Ask the canonical runner what it discovered (contract check, not a re-list)."""
    result = subprocess.run(  # noqa: S603
        [bash, str(repo_root / RUNNER_RELPATH), "--list"],
        capture_output=True,
        text=True,
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"runner --list failed ({result.returncode}): {result.stderr.strip()}")
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


_GENERATED_DART_SUFFIXES = (".g.dart", ".gen.dart", ".freezed.dart")


def _is_generated_dart(path: str) -> bool:
    return path.endswith(_GENERATED_DART_SUFFIXES) or path.startswith("app/lib/l10n/app_")


@dataclass
class Selection:
    selected: tuple[str, ...]
    fallback_full_suite: bool
    matched_rules: tuple[str, ...]
    unmatched_paths: tuple[str, ...]
    drift: list[str] = field(default_factory=list)


def select_journeys(repo_root: Path, paths: Sequence[str]) -> Selection:
    """Map changed paths onto the discovered journey suite.

    Unknown cross-cutting app/lib Dart falls back to the full suite; paths
    outside every rule select nothing (recorded, not an error). Rules naming a
    journey family that no longer exists are selection drift.
    """
    discovered = discover_journeys(repo_root)
    if not discovered:
        return Selection((), False, (), tuple(paths), drift=["no journey definitions discovered"])

    def resolve_families(families: tuple[str, ...] | str) -> tuple[str, ...]:
        """Resolve rule journey families (j2_, j5_) against the discovered suite."""
        if families == ALL_JOURNEYS:
            return discovered
        return tuple(sorted(j for j in discovered for family in families if j.startswith(family)))

    selected: set[str] = set()
    matched_rules: list[str] = []
    unmatched: list[str] = []
    fallback = False
    drift: list[str] = []

    for path in paths:
        normalized = path.strip()
        if not normalized:
            continue
        hit = False
        # An exact journey definition file selects exactly itself: the runner
        # executes it, and shared support is covered by the journey-support rule.
        if normalized.startswith("app/integration_test/journeys/") and JOURNEY_FILE_RE.match(Path(normalized).name):
            if normalized.rsplit("/", 1)[-1] in discovered:
                selected.add(normalized.rsplit("/", 1)[-1])
                matched_rules.append("journey-definition")
                continue
        for rule in SELECTION_RULES:
            families = rule.journeys
            if families != ALL_JOURNEYS:
                for family in families:
                    if not any(j.startswith(family) for j in discovered):
                        drift.append(f"rule '{rule.name}' references unknown journey family '{family}'")
            if normalized.startswith(rule.prefixes) or normalized in rule.exact:
                selected.update(resolve_families(families))
                matched_rules.append(rule.name)
                hit = True
        if (
            not hit
            and normalized.startswith("app/lib/")
            and normalized.endswith(".dart")
            and not _is_generated_dart(normalized)
        ):
            # Unknown cross-cutting production impact: the full small smoke
            # suite, never an empty selection.
            selected.update(discovered)
            fallback = True
            matched_rules.append("app-lib-unknown-fallback")
            hit = True
        if not hit:
            unmatched.append(normalized)

    if drift:
        return Selection((), fallback, tuple(dict.fromkeys(matched_rules)), tuple(unmatched), drift=drift)
    return Selection(tuple(sorted(selected)), fallback, tuple(dict.fromkeys(matched_rules)), tuple(unmatched))


# ---------------------------------------------------------------------------
# Receipt validation (session-evidence-v1 accounting rules)
# ---------------------------------------------------------------------------


def validate_journey_receipt(document: Mapping[str, Any]) -> list[str]:
    """Validate one C2 journey receipt against session-evidence-v1 accounting.

    Honest counts (passed + failed + skipped == executed), zero-execution can
    never be a pass, outcome agrees with counts, and timestamps are ordered.
    """
    errors: list[str] = []
    counts = document.get("counts")
    if not isinstance(counts, Mapping):
        return [f"receipt missing counts: {document.get('journey_id', '?')}"]
    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0)
    skipped = counts.get("skipped", 0)
    executed = counts.get("executed", 0)
    if passed + failed + skipped != executed:
        errors.append(f"{document.get('journey_id')}: counts dishonest {passed}+{failed}+{skipped} != {executed}")
    outcome = document.get("outcome")
    if outcome == "passed" and (failed > 0 or passed == 0):
        errors.append(f"{document.get('journey_id')}: outcome=passed with failed={failed} passed={passed}")
    if outcome == "zero-execution" and executed != 0:
        errors.append(f"{document.get('journey_id')}: outcome=zero-execution but executed={executed}")
    if outcome not in {"passed", "failed", "zero-execution"}:
        errors.append(f"{document.get('journey_id')}: unknown outcome {outcome!r}")
    started = document.get("started_at")
    finished = document.get("finished_at")
    if isinstance(started, str) and isinstance(finished, str) and finished < started:
        errors.append(f"{document.get('journey_id')}: finished_at {finished} before started_at {started}")
    return errors


def aggregate_receipts(evidence_dir: Path, journeys: Sequence[str], expected_runs: int) -> dict[str, dict[str, Any]]:
    """Group C2 receipts per journey; missing receipts are zero-execution."""
    per_journey: dict[str, dict[str, Any]] = {}
    receipts_by_journey: dict[str, list[Path]] = {}
    if evidence_dir.is_dir():
        for path in sorted(evidence_dir.glob("*.json")):
            if path.name == "verify-receipt.json":
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                journey_id = doc.get("journey_id") if isinstance(doc, dict) else None
            except (OSError, json.JSONDecodeError):
                journey_id = None
            # An unparseable receipt still counts for the journey named by its
            # file: it must surface as invalid, not silently disappear.
            if not isinstance(journey_id, str):
                candidate = path.name.split("_run")[0]
                for stem in journeys:
                    if candidate.startswith(stem[: -len("_test.dart")]):
                        journey_id = stem[: -len("_test.dart")]
                        break
            if isinstance(journey_id, str):
                receipts_by_journey.setdefault(journey_id, []).append(path)
    for stem in journeys:
        journey_id = stem[: -len("_test.dart")]
        paths = receipts_by_journey.get(journey_id, [])
        entries = []
        for receipt_path in paths:
            try:
                doc = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                entries.append({"outcome": "invalid", "error": str(exc), "file": receipt_path.name})
                continue
            errors = validate_journey_receipt(doc)
            entries.append(
                {
                    "outcome": doc.get("outcome", "unknown") if not errors else "invalid",
                    "counts": doc.get("counts", {}),
                    "errors": errors,
                    "artifact": doc.get("artifact", {}),
                    "file": receipt_path.name,
                }
            )
        if not paths:
            per_journey[journey_id] = {
                "outcome": "zero-execution",
                "receipts": 0,
                "expected_runs": expected_runs,
                "entries": [],
            }
            continue
        executed = sum(int(e.get("counts", {}).get("executed", 0)) for e in entries)
        passed = sum(int(e.get("counts", {}).get("passed", 0)) for e in entries)
        failed = sum(int(e.get("counts", {}).get("failed", 0)) for e in entries)
        skipped = sum(int(e.get("counts", {}).get("skipped", 0)) for e in entries)
        outcomes = {e["outcome"] for e in entries}
        if "invalid" in outcomes or "failed" in outcomes or "zero-execution" in outcomes:
            outcome = next(o for o in ("invalid", "zero-execution", "failed") if o in outcomes)
        elif len(paths) < expected_runs:
            outcome = "zero-execution"  # a requested run produced no receipt
        elif failed == 0 and passed > 0:
            outcome = "passed"
        else:
            outcome = "zero-execution"
        per_journey[journey_id] = {
            "outcome": outcome,
            "receipts": len(paths),
            "expected_runs": expected_runs,
            "executed": executed,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "entries": entries,
        }
    return per_journey


# ---------------------------------------------------------------------------
# Lane summary receipt
# ---------------------------------------------------------------------------


def flutter_version(flutter_cmd: str = "flutter") -> str:
    try:
        result = subprocess.run(
            [flutter_cmd, "--version"], capture_output=True, text=True, timeout=120, check=False
        )  # noqa: S603, S607
        for line in result.stdout.splitlines():
            if line.startswith("Flutter "):
                return line.strip()
        return result.stdout.splitlines()[0].strip() if result.stdout else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def build_lane_receipt(
    repo_root: Path,
    *,
    command: str,
    lane: str,
    selection: Mapping[str, Any],
    per_journey: Mapping[str, Mapping[str, Any]],
    outcome: str,
    rerun_command: str,
    failure_class: str | None,
    failures: Sequence[str],
    started_at: str,
) -> dict[str, Any]:
    totals = {
        "executed": sum(int(j.get("executed", 0)) for j in per_journey.values()),
        "passed": sum(int(j.get("passed", 0)) for j in per_journey.values()),
        "failed": sum(int(j.get("failed", 0)) for j in per_journey.values()),
        "skipped": sum(int(j.get("skipped", 0)) for j in per_journey.values()),
    }
    journeys_carry_artifact = any(entry.get("artifact") for j in per_journey.values() for entry in j.get("entries", []))
    return {
        "schema": LANE_RECEIPT_SCHEMA,
        "command": command,
        "lane": lane,
        "created_at": utc_now(),
        "started_at": started_at,
        "ended_at": utc_now(),
        "source": session_evidence.source_identity(repo_root),
        "runners": {
            "mobile-verify": CLI_VERSION,
            "journey_runner": str(RUNNER_RELPATH),
            "flutter": flutter_version(),
        },
        "selection": dict(selection),
        "journeys": {name: {k: v for k, v in info.items() if k != "entries"} for name, info in per_journey.items()},
        "totals": totals,
        "outcome": outcome,
        "failure_class": failure_class,
        "failures": list(failures),
        "rerun": rerun_command,
        "artifact_identity": {
            "bound_by": "lane-summary",
            "note": (
                "Hermetic host lane has no built app artifact; build identity is the "
                "source identity + runner versions in this receipt. Per-journey "
                "receipt artifact fields are C2-owned and reported as-is."
            ),
            "per_journey_receipts_observed": journeys_carry_artifact,
        },
    }


def write_lane_receipt(evidence_dir: Path, receipt: Mapping[str, Any]) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    target = evidence_dir / "verify-receipt.json"
    target.write_text(json.dumps(receipt, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_select(repo_root: Path, args: argparse.Namespace) -> int:
    paths = _collect_paths(args)
    selection = select_journeys(repo_root, paths)
    payload = {
        "discovered": discover_journeys(repo_root),
        "selected": list(selection.selected),
        "fallback_full_suite": selection.fallback_full_suite,
        "matched_rules": list(selection.matched_rules),
        "unmatched_paths": list(selection.unmatched_paths),
        "drift": selection.drift,
    }
    _emit(payload, as_json=args.json)
    if selection.drift:
        return EXIT_SELECTION_DRIFT
    return EXIT_OK


def cmd_doctor(repo_root: Path, args: argparse.Namespace) -> int:
    report = mobile_doctor.run_doctor(
        repo_root,
        platforms=tuple(args.platform or ()),
        min_free_gb=args.min_free_gb,
        skip_capacity=args.skip_capacity,
    )
    payload = report.as_dict()
    # Verify-lane additions (read-only; no C1 edits).
    runner_ok = (repo_root / RUNNER_RELPATH).is_file()
    discovered = discover_journeys(repo_root)
    payload["verify"] = {
        "journey_runner_present": runner_ok,
        "journeys_discovered": len(discovered),
        "journeys": list(discovered),
    }
    if args.json:
        _emit(payload, as_json=True)
    else:
        print(mobile_doctor.format_report_text(report))
        print(f"journey runner: {'present' if runner_ok else 'MISSING'}; journeys discovered: {len(discovered)}")
    if not runner_ok or not discovered:
        print("blocked: journey runner or journey definitions missing", file=sys.stderr)
        return EXIT_BLOCKED
    return {"ready": 0, "degraded": 1, "blocked": 2}[report.overall]


def cmd_fast(repo_root: Path, args: argparse.Namespace, *, runner_path: Path | None = None) -> int:
    started_at = utc_now()
    discovered = discover_journeys(repo_root)
    if not discovered:
        print("blocked: no journey definitions discovered", file=sys.stderr)
        return EXIT_BLOCKED

    if args.filter:
        selection = Selection(
            selected=tuple(j for j in discovered if args.filter in j),
            fallback_full_suite=False,
            matched_rules=("explicit-filter",),
            unmatched_paths=(),
        )
        if not selection.selected:
            print(f"selection drift: filter '{args.filter}' matched no journey", file=sys.stderr)
            return EXIT_SELECTION_DRIFT
    elif args.all:
        selection = Selection(discovered, True, ("explicit-all",), ())
    else:
        paths = _collect_paths(args)
        selection = select_journeys(repo_root, paths)
        if selection.drift:
            for line in selection.drift:
                print(f"selection drift: {line}", file=sys.stderr)
            return EXIT_SELECTION_DRIFT
        if not selection.selected:
            payload = {
                "outcome": "no-lane-selected",
                "selected": [],
                "matched_rules": list(selection.matched_rules),
                "unmatched_paths": list(selection.unmatched_paths),
                "note": "no changed path maps to a journey lane; nothing claimed",
            }
            _emit(payload, as_json=args.json)
            return EXIT_OK

    import tempfile

    evidence_dir = resolve_evidence_dir(args.evidence_dir)
    if evidence_dir is None:
        # Path("") is a truthy Path("."), so an unset/empty env var must become
        # None before Path() sees it — otherwise receipts misroute to the
        # process cwd and the lane fail-closes as zero-execution.
        evidence_dir = resolve_evidence_dir(os.environ.get("OMI_VERIFY_EVIDENCE_DIR"))
    if evidence_dir is None:
        evidence_dir = Path(tempfile.mkdtemp(prefix="mobile_verify_"))
    evidence_dir.mkdir(parents=True, exist_ok=True)

    runner = runner_path if runner_path is not None else repo_root / RUNNER_RELPATH
    per_journey_failures: list[str] = []
    logs: dict[str, str] = {}
    blocked_class: str | None = None
    runner_drift = False
    for stem in selection.selected:
        journey_id = stem[: -len("_test.dart")]
        log_path = evidence_dir / f"{journey_id}.log"
        cmd = [
            "bash",
            str(runner),
            "--lane",
            "hermetic",
            "--filter",
            journey_id,
            "--runs",
            str(args.runs),
            "--evidence-dir",
            str(evidence_dir),
        ]
        rerun = " ".join(cmd)
        print(f"── {journey_id} ({'full-suite fallback' if selection.fallback_full_suite else 'focused'})")
        print(f"   rerun: {rerun}")
        try:
            result = subprocess.run(  # noqa: S603
                cmd,
                cwd=repo_root / "app",
                capture_output=True,
                text=True,
                timeout=args.journey_timeout,
                check=False,
            )
            log_text = result.stdout + result.stderr
            status = result.returncode
        except subprocess.TimeoutExpired as exc:
            log_text = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            status = -1
        except OSError as exc:
            # bash / the journey runner missing must be a classified blocked
            # outcome, not a traceback — same contract as device doctor + adb.
            log_text = f"{cmd[0]} not available: {exc}"
            status = -1
            blocked_class = "infrastructure"
        log_path.write_text(log_text, encoding="utf-8")
        logs[journey_id] = log_text
        if status == EXIT_SELECTION_DRIFT:
            per_journey_failures.append(f"{journey_id}: selection drift inside runner")
            runner_drift = True
            continue
        if status == 0:
            continue
        failure_class = classify_log_text(log_text[-8000:])
        if failure_class in {"compile", "infrastructure"} or status == -1:
            if status != -1:
                blocked_class = failure_class
            elif blocked_class is None:
                blocked_class = "timeout"
            per_journey_failures.append(f"{journey_id}: {blocked_class} failure (not a test verdict) — rerun: {rerun}")
            break  # infra/compile failures stop the lane: later journeys would not be meaningful
        per_journey_failures.append(f"{journey_id}: test failures (exit {status}) — rerun: {rerun}")

    per_journey = aggregate_receipts(evidence_dir, selection.selected, args.runs)
    if per_journey_failures or any(info["outcome"] != "passed" for info in per_journey.values()):
        outcome = "failed"
        for info in per_journey.values():
            if info["outcome"] == "zero-execution":
                outcome = "zero-execution"
                break
        if blocked_class:
            outcome = "blocked"
    else:
        outcome = "passed"

    receipt = build_lane_receipt(
        repo_root,
        command="fast",
        lane="hermetic",
        selection={
            "selected": list(selection.selected),
            "fallback_full_suite": selection.fallback_full_suite,
            "matched_rules": list(selection.matched_rules),
            "runs": args.runs,
        },
        per_journey=per_journey,
        outcome=outcome,
        rerun_command=f"bash scripts/dev-harness/mobile-verify.sh fast --all --evidence-dir {evidence_dir}",
        failure_class=blocked_class,
        failures=per_journey_failures,
        started_at=started_at,
    )
    receipt["evidence_dir"] = str(evidence_dir)
    write_lane_receipt(evidence_dir, receipt)
    if args.json:
        _emit(receipt, as_json=True)
    else:
        print(json.dumps({k: receipt[k] for k in ("outcome", "totals", "failure_class")}, indent=2))
        print(f"receipt: {evidence_dir / 'verify-receipt.json'}")
        for failure in per_journey_failures:
            print(f"✗ {failure}", file=sys.stderr)
    if runner_drift:
        return EXIT_SELECTION_DRIFT
    if outcome == "passed":
        return EXIT_OK
    if outcome == "blocked":
        return EXIT_BLOCKED
    return EXIT_TEST_FAILURES


def cmd_smoke(repo_root: Path, args: argparse.Namespace) -> int:
    """Bounded simulator smoke: C1 session infra + simulator-lane journeys.

    Fail-closed: missing simulator/session infrastructure exits 2 with the
    exact remedy and is NEVER reported as success. Ordinary CI never invokes
    this lane (hermetic only); it exists for provisioned local/trusted hosts.
    """
    started_at = utc_now()
    report = mobile_doctor.run_doctor(repo_root, platforms=("ios-simulator",), min_free_gb=12)
    if report.overall != "ready":
        payload = {
            "outcome": "blocked",
            "reason": "simulator lane not ready (doctor)",
            "doctor": report.as_dict(),
            "remedy": "run: bash scripts/dev-harness/mobile-session.sh doctor --platform ios-simulator",
        }
        _emit(payload, as_json=args.json)
        print("blocked: simulator lane not ready — see remedy above", file=sys.stderr)
        return EXIT_BLOCKED
    session_id = args.session
    if not session_id:
        payload = {
            "outcome": "blocked",
            "reason": "smoke lane requires an explicitly started C1 session (--session oms-<name>)",
            "remedy": "make mobile-session ARGS=\"start oms-<name>\" then re-run with --session oms-<name>",
        }
        _emit(payload, as_json=args.json)
        return EXIT_BLOCKED
    cli = repo_root / SESSION_CLI_RELPATH
    status_result = subprocess.run(  # noqa: S603
        ["bash", str(cli), "status", session_id, "--json"], capture_output=True, text=True, check=False
    )
    if status_result.returncode != 0:
        _emit(
            {
                "outcome": "blocked",
                "reason": f"session {session_id} not queryable",
                "doctor": status_result.stderr.strip(),
            },
            as_json=args.json,
        )
        return EXIT_BLOCKED
    status_doc = json.loads(status_result.stdout or "{}")
    device = (status_doc.get("device") or {}).get("udid") or ""
    api_base = status_doc.get("api_base_url") or ""
    if not device or not api_base:
        _emit(
            {
                "outcome": "blocked",
                "reason": f"session {session_id} has no attached simulator or API base",
                "status": status_doc,
            },
            as_json=args.json,
        )
        return EXIT_BLOCKED
    evidence_dir = resolve_evidence_dir(args.evidence_dir) or Path(f"/tmp/mobile-verify-smoke-{session_id}")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "bash",
        str(repo_root / RUNNER_RELPATH),
        "--lane",
        "simulator",
        "--device",
        device,
        "--api-base",
        api_base,
        "--evidence-dir",
        str(evidence_dir),
    ]
    rerun = " ".join(cmd)
    try:
        result = subprocess.run(
            cmd, cwd=repo_root / "app", capture_output=True, text=True, timeout=args.journey_timeout, check=False
        )  # noqa: S603
        log_text = result.stdout + result.stderr
        status = result.returncode
    except subprocess.TimeoutExpired as exc:
        # Mirror the fast lane: a hung simulator run is blocked (exit 2) with a
        # receipt, never an unhandled traceback after a full-length run.
        log_text = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        status = -1
    (evidence_dir / "smoke.log").write_text(log_text, encoding="utf-8")
    discovered = discover_journeys(repo_root)
    per_journey = aggregate_receipts(evidence_dir, discovered, 1)
    failure_class = "timeout" if status == -1 else classify_log_text(log_text[-8000:])
    outcome = (
        "passed"
        if status == 0 and all(info["outcome"] == "passed" for info in per_journey.values())
        else ("blocked" if status == -1 or failure_class in {"compile", "infrastructure"} else "failed")
    )
    receipt = build_lane_receipt(
        repo_root,
        command="smoke",
        lane="simulator",
        selection={"selected": list(discovered), "session": session_id, "device": device, "api_base": api_base},
        per_journey=per_journey,
        outcome=outcome,
        rerun_command=rerun,
        failure_class=failure_class or None,
        failures=[] if outcome == "passed" else [f"runner exit {status}"],
        started_at=started_at,
    )
    receipt["evidence_dir"] = str(evidence_dir)
    write_lane_receipt(evidence_dir, receipt)
    _emit(receipt, as_json=args.json)
    return {"passed": EXIT_OK, "blocked": EXIT_BLOCKED}.get(outcome, EXIT_TEST_FAILURES)


def cmd_physical(repo_root: Path, args: argparse.Namespace) -> int:
    """Physical qualification admission: a separate trusted/manual lane.

    Physical-device evidence comes only from the C5 (SCA-491) device runner on
    provisioned hardware with a signed build. This command never runs device
    tests and never reports success: it exists so contributors and CI cannot
    mistake a simulator pass for physical acceptance.
    """
    payload = {
        "outcome": "blocked",
        "lane": "physical",
        "reason": "physical qualification is a separately trusted, manual admission path (C5/SCA-491); software exists, hardware evidence is pending user-run results",
        "handoff": "scripts/dev-harness/PHYSICAL_DEVICES.md",
        "commands": [
            "make mobile-session ARGS=\"device doctor\"",
            "make mobile-session ARGS=\"device run ...\" (see PHYSICAL_DEVICES.md)",
        ],
        "requires": [
            "provisioned device + signing per SCA-491 external handoff",
            "C1 session lease on the device",
            "C5 device lease + runner (mobile-session device acquire/run)",
        ],
        "physical_acceptance": "pending-user-run-evidence",
        "ci_policy": "ordinary CI (including forks) never runs this lane; simulator passes are not physical evidence",
        "simulator_vs_hardware": "separate visibility is the contract: hermetic/simulator results never stand in for hardware",
    }
    _emit(payload, as_json=args.json)
    return EXIT_BLOCKED


def _collect_paths(args: argparse.Namespace) -> list[str]:
    if getattr(args, "changed_files", None):
        return [
            line.strip() for line in Path(args.changed_files).read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    return list(getattr(args, "paths", ()) or ())


def _emit(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}: {json.dumps(value, default=str) if not isinstance(value, str) else value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mobile-verify", description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    # --json is accepted before or after the subcommand: subparser copies use
    # SUPPRESS so an absent flag keeps the main parser's value.
    def _add(name: str, **kwargs: Any) -> argparse.ArgumentParser:
        child = sub.add_parser(name, **kwargs)
        child.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return child

    p_select = _add("select", help="show which journeys a diff selects")
    p_select.add_argument("--changed-files", help="file with one changed path per line")
    p_select.add_argument("--paths", nargs="*", default=[], help="changed paths")

    p_doctor = _add("doctor", help="lane readiness (C1 doctor + verify surface)")
    p_doctor.add_argument("--platform", action="append", choices=("android", "ios"))
    p_doctor.add_argument("--min-free-gb", type=float, default=12)
    p_doctor.add_argument("--skip-capacity", action="store_true")

    p_fast = _add("fast", help="focused hermetic fast feedback")
    p_fast.add_argument("--changed-files", help="file with one changed path per line")
    p_fast.add_argument("--paths", nargs="*", default=[], help="changed paths")
    p_fast.add_argument("--filter", help="explicit journey substring (drift-checked)")
    p_fast.add_argument("--all", action="store_true", help="run the full hermetic suite")
    p_fast.add_argument("--runs", type=int, default=1)
    p_fast.add_argument("--evidence-dir")
    p_fast.add_argument("--session", help="attach to an existing live session; never cold fallback")
    p_fast.add_argument("--journey-timeout", type=int, default=DEFAULT_JOURNEY_TIMEOUT_S)

    p_smoke = _add("smoke", help="bounded simulator smoke (fail-closed; not for ordinary CI)")
    p_smoke.add_argument("--session", help="C1 session id with an attached simulator")
    p_smoke.add_argument("--evidence-dir")
    p_smoke.add_argument("--journey-timeout", type=int, default=3600)

    _add("physical", help="physical admission document (always blocked until user-run hardware evidence)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[3]
    handlers: dict[str, Callable[[Path, argparse.Namespace], int]] = {
        "select": cmd_select,
        "doctor": cmd_doctor,
        "fast": cmd_fast,
        "smoke": cmd_smoke,
        "physical": cmd_physical,
    }
    if args.command == "fast" and args.session:
        from . import live_session

        try:
            return live_session.verify_live(repo_root, args)
        except live_session.SessionError as exc:
            print(f"blocked: {exc}", file=sys.stderr)
            return EXIT_BLOCKED
    return handlers[args.command](repo_root, args)


if __name__ == "__main__":
    raise SystemExit(main())
