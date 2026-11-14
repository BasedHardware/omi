from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from run_checks import _parse_yaml_subset, head_tree_paths

KINDS = {"env", "posthog", "bundle", "server_capability", "build_define", "firestore", "hardcoded"}
LIFECYCLES = {"experiment", "rollout", "ops_kill", "config_switch"}
SURFACES = {"backend", "macos", "windows", "web-app", "web-admin", "web-frontend", "mobile", "llm-gateway"}
FAILS = {"open", "closed", "inverted"}
DECISIONS = {"pending", "graduate", "ship", "kill", "kill_after_readout", "keep", "with_legacy"}
TERMINALS = {"on", "off", "keep", "undecided"}
REVIEW_GRACE_DAYS = 7
RAMP_REQUIRED_FROM = date(2026, 10, 21)
# Temporary migration debt; relabel these opt-in controls in the registry sweep.
OPS_KILL_DEFAULT_OFF_ALLOWLIST_EXPIRES = date(2026, 11, 29)
OPS_KILL_DEFAULT_OFF_ALLOWLIST = {
    "BATCH_FINAL_PASS_PERCENT",
    "BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED",
    "BATCH_PIPELINE_PROJECTION_RESTORABLE_CAP_EXPIRY_ENABLED",
    "BATCH_PIPELINE_WORKER_ENABLED",
    "CAP_HOLD_DURABLE_REDRIVE_ENABLED",
    "CAP_HOLD_FLEET_SNAPSHOT_ENABLED",
    "CAP_HOLD_LIVE_FRAGMENT_ENABLED",
    "CAP_HOLD_REDRIVE_PARALLEL_DRAIN_ENABLED",
    "EPISODE_F_JOIN_ENABLED",
    "EPISODE_F_JOIN_PERCENT",
    "FAIR_USE_ENABLED",
    "MEMORY_ENABLED",
    "PARAKEET_STREAM_ALLOCATION_PERCENT",
    "PARAKEET_WINDOW_ALLOCATION_PERCENT",
    "PLAYBACK_MANIFEST_RECOVERY_ENABLED",
    "RECORD_GAP_FILL",
    "STT_GPU_FLEET_OFF",
    "STT_STREAMING_PARAKEET_SLOT_ENABLED",
}

POSTHOG_ROLES = {"enable", "kill", "exposure", "payload"}
FLAG_SUFFIX = re.compile(r"(?:_ENABLED|_MODE|_KILL_SWITCH|_COHORT|_PERCENT|_PAUSED|_STOP|_SHADOW(?:_[A-Z0-9]+)?)$")
SWIFT_FLAG = re.compile(
    r'\bstatic\s+let\s+\w*(?:flagName|FlagName|FlagKey|Flag|enabledFlag|killSwitchFlag|enableFlag)\s*=\s*"([^"\n]+)"'
)
SWIFT_LITERAL = re.compile(r'\bisFeatureEnabled\s*\(\s*"([^"\n]+)"')
SWIFT_STRING_CONSTANT = re.compile(r'\bstatic\s+let\s+([A-Za-z_]\w*)\s*=\s*"([^"\n]+)"')
SWIFT_POSTHOG_CONSTANT_READ = re.compile(r'\bgetFeatureFlag\s*\(\s*(?:Self\.)?([A-Za-z_]\w*)\s*[,)]')
SWIFT_HEADER = re.compile(
    r'\blet\s+(?:canonicalLifecycleExposed|deviceScopeSupported|defaultDeleteSupported|beliefEnabled)Header\s*=\s*"(X-Omi-[^"\n]+)"'
)
SWIFT_HARDCODED = re.compile(
    r'\bstatic\s+var\s+(isWorkstreamPoolingEnabled|isProactiveCandidatesEnabled|isEnabled)\s*:'
)
DART_DEFINITION = re.compile(r"\bExperimentDefinition(?:<[^>]+>)?\s*\(\s*key\s*:\s*['\"]([^'\"\n]+)['\"]")
DART_MASTER = re.compile(r"\b(?:enabledFlag|killSwitchFlag)\s*=\s*['\"]([^'\"\n]+)['\"]")
BUILD_DEFINE = re.compile(r"\b(?:import\.meta\.env\.VITE_ENABLE_|process\.env\.NEXT_PUBLIC_ENABLE_)([A-Z0-9_]+)")
# PostHog keys on TypeScript clients: `static readonly enabledFlag = 'web-…'`.
TS_POSTHOG_FLAG = re.compile(r"\b(?:enabledFlag|killSwitchFlag)\s*=\s*['\"]([^'\"\n]+)['\"]")
# Cataloged server-side Node switches are runtime env reads, not build defines.
# Restrict discovery to known names so this does not re-inventory every legacy
# private Node setting while registering a new runtime switch.
NODE_RUNTIME_ENV = re.compile(r"\bprocess\.env\.((?!NEXT_PUBLIC_)[A-Z][A-Z0-9_]*)")
ACTION_ENV_ARG = re.compile(r"--(?:update|set)-env-vars(?:=|\s+)(?:\"([^\"]*)\"|'([^']*)'|([^\s\\]+))", re.S)
ACTION_ASSIGNMENT = re.compile(r"^\s*([A-Z][A-Z0-9_]+)=([^,\s]+)")


