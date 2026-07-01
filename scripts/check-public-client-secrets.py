#!/usr/bin/env python3
"""Guard public client builds from server-only secrets.

This script enforces the policy in app/config/client_env_policy.yaml. It is
deliberately stdlib-only so it can run in git hooks, Codemagic, and GitHub
Actions before language-specific setup.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "app" / "config" / "client_env_policy.yaml"
APP_LIB = ROOT / "app" / "lib"


def load_policy() -> dict:
    with POLICY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def compile_patterns(policy: dict) -> list[re.Pattern[str]]:
    patterns = policy["server_secret_env"]["denied_name_patterns"]
    return [re.compile(pattern) for pattern in patterns]


def denied_names(policy: dict) -> set[str]:
    return set(policy["server_secret_env"]["denied_exact"])


def allowed_names(policy: dict) -> set[str]:
    return set(policy["public_client_env"]["allowed"]) | set(
        policy.get("legacy_public_client_env", {}).get("allowed", [])
    )


def name_is_denied(name: str, exact: set[str], patterns: list[re.Pattern[str]]) -> bool:
    return name in exact or any(pattern.search(name) for pattern in patterns)


def git_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def check_policy_shape(policy: dict) -> list[str]:
    errors: list[str] = []
    allowed = allowed_names(policy)
    public_prefixed = set(policy["public_client_env"]["allowed"])
    exact = denied_names(policy)
    patterns = compile_patterns(policy)
    restricted = policy.get("restricted_public_client_keys", {})

    for name in sorted(public_prefixed):
        if not name.startswith("PUBLIC_"):
            errors.append(f"{POLICY_PATH}: public client env name must use PUBLIC_ prefix: {name}")
        if name_is_denied(name, exact, patterns):
            errors.append(f"{POLICY_PATH}: public client env name matches denied secret policy: {name}")

    for name, metadata in sorted(restricted.items()):
        if name not in allowed:
            errors.append(f"{POLICY_PATH}: restricted public key {name} must also be in public_client_env.allowed")
        for field in ("owner", "purpose", "restriction", "revocation"):
            if not str(metadata.get(field, "")).strip():
                errors.append(f"{POLICY_PATH}: restricted public key {name} is missing {field}")

    return errors


def check_env_file(path: Path, policy: dict) -> list[str]:
    errors: list[str] = []
    allowed = allowed_names(policy)
    exact = denied_names(policy)
    patterns = compile_patterns(policy)

    if not path.exists():
        return errors

    for lineno, raw in enumerate(read_text(path).splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split("=", 1)[0].strip()
        if not name:
            continue
        if name not in allowed:
            errors.append(f"{path}:{lineno}: {name} is not in public_client_env.allowed")
        if name_is_denied(name, exact, patterns):
            errors.append(f"{path}:{lineno}: {name} is server-only and cannot enter public client env")

    return errors


def check_app_source(policy: dict) -> list[str]:
    errors: list[str] = []
    exact = denied_names(policy)
    source_roots = [APP_LIB, ROOT / "app" / "ios", ROOT / "app" / "android", ROOT / "app" / "macos"]
    suffixes = {".dart", ".swift", ".kt", ".java", ".m", ".mm", ".h", ".plist", ".xml", ".gradle"}

    files = [
        path
        for path in git_files()
        if path.exists()
        if any(path.is_relative_to(root) for root in source_roots)
        and path.suffix in suffixes
        and not path.name.endswith(".g.dart")
        and not path.name.endswith(".gen.dart")
    ]

    for path in files:
        text = read_text(path)
        rel = path.relative_to(ROOT)
        for name in exact:
            if name in text:
                errors.append(f"{rel}: references server-only env name {name}")
    generated = [ROOT / "app" / "lib" / "env" / "prod_env.g.dart", ROOT / "app" / "lib" / "env" / "dev_env.g.dart"]
    for path in generated:
        if not path.exists():
            continue
        text = read_text(path)
        rel = path.relative_to(ROOT)
        for name in exact:
            if name in text:
                errors.append(f"{rel}: generated Envied output contains server-only env name {name}")

    return errors


def check_codemagic(policy: dict) -> list[str]:
    errors: list[str] = []
    path = ROOT / "codemagic.yaml"
    if not path.exists():
        return errors

    allowed = allowed_names(policy)
    exact = denied_names(policy)
    patterns = compile_patterns(policy)
    text = read_text(path)

    for lineno, line in enumerate(text.splitlines(), start=1):
        echo_match = re.search(r"echo\s+([A-Z0-9_]+)=.*>>\s+.*(?:^|\s)(?:\.env|\.client\.env)", line)
        if echo_match:
            name = echo_match.group(1)
            if name not in allowed:
                errors.append(
                    f"{path.relative_to(ROOT)}:{lineno}: Codemagic writes non-allowlisted {name} into client env"
                )
            if name_is_denied(name, exact, patterns):
                errors.append(f"{path.relative_to(ROOT)}:{lineno}: Codemagic writes server-only {name} into client env")

        if "Set up App .env" in line:
            errors.append(
                f"{path.relative_to(ROOT)}:{lineno}: use Generate public client config, not hand-written App .env"
            )

    return errors


def check_public_templates(policy: dict) -> list[str]:
    errors: list[str] = []
    exact = denied_names(policy)
    templates = [ROOT / "app" / ".env.template", ROOT / "app" / ".client.env.example"]
    for path in templates:
        if not path.exists():
            continue
        text = read_text(path)
        rel = path.relative_to(ROOT)
        for name in exact:
            if name in text:
                errors.append(f"{rel}: public app env template references server-only {name}")
    return errors


def check_docker_secret_baking(policy: dict) -> list[str]:
    errors: list[str] = []
    exact = denied_names(policy)
    patterns = compile_patterns(policy)

    dockerfiles = [
        path
        for path in git_files()
        if path.exists() and (path.name == "Dockerfile" or path.name.startswith("Dockerfile."))
    ]
    for path in dockerfiles:
        text = read_text(path)
        rel = path.relative_to(ROOT)
        secret_args: set[str] = set()
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("ARG "):
                name = stripped.removeprefix("ARG ").split("=", 1)[0].strip()
                if name_is_denied(name, exact, patterns) and not name.startswith("NEXT_PUBLIC_"):
                    secret_args.add(name)
                    errors.append(f"{rel}:{lineno}: server-only build ARG {name} can leak through image history")
            if stripped.startswith("ENV "):
                for name in exact | secret_args:
                    if name in stripped and not name.startswith("NEXT_PUBLIC_"):
                        errors.append(f"{rel}:{lineno}: server-only {name} is promoted into final image ENV")

    workflow_files = [path for path in git_files() if path.exists() and path.match(".github/workflows/*.yml")]
    for path in workflow_files:
        text = read_text(path)
        rel = path.relative_to(ROOT)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "--build-arg" not in line:
                continue
            for name in exact:
                if name in line and not name.startswith("NEXT_PUBLIC_"):
                    errors.append(f"{rel}:{lineno}: server-only {name} is passed as docker build-arg")
            for match in re.finditer(r"--build-arg\s+([A-Z0-9_]+)=", line):
                name = match.group(1)
                if name_is_denied(name, exact, patterns) and not name.startswith("NEXT_PUBLIC_"):
                    errors.append(f"{rel}:{lineno}: server-only {name} is passed as docker build-arg")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", action="append", default=[], help="public client env file to validate")
    args = parser.parse_args()

    policy = load_policy()
    errors: list[str] = []
    errors.extend(check_policy_shape(policy))

    env_files = [Path(raw).resolve() for raw in args.env_file]
    env_files.extend(
        [ROOT / "app" / ".client.env", ROOT / "app" / ".client.dev.env", ROOT / "app" / ".client.env.example"]
    )
    for path in env_files:
        errors.extend(check_env_file(path, policy))

    errors.extend(check_app_source(policy))
    errors.extend(check_codemagic(policy))
    errors.extend(check_public_templates(policy))
    errors.extend(check_docker_secret_baking(policy))

    if errors:
        print("Public client secret boundary check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Public client secret boundary check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
