#!/usr/bin/env python3
"""Diff-ratchet deployment setting classifications without inspecting values.

The checker deliberately reads only names in checked-in deployment wiring. It
never loads environment variables, Secret Manager data, or rendered manifests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "config" / "deployment-setting-classification.json"
EXPRESSION = re.compile(r"\$\{\{\s*(secrets|vars)\.([A-Z][A-Z0-9_]*)\s*}}")
UPPER_VALUE = r"([A-Z][A-Z0-9_]*)"
KEY_VALUE = re.compile(rf"^\s*(?:secretKey|remoteKey):\s*{UPPER_VALUE}\s*(?:#.*)?$")
CLOUD_RUN_SECRET = re.compile(rf"^\s*secret:\s*{UPPER_VALUE}\s*(?:#.*)?$")
YAML_KEY = re.compile(r"^(\s*)([A-Z][A-Z0-9_]*):\s*(?:#.*)?$")
YAML_VALUE = re.compile(r"^\s*(?:value|env_var):")
HELM_ENV_NAME = re.compile(rf"^\s*-\s*name:\s*{UPPER_VALUE}\s*(?:#.*)?$")
HELM_SECRET_KEY = re.compile(rf"^\s*key:\s*{UPPER_VALUE}\s*(?:#.*)?$")
CLOUD_RUN_SECRET_LINE = re.compile(rf"^\s*{UPPER_VALUE}={UPPER_VALUE}(?::[^\s#]+)?\s*(?:#.*)?$")
SECRET_MANAGER_OUTPUT = re.compile(
    rf'^\s*echo\s+["\']?({UPPER_VALUE})=\$\(gcloud\s+secrets\s+versions\s+access\b.*?--secret={UPPER_VALUE}'
)


@dataclass(frozen=True, order=True)
class Binding:
    path: str
    source: str
    name: str


def _value_from_match(match: re.Match[str], group: int = 1) -> str:
    return match.group(group)


def _deployment_paths(root: Path) -> set[str]:
    paths = {
        str(path.relative_to(root))
        for path in (root / ".github" / "workflows").glob("*.y*ml")
        if path.is_file()
    }
    for relative in ("backend/deploy/runtime_env.yaml",):
        if (root / relative).is_file():
            paths.add(relative)
    charts = root / "backend" / "charts"
    if charts.is_dir():
        paths.update(
            str(path.relative_to(root))
            for path in charts.glob("*/*_values.yaml")
            if path.is_file()
        )
    return paths


def _git_environment() -> dict[str, str]:
    """Avoid hook-scoped Git paths when inspecting an explicit repository root."""
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


def _base_paths(root: Path, base: str) -> set[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", base],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        env=_git_environment(),
    )
    paths = set(result.stdout.splitlines())
    return {
        path
        for path in paths
        if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))
        or path == "backend/deploy/runtime_env.yaml"
        or re.fullmatch(r"backend/charts/[^/]+/[^/]+_values\.yaml", path) is not None
    }


def _read_base_file(root: Path, base: str, relative_path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{base}:{relative_path}"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=_git_environment(),
    )
    return result.stdout if result.returncode == 0 else None


def _extract_bindings(relative_path: str, text: str) -> set[Binding]:
    bindings: set[Binding] = set()
    helm_env_name: str | None = None
    helm_secret_indent: int | None = None
    cloud_run_secrets_indent: int | None = None
    yaml_keys: list[tuple[int, str]] = []
    lines = text.splitlines()

    for line in lines:
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        for expression in EXPRESSION.finditer(line):
            source, name = expression.groups()
            bindings.add(Binding(relative_path, f"github_{source}", name))

        secret_manager_output = SECRET_MANAGER_OUTPUT.match(line)
        if secret_manager_output:
            bindings.add(Binding(relative_path, "secret_manager", secret_manager_output.group(1)))

        key_value = KEY_VALUE.match(line)
        if key_value:
            bindings.add(Binding(relative_path, "external_secret", _value_from_match(key_value)))

        cloud_run_secret = CLOUD_RUN_SECRET.match(line)
        if cloud_run_secret:
            bindings.add(Binding(relative_path, "cloud_run_secret", _value_from_match(cloud_run_secret)))

        if helm_secret_indent is not None and stripped and indent <= helm_secret_indent:
            helm_secret_indent = None
        if stripped == "secretKeyRef:":
            helm_secret_indent = indent
        elif helm_secret_indent is not None:
            helm_secret_key = HELM_SECRET_KEY.match(line)
            if helm_secret_key:
                bindings.add(Binding(relative_path, "helm_secret", _value_from_match(helm_secret_key)))

        if cloud_run_secrets_indent is not None and stripped and indent <= cloud_run_secrets_indent:
            cloud_run_secrets_indent = None
        if stripped == "secrets:":
            cloud_run_secrets_indent = indent
        elif cloud_run_secrets_indent is not None:
            cloud_run_secret_line = CLOUD_RUN_SECRET_LINE.match(line)
            if cloud_run_secret_line:
                remote_name = cloud_run_secret_line.group(2)
                bindings.add(Binding(relative_path, "cloud_run_secret", remote_name))

        helm_env = HELM_ENV_NAME.match(line)
        if helm_env:
            helm_env_name = _value_from_match(helm_env)
        elif stripped.startswith("- "):
            helm_env_name = None
        elif helm_env_name is not None and re.match(r"^\s*value:\s*", line):
            bindings.add(Binding(relative_path, "normal_env", helm_env_name))

        while yaml_keys and indent <= yaml_keys[-1][0]:
            yaml_keys.pop()
        yaml_key = YAML_KEY.match(line)
        if yaml_key:
            yaml_keys.append((len(yaml_key.group(1)), yaml_key.group(2)))
        elif yaml_keys and indent > yaml_keys[-1][0] and YAML_VALUE.match(line):
            bindings.add(Binding(relative_path, "normal_env", yaml_keys[-1][1]))

    return bindings


def extract_current_bindings(root: Path) -> set[Binding]:
    bindings: set[Binding] = set()
    for relative_path in _deployment_paths(root):
        bindings.update(_extract_bindings(relative_path, (root / relative_path).read_text(encoding="utf-8")))
    return bindings


def extract_base_bindings(root: Path, base: str) -> set[Binding]:
    bindings: set[Binding] = set()
    for relative_path in _base_paths(root, base):
        content = _read_base_file(root, base, relative_path)
        if content is not None:
            bindings.update(_extract_bindings(relative_path, content))
    return bindings


def load_policy(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        policy = json.load(handle)
    if not isinstance(policy, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return policy


def _policy_kinds(policy: dict[str, object]) -> dict[str, set[str]]:
    raw_kinds = policy.get("kinds")
    if not isinstance(raw_kinds, dict):
        raise ValueError("policy.kinds must be an object")
    kinds: dict[str, set[str]] = {}
    for kind in ("secret", "config", "public_build"):
        names = raw_kinds.get(kind)
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ValueError(f"policy.kinds.{kind} must be a list of names")
        kinds[kind] = set(names)
    return kinds


def validate_policy(policy: dict[str, object]) -> list[str]:
    errors: list[str] = []
    try:
        kinds = _policy_kinds(policy)
    except ValueError as exc:
        return [str(exc)]
    seen: dict[str, str] = {}
    for kind, names in kinds.items():
        for name in names:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                errors.append(f"{kind} classification has invalid name {name!r}")
            if name in seen:
                errors.append(f"{name} is classified as both {seen[name]} and {kind}")
            seen[name] = kind

    exceptions = policy.get("exceptions", {})
    if not isinstance(exceptions, dict):
        return errors + ["policy.exceptions must be an object"]
    today = dt.date.today()
    for name, raw_metadata in sorted(exceptions.items()):
        if name not in seen:
            errors.append(f"exception {name} must also be classified")
        if not isinstance(raw_metadata, dict):
            errors.append(f"exception {name} must be an object")
            continue
        for field in ("owner", "reason", "expires", "allowed_sources"):
            if not raw_metadata.get(field):
                errors.append(f"exception {name} is missing {field}")
        expiry = raw_metadata.get("expires")
        if isinstance(expiry, str):
            try:
                if dt.date.fromisoformat(expiry) < today:
                    errors.append(f"exception {name} expired on {expiry}")
            except ValueError:
                errors.append(f"exception {name} has invalid ISO expiry {expiry!r}")
        allowed_sources = raw_metadata.get("allowed_sources")
        if not isinstance(allowed_sources, list) or not all(isinstance(source, str) for source in allowed_sources):
            errors.append(f"exception {name} allowed_sources must be a list")
    return errors


def _classification(policy: dict[str, object], name: str) -> str | None:
    for kind, names in _policy_kinds(policy).items():
        if name in names:
            return kind
    return None


def _exception_allows(policy: dict[str, object], binding: Binding) -> bool:
    exceptions = policy.get("exceptions", {})
    metadata = exceptions.get(binding.name) if isinstance(exceptions, dict) else None
    return isinstance(metadata, dict) and binding.source in metadata.get("allowed_sources", [])


def _expected_kinds(source: str) -> set[str]:
    if source == "github_vars":
        return {"config", "public_build"}
    if source == "normal_env":
        return {"config", "public_build"}
    return {"secret"}


def validate_bindings(
    policy: dict[str, object], current_bindings: Iterable[Binding], base_bindings: Iterable[Binding]
) -> list[str]:
    errors: list[str] = []
    current = set(current_bindings)
    new_or_changed = current - set(base_bindings)

    # Public build configuration is an explicit migration target, not legacy
    # debt. Reject it even when a pre-ratchet line still exists in the base.
    to_validate = new_or_changed | {
        binding for binding in current if binding.source == "github_secrets" and _classification(policy, binding.name) == "public_build"
    }
    for binding in sorted(to_validate):
        kind = _classification(policy, binding.name)
        if kind is None:
            errors.append(f"{binding.path}: {binding.source} binding {binding.name} is unclassified")
            continue
        expected = _expected_kinds(binding.source)
        if kind in expected or _exception_allows(policy, binding):
            continue
        if binding.source == "github_secrets" and kind == "public_build":
            errors.append(f"{binding.path}: public_build setting {binding.name} must use vars.{binding.name}, not secrets.{binding.name}")
        else:
            expected_text = " or ".join(sorted(expected))
            errors.append(
                f"{binding.path}: {binding.source} binding {binding.name} is {kind}; expected {expected_text}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff-ratchet deployment setting classifications.")
    parser.add_argument("--base", required=True, help="Git ref used as the legacy binding baseline.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    policy_path = (args.policy or root / DEFAULT_POLICY.relative_to(ROOT)).resolve()
    try:
        policy = load_policy(policy_path)
        errors = validate_policy(policy)
        errors.extend(validate_bindings(policy, extract_current_bindings(root), extract_base_bindings(root, args.base)))
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"deployment secret-boundary check failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("deployment secret-boundary check failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("deployment secret-boundary check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