@dataclass(frozen=True)
class Read:
    key: str
    path: str
    line: int


@dataclass(frozen=True)
class Declaration(Read):
    platform: str
    workload: str
    environment: str
    source: str


def load_registry(path: Path) -> dict[str, list[dict[str, Any]]]:
    return _parse_yaml_subset(path)


def _ramp_applies_to(entry: dict[str, Any]) -> bool:
    return entry.get("lifecycle") == "rollout" and (
        entry.get("decision") in {"pending", "undecided"} or entry.get("terminal") == "undecided"
    )


def effective_due(entry: dict[str, Any]) -> date:
    """The review date, extended only by the row's single bounded extension."""
    due = date.fromisoformat(entry["review_by"])
    if "extension" in entry:
        due = max(due, date.fromisoformat(entry["extension"]["until"]))
    return due


def ramp_due(entry: dict[str, Any]) -> date:
    """Use the same extension for the ramp deadline and review deadline."""
    due = date.fromisoformat(entry["ramp"]["done_by"])
    if "extension" in entry:
        due = max(due, date.fromisoformat(entry["extension"]["until"]))
    return due


def due_dates(entry: dict[str, Any]) -> list[tuple[str, date]]:
    if entry.get("lifecycle") not in {"rollout", "experiment"}:
        return []
    deadlines = [("review", effective_due(entry))]
    if _ramp_applies_to(entry) and "ramp" in entry:
        deadlines.append(("ramp", ramp_due(entry)))
    return deadlines


def _validate_extension(entry: dict[str, Any], key: str, errors: list[str], as_of: date) -> None:
    if "extension" not in entry:
        return
    extension = entry["extension"]
    if not isinstance(extension, dict):
        errors.append(f"{key}: extension must be an object")
        return
    dates: dict[str, date] = {}
    for field in ("until", "granted"):
        try:
            dates[field] = date.fromisoformat(extension[field])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{key}: extension.{field} must be an ISO date")
    if len(dates) == 2 and not 0 <= (dates["until"] - dates["granted"]).days <= 14:
        errors.append(f"{key}: extension.until must be 0 to 14 days after extension.granted")
    if "granted" in dates and dates["granted"] > as_of:
        errors.append(f"{key}: extension.granted must not be in the future")
    reason = extension.get("reason")
    if (
        not isinstance(reason, str)
        or len(reason.strip()) < 15
        or reason.strip().casefold() in {"renew", "extend", "tbd", "later"}
    ):
        errors.append(f"{key}: extension.reason must be at least 15 characters and explain the delay")
    if not isinstance(extension.get("by"), str) or not extension["by"].strip():
        errors.append(f"{key}: extension.by must name the owning lane")


def _single_user_cohort_step(step: str) -> bool:
    normalized = step.strip().casefold().replace("_", " ")
    return bool(
        re.search(r"\b(?:single|one|1)[ -]?(?:user|person|uid)\b", normalized)
        or re.search(r"\buid\s*[:=]\s*[a-z0-9_-]+\b", normalized)
        or re.search(r"(?:^|\s)@[a-z0-9_.-]+$", normalized)
        or re.search(r"\b[a-z][a-z0-9.'-]*[- ]only$", normalized)
        or re.fullmatch(r"[a-z0-9.+-]+@[a-z0-9.-]+", normalized)
    )


