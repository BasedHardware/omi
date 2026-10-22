from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
from run_checks import _parse_yaml_subset

KINDS = {"env", "posthog", "bundle", "server_capability", "build_define", "firestore", "hardcoded"}
LIFECYCLES = {"experiment", "rollout", "ops_kill", "config_switch"}
SURFACES = {"backend", "macos", "windows", "web-app", "web-admin", "web-frontend", "mobile", "llm-gateway"}
FAILS = {"open", "closed", "inverted"}
DECISIONS = {"pending", "graduate", "ship", "kill", "kill_after_readout", "keep", "with_legacy"}
TERMINALS = {"on", "off", "keep", "undecided"}
REVIEW_GRACE_DAYS = 7
RAMP_REQUIRED_FROM = date(2026, 10, 21)
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
CHART_KEY = re.compile(r"^\s*-\s*name:\s*['\"]?([A-Z][A-Z0-9_]+)")
MANIFEST_KEY = re.compile(r"^\s*([A-Z][A-Z0-9_]+):(?:\s|$)")
ACTION_ENV_ARG = re.compile(r"--(?:update|set)-env-vars(?:=|\s+)(?:\"([^\"]*)\"|'([^']*)'|([^\s\\]+))", re.S)
ACTION_ASSIGNMENT = re.compile(r"^\s*([A-Z][A-Z0-9_]+)=([^,\s]+)")


@dataclass(frozen=True)
class Read:
    key: str
    path: str
    line: int


def load_registry(path: Path) -> dict[str, list[dict[str, Any]]]:
    return _parse_yaml_subset(path)


def _ramp_applies_to(entry: dict[str, Any]) -> bool:
    return entry.get("lifecycle") == "rollout" and (
        entry.get("decision") in {"pending", "undecided"} or entry.get("terminal") == "undecided"
    )


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


def validate_registry(registry: dict[str, list[dict[str, Any]]], *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
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
        if not relevant_code(path) or not (root / path).is_file():
            continue
        text = (root / path).read_text(encoding="utf-8")
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


def extract_deploy_declarations(root: Path) -> list[Read]:
    files = [
        root / "backend/deploy/runtime_env" / name for name in ("_base.yaml", "dev.overlay.yaml", "prod.overlay.yaml")
    ]
    files += [p for p in (root / "backend/charts").rglob("*values.yaml") if p.name.startswith(("dev_", "prod_"))]
    reads: list[Read] = []
    for file in files:
        if not file.is_file():
            continue
        for lineno, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            pattern = CHART_KEY if "/charts/" in file.as_posix() else MANIFEST_KEY
            match = pattern.match(line)
            if match and (FLAG_SUFFIX.search(match[1]) or "ALLOWLIST" in match[1]):
                reads.append(Read(match[1], file.relative_to(root).as_posix(), lineno))
    return reads


def extract_action_declarations(root: Path) -> list[Read]:
    """Find ramp-percent/allowlist values emitted by deploy actions and prod workflows."""
    files = list((root / ".github/actions").rglob("action.yml"))
    files.extend((root / ".github/workflows").glob("*prod*.y*ml"))
    reads: list[Read] = []
    for file in files:
        if not file.is_file():
            continue
        text = file.read_text(encoding="utf-8")
        for match in ACTION_ENV_ARG.finditer(text):
            payload = next((value for value in match.groups() if value is not None), "")
            line = text.count("\n", 0, match.start()) + 1
            for item in payload.replace("\\\n", "").split(","):
                key, separator, _ = item.partition("=")
                key = key.strip()
                if separator and ("PERCENT" in key or "ALLOWLIST" in key):
                    reads.append(Read(key, file.relative_to(root).as_posix(), line))
        if file.as_posix().endswith(".github/actions/sync-backfill-lifecycle/action.yml"):
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
                        reads.append(Read(assignment[1], file.relative_to(root).as_posix(), lineno))
    return reads


def duplicate_declaration_sources(declarations: list[Read]) -> dict[str, list[str]]:
    """Return ramp-percent/allowlist keys declared in multiple source files."""
    sources: dict[str, set[str]] = {}
    for declaration in declarations:
        if "PERCENT" in declaration.key or "ALLOWLIST" in declaration.key:
            sources.setdefault(declaration.key, set()).add(declaration.path)
    return {key: sorted(paths) for key, paths in sorted(sources.items()) if len(paths) > 1}


def overdue(registry: dict[str, list[dict[str, Any]]], as_of: date) -> list[str]:
    return sorted(
        entry["key"]
        for entry in registry.get("flags", [])
        if entry.get("lifecycle") in {"rollout", "experiment"}
        and entry.get("review_by")
        and date.fromisoformat(entry["review_by"]) < as_of
    )


def overdue_beyond_grace(registry: dict[str, list[dict[str, Any]]], as_of: date) -> list[str]:
    """Return rollout/experiment rows whose review date plus the grace has passed."""
    return sorted(
        entry["key"]
        for entry in registry.get("flags", [])
        if entry.get("lifecycle") in {"rollout", "experiment"}
        and entry.get("review_by")
        and date.fromisoformat(entry["review_by"]) + timedelta(days=REVIEW_GRACE_DAYS) < as_of
    )