def _validate_ramp(entry: dict[str, Any], label: str, errors: list[str]) -> None:
    if "ramp" not in entry:
        return
    ramp = entry["ramp"]
    if not isinstance(ramp, dict):
        errors.append(f"{label}: ramp must be an object")
        return
    cohorts = ramp.get("cohorts")
    if (
        not isinstance(cohorts, list)
        or not cohorts
        or any(not isinstance(step, str) or not step.strip() for step in cohorts)
    ):
        errors.append(f"{label}: ramp.cohorts must be a nonempty list of nonempty strings")
    elif _single_user_cohort_step(cohorts[-1]):
        errors.append(f"{label}: ramp.cohorts terminal step must not be single-user (David-only is never terminal)")
    for field in ("clean_metric", "expander"):
        if not isinstance(ramp.get(field), str) or not ramp[field].strip():
            errors.append(f"{label}: ramp.{field} is required")
    try:
        done_by = date.fromisoformat(ramp["done_by"])
    except (KeyError, TypeError, ValueError):
        errors.append(f"{label}: ramp.done_by must be an ISO date")
    else:
        try:
            review_by = date.fromisoformat(entry["review_by"])
        except (KeyError, TypeError, ValueError):
            return
        if done_by > review_by:
            errors.append(f"{label}: ramp.done_by must be on or before review_by")


def validate_registry(
    registry: dict[str, list[dict[str, Any]]], *, root: Path = ROOT, as_of: date | None = None
) -> list[str]:
    errors: list[str] = []
    current_date = as_of or datetime.now(timezone.utc).date()
    default_off_ops: set[str] = set()
    names: dict[str, str] = {}
    resolved_root = root.resolve()
    if set(registry) != {"flags", "ignore", "retired"}:
        errors.append("registry must contain exactly flags:, ignore:, and retired: sections")
    for section in ("flags", "ignore", "retired"):
        for index, entry in enumerate(registry.get(section, []), 1):
            label = f"{section}[{index}]"
            key = entry.get("key")
            if not isinstance(key, str) or not key.strip():
                errors.append(f"{label}: key must be nonempty")
                continue
            keys = [key]
            if section == "flags":
                aliases = entry.get("aliases", [])
                if not isinstance(aliases, list) or not all(isinstance(alias, str) and alias for alias in aliases):
                    errors.append(f"{label}: aliases must be a list of nonempty names")
                    aliases = []
                keys += aliases
                for field, allowed in (
                    ("kind", KINDS),
                    ("lifecycle", LIFECYCLES),
                    ("fail", FAILS),
                    ("decision", DECISIONS),
                ):
                    if entry.get(field) not in allowed:
                        errors.append(f"{label}: invalid {field}: {entry.get(field)!r}")
                lifecycle = entry.get("lifecycle")
                decision = entry.get("decision")
                terminal = entry.get("terminal")
                if "terminal" not in entry:
                    errors.append(f"{label}: terminal is required")
                elif terminal not in TERMINALS:
                    errors.append(f"{label}: invalid terminal: {terminal!r}")
                if lifecycle in {"ops_kill", "config_switch"} and terminal != "keep":
                    errors.append(f"{label}: {lifecycle} terminal must be keep")
                if lifecycle in {"rollout", "experiment"} and entry.get("owner") == "unowned":
                    errors.append(f"{label}: {lifecycle} owner must not be unowned")
                terminal_for_decision = {
                    "graduate": "on",
                    "ship": "on",
                    "kill": "off",
                    "keep": "keep",
                    "with_legacy": "off",
                }
                if decision in terminal_for_decision and terminal != terminal_for_decision[decision]:
                    errors.append(f"{label}: decision {decision} requires terminal {terminal_for_decision[decision]}")
                if decision == "kill_after_readout" and (lifecycle != "experiment" or terminal != "undecided"):
                    errors.append(f"{label}: kill_after_readout requires experiment lifecycle and undecided terminal")
                surfaces = entry.get("surfaces")
                if not isinstance(surfaces, list) or not surfaces or any(s not in SURFACES for s in surfaces):
                    errors.append(f"{label}: invalid surfaces")
                for field in ("summary", "owner", "created"):
                    if not isinstance(entry.get(field), str) or not entry[field].strip():
                        errors.append(f"{label}: {field} is required")
                for field in ("created", "review_by"):
                    if field in entry:
                        try:
                            date.fromisoformat(entry[field])
                        except (TypeError, ValueError):
                            errors.append(f"{label}: {field} must be an ISO date")
                _validate_ramp(entry, label, errors)
                _validate_extension(entry, key, errors, current_date)
                if lifecycle == "ops_kill" and entry.get("fail") == "closed":
                    default_off_ops.add(key)
                    if key not in OPS_KILL_DEFAULT_OFF_ALLOWLIST:
                        errors.append(
                            f"{key}: ops_kill must default on (off is the kill); use rollout or config_switch"
                        )
                    elif current_date > OPS_KILL_DEFAULT_OFF_ALLOWLIST_EXPIRES:
                        errors.append(
                            f"ops_kill default-off exception expired {OPS_KILL_DEFAULT_OFF_ALLOWLIST_EXPIRES}: {key}"
                        )
                if _ramp_applies_to(entry) and "ramp" not in entry:
                    try:
                        created = date.fromisoformat(entry["created"])
                    except (KeyError, TypeError, ValueError):
                        pass
                    else:
                        if created >= RAMP_REQUIRED_FROM:
                            errors.append(
                                f"{label}: ramp is required for pending/undecided rollout rows created on or after "
                                f"{RAMP_REQUIRED_FROM.isoformat()}"
                            )
                if entry.get("lifecycle") in {"experiment", "rollout"} and "review_by" not in entry:
                    errors.append(f"{label}: review_by is required for experiment/rollout")
                if entry.get("lifecycle") in {"ops_kill", "config_switch"} and "review_by" in entry:
                    errors.append(f"{label}: ops_kill/config_switch must omit review_by")
                prereg = entry.get("prereg")
                if isinstance(prereg, str) and prereg.strip():
                    candidate = Path(prereg)
                    resolved = (resolved_root / candidate).resolve()
                    if candidate.is_absolute():
                        errors.append(f"{label}: prereg must be a repo-relative path: {prereg}")
                    elif not resolved.is_relative_to(resolved_root):
                        errors.append(f"{label}: prereg escapes the repository root: {prereg}")
                    elif not resolved.is_file():
                        # Cone-mode sparse checkouts do not materialise
                        # out-of-cone paths, so a prereg doc that is real at
                        # HEAD is valid evidence; absent from disk AND HEAD is
                        # still an error. None means "not a git repo" (tests
                        # validate against plain directories): disk only.
                        tracked = head_tree_paths(resolved_root)
                        relative = resolved.relative_to(resolved_root).as_posix()
                        if tracked is None or relative not in tracked:
                            errors.append(f"{label}: prereg file does not exist: {prereg}")
                elif "prereg" in entry:
                    errors.append(f"{label}: prereg must be a nonempty repo-relative path")
                elif entry.get("lifecycle") == "experiment" and entry.get("decision") != "kill":
                    errors.append(f"{label}: prereg is required for experiments")
                ph = entry.get("posthog")
                if entry.get("kind") == "posthog":
                    if (
                        not isinstance(ph, dict)
                        or ph.get("row") not in {"expected", "absent"}
                        or ph.get("role") not in POSTHOG_ROLES
                    ):
                        errors.append(
                            f"{label}: posthog requires row expected|absent and role enable|kill|exposure|payload"
                        )
                elif ph is not None:
                    errors.append(f"{label}: posthog block requires kind: posthog")
                if "pairs_with" in entry and (
                    not isinstance(entry["pairs_with"], list)
                    or not all(isinstance(p, str) for p in entry["pairs_with"])
                ):
                    errors.append(f"{label}: pairs_with must be a list of names")
            elif section == "ignore":
                if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
                    errors.append(f"{label}: ignore requires reason")
            else:
                kind = entry.get("kind")
                if kind == "posthog":
                    if entry.get("posthog") != {"row": "delete"}:
                        errors.append(f"{label}: retired posthog rows require posthog row: delete")
                elif kind in {"hardcoded", "env", "server_capability"}:
                    if "posthog" in entry:
                        errors.append(f"{label}: retired hardcoded/env entries must omit posthog")
                else:
                    errors.append(f"{label}: retired requires kind: posthog, hardcoded, or env")
                if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
                    errors.append(f"{label}: retired requires reason")
                try:
                    date.fromisoformat(entry["retired"])
                except (KeyError, TypeError, ValueError):
                    errors.append(f"{label}: retired must be an ISO date")
            for name in keys:
                if name in names:
                    errors.append(f"duplicate key or alias: {name} ({names[name]}, {label})")
                names[name] = label
    if resolved_root == ROOT.resolve():
        stale = sorted(OPS_KILL_DEFAULT_OFF_ALLOWLIST - default_off_ops)
        if stale:
            errors.append("remove stale ops_kill default-off allowlist entries: " + ", ".join(stale))
    return errors


def tracked_code_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        stdout=subprocess.PIPE,
        check=True,
        env={key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
    )
    return sorted({p.decode("utf-8") for p in result.stdout.split(b"\0") if p})


def source_text(root: Path, path: str) -> str | None:
    """File content from the working tree, falling back to the HEAD blob.

    Cone-mode sparse checkouts keep out-of-cone paths in the index but do not
    materialise them, so flag reads outside the cone must be scanned at HEAD
    or the registry misreports those flags as stale. None = unreadable
    everywhere (deleted without a commit): callers skip, as before.
    """
    file = root / path
    if file.is_file():
        return file.read_text(encoding="utf-8")
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        env={key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8")


def relevant_code(path: str) -> bool:
    if path.startswith("backend/") and path.endswith(".py"):
        return not any(part in path.split("/") for part in ("tests", "testing", "scripts", "migrations", ".venv"))
    if path.startswith("llm_gateway/") and path.endswith(".py"):
        return "/tests/" not in path
    return (
        path.startswith("desktop/macos/Desktop/Sources/")
        and path.endswith(".swift")
        and "/Generated/" not in path
        or path.startswith("app/lib/services/experiments/")
        and path.endswith(".dart")
        or path.startswith(("web/", "desktop/windows/src/"))
        and path.endswith((".ts", ".tsx"))
        and "/generated/" not in path.lower()
    )


def python_reads(path: str, text: str, known: set[str]) -> list[tuple[str, int]]:
    if not any(
        token in text
        for token in ("getenv", "environ", "_FLAG_KEY", "_ENV", "_COHORT", "_HEADER", "enabled_env_var", "kill_switch")
    ):
        return []
    tree = ast.parse(text, filename=path)
    values: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                for target in targets:
                    if isinstance(target, ast.Name):
                        values[target.id] = value.value
    found: list[tuple[str, int]] = []

    def literal(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return values.get(node.id)
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if node.args and isinstance(func, ast.Attribute):
                if func.attr == "getenv" and isinstance(func.value, ast.Name) and func.value.id == "os":
                    key = literal(node.args[0])
                    if key and (FLAG_SUFFIX.search(key) or key in known):
                        found.append((key, node.lineno))
                elif (
                    func.attr == "get"
                    and isinstance(func.value, ast.Attribute)
                    and isinstance(func.value.value, ast.Name)
                    and func.value.value.id == "os"
                    and func.value.attr == "environ"
                ):
                    key = literal(node.args[0])
                    if key and (FLAG_SUFFIX.search(key) or key in known):
                        found.append((key, node.lineno))
                elif func.attr in {"get_feature_flag", "feature_enabled", "is_feature_enabled"}:
                    key = literal(node.args[0])
                    if key:
                        found.append((key, node.lineno))
            if isinstance(func, ast.Name) and func.id == "cohort_admits" and node.args:
                cohort = literal(node.args[0])
                if cohort and f"{cohort}_COHORT" in known:
                    found.append((f"{cohort}_COHORT", node.lineno))
            for arg in (*node.args, *(keyword.value for keyword in node.keywords)):
                key = literal(arg)
                if key and (key in known or (FLAG_SUFFIX.search(key) and re.fullmatch(r"[A-Z][A-Z0-9_]+", key))):
                    found.append((key, node.lineno))
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "os"
            and node.value.attr == "environ"
        ):
            key = literal(node.slice)
            if key and (FLAG_SUFFIX.search(key) or key in known):
                found.append((key, node.lineno))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id.endswith("_FLAG_KEY") for target in targets):
                key = literal(node.value)
                if key:
                    found.append((key, node.lineno))
            for target in targets:
                if isinstance(target, ast.Name) and target.id in known and target.id in {"ACCOUNT_CUTOVER_COHORT"}:
                    found.append((target.id, node.lineno))
                if isinstance(target, ast.Name) and target.id in known and target.id.endswith("_COHORT"):
                    found.append((target.id, node.lineno))
                if (
                    isinstance(target, ast.Name)
                    and (target.id.endswith(("_ENV", "_HEADER")) or target.id == "enabled_env_var")
                    and literal(node.value) in known
                ):
                    found.append((literal(node.value), node.lineno))
    return found


def _in_client_comment(text: str, pos: int) -> bool:
    line_prefix = text[text.rfind("\n", 0, pos) + 1 : pos]
    return bool(re.search(r"(?:^|\s)//", line_prefix)) or text.rfind("/*", 0, pos) > text.rfind("*/", 0, pos)


def extract_code_reads(root: Path, known: set[str]) -> list[Read]:
    reads: list[Read] = []
    for path in tracked_code_paths(root):
        if not relevant_code(path):
            continue
        text = source_text(root, path)
        if text is None:
            continue
        matches: list[tuple[str, int]] = []
        if path.endswith(".py"):
            matches = python_reads(path, text, known)
        else:
            patterns = (
                (SWIFT_FLAG, SWIFT_LITERAL, SWIFT_HEADER)
                if path.endswith(".swift")
                else (
                    (DART_DEFINITION, DART_MASTER)
                    if path.endswith(".dart")
                    else (BUILD_DEFINE, TS_POSTHOG_FLAG, NODE_RUNTIME_ENV)
                )
            )
            for pattern in patterns:
                for match in pattern.finditer(text):
                    if _in_client_comment(text, match.start()):
                        continue
                    key = (
                        ("VITE_ENABLE_" if "import.meta.env.VITE_ENABLE_" in match.group(0) else "NEXT_PUBLIC_ENABLE_")
                        + match[1]
                        if pattern is BUILD_DEFINE
                        else match[1]
                    )
                    if pattern is NODE_RUNTIME_ENV and key not in known:
                        continue
                    if not key.startswith("--"):
                        matches.append((key, text.count("\n", 0, match.start()) + 1))
            if path.endswith(".swift"):
                constants: dict[str, list[tuple[str, int]]] = {}
                for match in SWIFT_STRING_CONSTANT.finditer(text):
                    if not _in_client_comment(text, match.start()):
                        constants.setdefault(match[1], []).append((match[2], match.start()))
                for match in SWIFT_POSTHOG_CONSTANT_READ.finditer(text):
                    definitions = constants.get(match[1], [])
                    if not _in_client_comment(text, match.start()) and len(definitions) == 1:
                        key, _ = definitions[0]
                        matches.append((key, text.count("\n", 0, match.start()) + 1))
            if path.endswith("ContextBucketsFeature.swift"):
                for match in SWIFT_HARDCODED.finditer(text):
                    if _in_client_comment(text, match.start()):
                        continue
                    key = "ContextBucketsFeature.isEnabled" if match[1] == "isEnabled" else match[1]
                    if key in known:
                        matches.append((key, text.count("\n", 0, match.start()) + 1))
        reads.extend(Read(key, path, line) for key, line in matches)
    return reads


def _manifest_workload(parents: tuple[str, ...]) -> tuple[str, str] | None:
    # Keep runtime identity: Cloud Run and a GKE pod are different workloads.
    if parents[:1] == ("gke",) and len(parents) == 3 and parents[-1] == "env":
        return "gke", parents[1]
    if parents == ("desktop_backend", "env"):
        return "desktop", "desktop_backend"
    if len(parents) == 4 and parents[0] == "cloud_run" and parents[1] in {"services", "jobs"} and parents[-1] == "env":
        platform = "cloud_run_service" if parents[1] == "services" else "cloud_run_job"
        return platform, "/".join(parents[:3])
    return None


def _yaml_mappings(node, parents=(), ancestors=()):
    """Walk aliases at each use site, preserving the env path through mapping merges."""
    if not isinstance(node, (yaml.MappingNode, yaml.SequenceNode)):
        return
    if id(node) in ancestors:
        raise ValueError("recursive YAML declaration mapping")
    ancestors = (*ancestors, id(node))
    if isinstance(node, yaml.MappingNode):
        yield node, parents
        for key, value in node.value:
            if key.value == "<<":
                yield from _yaml_mappings(value, parents, ancestors)
            else:
                yield from _yaml_mappings(value, (*parents, key.value), ancestors)
    else:
        for value in node.value:
            yield from _yaml_mappings(value, parents, ancestors)


def _validated_chart_bindings(root: Path) -> dict[tuple[str, str], list[str]]:
    """Chart path/environment -> GKE sections whose expected env is validated against it.

    Mirror the composer's precedence for values_file: a per-env override wins
    over the shared section. Equality remains enforced by _validate_gke; this
    checker identifies sources and never substitutes for that admission check.
    """
    sections: dict[str, dict[str, Any]] = {}
    for name, section in (
        ("_base.yaml", "environment_shared"),
        ("dev.overlay.yaml", "overlay"),
        ("prod.overlay.yaml", "overlay"),
    ):
        path = f"backend/deploy/runtime_env/{name}"
        text = source_text(root, path)
        try:
            document = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) if text else {}
        except yaml.YAMLError as error:
            raise ValueError(f"{path}: invalid declaration YAML: {error}") from error
        sections[name] = ((document or {}).get(section) or {}).get("gke") or {}
    shared = sections["_base.yaml"]
    bindings: dict[tuple[str, str], list[str]] = {}
    for env in ("dev", "prod"):
        overlay = sections[f"{env}.overlay.yaml"]
        for workload in sorted(set(shared) | set(overlay)):
            base_service = shared.get(workload) or {}
            env_service = overlay.get(workload) or {}
            values_file = env_service.get("values_file", base_service.get("values_file"))
            if not isinstance(values_file, str) or not values_file:
                continue
            resolved = (root / values_file.replace("{env}", env)).resolve()
            try:
                path = resolved.relative_to(root.resolve()).as_posix()
            except ValueError as error:
                raise ValueError(f"gke/{workload}: values_file must be inside the repository") from error
            bindings.setdefault((path, env), []).append(workload)
    return bindings


def extract_deploy_declarations(root: Path) -> list[Declaration]:
    files = [
        root / "backend/deploy/runtime_env" / name for name in ("_base.yaml", "dev.overlay.yaml", "prod.overlay.yaml")
    ]
    # Track the index so sparse checkouts still see unmaterialised chart files.
    files += [
        root / path
        for path in tracked_code_paths(root)
        if path.startswith("backend/charts/")
        and path.endswith("values.yaml")
        and Path(path).name.startswith(("dev_", "prod_"))
    ]
    bindings = _validated_chart_bindings(root)
    # A referenced chart need not use the conventional dev_/prod_ filename.
    files += [root / path for path, _ in bindings]
    files = list(dict.fromkeys(files))
    reads: list[Declaration] = []
    for file in files:
        path = file.relative_to(root).as_posix()
        text = source_text(root, path)
        if text is None:
            continue
        chart = "/charts/" in path or any(bound_path == path for bound_path, _ in bindings)
        if not chart:
            environments = ("dev", "prod") if file.name == "_base.yaml" else (file.name.split(".")[0],)
        elif file.name.startswith(("dev_", "prod_")):
            environments = (file.name.split("_")[0],)
        else:
            environments = tuple(sorted(env for bound_path, env in bindings if bound_path == path))
        try:
            tree = yaml.compose(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        except yaml.YAMLError as error:
            raise ValueError(f"{path}: invalid declaration YAML: {error}") from error
        fields = {key.value: value for key, value in tree.value} if isinstance(tree, yaml.MappingNode) else {}
        # Independent releases may share a chart (e.g. CPU LID).
        release = fields.get("fullnameOverride")
        release_name = release.value if isinstance(release, yaml.ScalarNode) else ""
        workload = re.sub(r"^(?:dev|prod)-omi-", "", release_name) or file.parent.name
        for node, parents in _yaml_mappings(tree):
            if chart:
                fields = {key.value: value for key, value in node.value}
                key_node = fields.get("name")
                candidates = [key_node] if isinstance(key_node, yaml.ScalarNode) else []
                platform = "gke"
                source = path
            else:
                section = parents[1:] if parents[:1] in {("environment_shared",), ("overlay",)} else parents
                identity = _manifest_workload(section)
                if identity is None:
                    continue
                platform, workload = identity
                source = f"backend/deploy/runtime_env#{workload}"
                candidates = [key for key, _ in node.value if isinstance(key, yaml.ScalarNode)]
            for key_node in candidates:
                key = key_node.value
                if re.fullmatch(r"[A-Z][A-Z0-9_]+", key) and (FLAG_SUFFIX.search(key) or "ALLOWLIST" in key):
                    for env in environments:
                        # The referenced chart and expected GKE env are one source.
                        # Unreferenced charts retain their own source file identity.
                        owners = bindings.get((path, env), []) if chart else []
                        if owners:
                            reads.extend(
                                Declaration(
                                    key,
                                    path,
                                    key_node.start_mark.line + 1,
                                    "gke",
                                    owner,
                                    env,
                                    f"backend/deploy/runtime_env#{owner}",
                                )
                                for owner in owners
                            )
                        else:
                            reads.append(
                                Declaration(key, path, key_node.start_mark.line + 1, platform, workload, env, source)
                            )
    return reads


def _action_targets(path: str, text: str, start: int) -> tuple[str, str, tuple[str, ...]]:
    # Follow shell continuations in both directions, including flags after the env payload.
    begin = text.rfind("\n", 0, start) + 1
    while begin > 0 and text[:begin].rstrip("\n").endswith("\\"):
        begin = text.rfind("\n", 0, begin - 1) + 1
    end = text.find("\n", start)
    while end >= 0 and text[:end].endswith("\\"):
        end = text.find("\n", end + 1)
    command = text[begin : end if end >= 0 else len(text)].replace("\\\n", " ")
    targets = list(
        re.finditer(
            r"gcloud\s+run\s+(?:services\s+(?:update|replace)|deploy|jobs\s+(?:update|deploy))\s+[\"']?([a-z][a-z0-9-]*)",
            command[: start - begin],
        )
    )
    target = targets[-1] if targets else None
    if target is None:
        raise ValueError(f"{path}: cannot resolve workload for flag declaration; use the runtime manifest or chart")
    name = target[1]
    kind = "jobs" if "jobs" in target[0].split() else "services"
    platform = "cloud_run_job" if kind == "jobs" else "cloud_run_service"
    workload = f"cloud_run/{kind}/{name}"
    if re.search(r"--project(?:=|\s+)[\"']?based-hardware(?:[\"'\s]|$)", command):
        environments = ("prod",)
    elif re.search(r"--project(?:=|\s+)[\"']?based-hardware-dev(?:[\"'\s]|$)", command):
        environments = ("dev",)
    elif "prod" in Path(path).name:
        environments = ("prod",)
    else:
        # Shared actions and dispatch-selected environments can deploy to either environment.
        environments = ("dev", "prod")
    return platform, workload, environments


def extract_action_declarations(root: Path) -> list[Declaration]:
    """Find ramp/allowlist literals paired with their deployed workload and environment."""
    files = list((root / ".github/actions").rglob("action.yml"))
    files.extend((root / ".github/workflows").glob("*prod*.y*ml"))
    reads: list[Declaration] = []
    for file in files:
        if not file.is_file():
            continue
        path = file.relative_to(root).as_posix()
        text = file.read_text(encoding="utf-8")
        for match in ACTION_ENV_ARG.finditer(text):
            payload = next((value for value in match.groups() if value is not None), "")
            line = text.count("\n", 0, match.start()) + 1
            for item in payload.replace("\\\n", "").split(","):
                key, separator, _ = item.partition("=")
                key = key.strip()
                if separator and ("PERCENT" in key or "ALLOWLIST" in key):
                    platform, workload, environments = _action_targets(path, text, match.start())
                    reads.extend(Declaration(key, path, line, platform, workload, env, path) for env in environments)
        if path == ".github/actions/sync-backfill-lifecycle/action.yml":
            in_output = False
            for lineno, raw in enumerate(text.splitlines(), 1):
                if 'echo "sync_backfill_env_vars<<EOF"' in raw:
                    in_output = True
                    continue
                if in_output and 'echo "EOF"' in raw:
                    break
                if in_output:
                    assignment = ACTION_ASSIGNMENT.match(raw.strip().removeprefix('echo "').removesuffix('"'))
                    if assignment and ("PERCENT" in assignment[1] or "ALLOWLIST" in assignment[1]):
                        reads.extend(
                            Declaration(
                                assignment[1],
                                path,
                                lineno,
                                "cloud_run_service",
                                "cloud_run/services/backend-sync-backfill",
                                env,
                                path,
                            )
                            for env in ("dev", "prod")
                        )
    return reads


def duplicate_declaration_sources(declarations: list[Declaration]) -> dict[tuple[str, str, str, str], list[str]]:
    """Reject independent sources; overlays and values_file-validated pairs compose."""
    sources: dict[tuple[str, str, str, str], set[str]] = {}
    for declaration in declarations:
        if "PERCENT" in declaration.key or "ALLOWLIST" in declaration.key:
            identity = (declaration.key, declaration.platform, declaration.workload, declaration.environment)
            sources.setdefault(identity, set()).add(declaration.source)
    return {identity: sorted(paths) for identity, paths in sorted(sources.items()) if len(paths) > 1}


def overdue(registry: dict[str, list[dict[str, Any]]], as_of: date) -> list[str]:
    return sorted(
        entry["key"]
        for entry in registry.get("flags", [])
        if entry.get("lifecycle") in {"rollout", "experiment"}
        and entry.get("review_by")
        and effective_due(entry) < as_of
    )


def overdue_beyond_grace(registry: dict[str, list[dict[str, Any]]], as_of: date) -> list[str]:
    """Return rollout/experiment rows whose review date plus the grace has passed."""
    return sorted(
        entry["key"]
        for entry in registry.get("flags", [])
        if entry.get("lifecycle") in {"rollout", "experiment"}
        and entry.get("review_by")
        and effective_due(entry) + timedelta(days=REVIEW_GRACE_DAYS) < as_of
    )
