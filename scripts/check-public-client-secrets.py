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
LEGACY_DIRECT_PROVIDER_ALLOW_COMMENT = "public-client-secret-boundary: legacy-direct-provider"


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


def allowed_public_names(policy: dict) -> set[str]:
    return allowed_names(policy) | set(policy.get("public_web_build_args", {}).get("allowed", []))


def name_is_denied(name: str, exact: set[str], patterns: list[re.Pattern[str]]) -> bool:
    return name in exact or any(pattern.search(name) for pattern in patterns)


def variable_like_tokens(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", text))


def line_reads_env_or_config(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in ("env", "getenv", "process.env", "platform.environment", "buildconfig"))


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


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def denied_env_values(policy: dict) -> dict[str, str]:
    exact = denied_names(policy)
    patterns = compile_patterns(policy)
    return {
        name: value
        for name, value in os.environ.items()
        if value
        and len(value) >= 8
        and not name.startswith(("PUBLIC_", "NEXT_PUBLIC_"))
        and name_is_denied(name, exact, patterns)
    }


def check_duplicate_yaml_keys(path: Path) -> list[str]:
    errors: list[str] = []
    seen_by_indent: dict[int, set[str]] = {}
    block_scalar_indent: int | None = None
    key_re = re.compile(r"^(\s*)(?:[\"']?)([A-Za-z0-9_.-]+)(?:[\"']?):(?:\s.*)?$")

    for lineno, raw in enumerate(read_text(path).splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if block_scalar_indent is not None:
            if indent > block_scalar_indent:
                continue
            block_scalar_indent = None
        if raw.lstrip().startswith("- "):
            for existing_indent in list(seen_by_indent):
                if existing_indent > indent:
                    del seen_by_indent[existing_indent]

        match = key_re.match(raw)
        if not match:
            continue
        key = match.group(2)
        line_tail = raw.split(":", 1)[1].strip()
        if line_tail in {"|", "|-", "|+", ">", ">-", ">+"}:
            block_scalar_indent = indent

        for existing_indent in list(seen_by_indent):
            if existing_indent > indent:
                del seen_by_indent[existing_indent]
        seen = seen_by_indent.setdefault(indent, set())
        if key in seen:
            errors.append(f"{display_path(path)}:{lineno}: duplicate YAML key {key!r} at indent {indent}")
        seen.add(key)

    return errors


def check_policy_shape(policy: dict) -> list[str]:
    errors: list[str] = []
    allowed = allowed_names(policy)
    public_prefixed = set(policy["public_client_env"]["allowed"])
    exact = denied_names(policy)
    patterns = compile_patterns(policy)
    restricted = policy.get("restricted_public_client_keys", {})
    direct_provider_exceptions = policy.get("legacy_direct_provider_domain_exceptions", {})
    allowed_build_secret_source_refs = set(policy.get("allowed_build_secret_source_references", []))

    for name in sorted(public_prefixed):
        if not name.startswith("PUBLIC_"):
            errors.append(f"{POLICY_PATH}: public client env name must use PUBLIC_ prefix: {name}")
        if name_is_denied(name, exact, patterns) and name not in restricted:
            errors.append(f"{POLICY_PATH}: denied-looking public client env name {name} needs restricted metadata")
    for name, metadata in sorted(restricted.items()):
        if name not in allowed:
            errors.append(f"{POLICY_PATH}: restricted public key {name} must also be in public_client_env.allowed")
        for field in ("owner", "purpose", "restriction", "revocation"):
            if not str(metadata.get(field, "")).strip():
                errors.append(f"{POLICY_PATH}: restricted public key {name} is missing {field}")

    for path, metadata in sorted(direct_provider_exceptions.items()):
        exception_path = ROOT / path
        if not exception_path.exists():
            errors.append(f"{POLICY_PATH}: legacy direct-provider exception points at missing file: {path}")
        for field in ("owner", "reason", "migration"):
            if not str(metadata.get(field, "")).strip():
                errors.append(f"{POLICY_PATH}: legacy direct-provider exception {path} is missing {field}")
        allowed_occurrences = metadata.get("allowed_occurrences")
        if not isinstance(allowed_occurrences, dict) or not allowed_occurrences:
            errors.append(f"{POLICY_PATH}: legacy direct-provider exception {path} must pin allowed_occurrences")
        else:
            for domain, count in allowed_occurrences.items():
                if domain not in policy.get("direct_provider_domains_denied_in_app", []):
                    errors.append(
                        f"{POLICY_PATH}: legacy direct-provider exception {path} pins unknown domain {domain}"
                    )
                if not isinstance(count, int) or count < 0:
                    errors.append(
                        f"{POLICY_PATH}: legacy direct-provider exception {path} has invalid count for {domain}"
                    )
            if exception_path.exists():
                text = read_text(exception_path)
                for domain in policy.get("direct_provider_domains_denied_in_app", []):
                    actual = text.count(domain)
                    expected = int(allowed_occurrences.get(domain, 0))
                    if actual != expected:
                        errors.append(
                            f"{path}: legacy direct-provider domain {domain} count changed: expected {expected}, found {actual}"
                        )
                for lineno, line in enumerate(text.splitlines(), start=1):
                    for domain in policy.get("direct_provider_domains_denied_in_app", []):
                        if domain in line and LEGACY_DIRECT_PROVIDER_ALLOW_COMMENT not in line:
                            errors.append(
                                f"{path}:{lineno}: legacy direct-provider domain {domain} needs inline allow comment"
                            )

    for name in sorted(allowed_build_secret_source_refs):
        if not name_is_denied(name, exact, patterns):
            errors.append(f"{POLICY_PATH}: allowed build secret source reference is not denied by policy: {name}")

    return errors


def check_env_file(path: Path, policy: dict) -> list[str]:
    errors: list[str] = []
    allowed = allowed_names(policy)
    exact = denied_names(policy)
    patterns = compile_patterns(policy)
    private_values = denied_env_values(policy)

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
        if name not in allowed and name_is_denied(name, exact, patterns):
            errors.append(f"{path}:{lineno}: {name} is server-only and cannot enter public client env")
        value = line.split("=", 1)[1] if "=" in line else ""
        for env_name, private_value in private_values.items():
            if value == private_value:
                errors.append(f"{path}:{lineno}: value matches current private env value {env_name}")

    return errors


def check_app_source(policy: dict) -> list[str]:
    errors: list[str] = []
    exact = denied_names(policy)
    patterns = compile_patterns(policy)
    denied_domains = set(policy.get("direct_provider_domains_denied_in_app", []))
    legacy_domain_exceptions = set(policy.get("legacy_direct_provider_domain_exceptions", {}).keys())
    allowed_build_secret_source_refs = set(policy.get("allowed_build_secret_source_references", []))
    allowed_public = allowed_public_names(policy) | set(policy.get("allowed_public_client_tokens", []))
    source_roots = [
        APP_LIB,
        ROOT / "app" / "ios",
        ROOT / "app" / "android",
        ROOT / "app" / "macos",
        ROOT / "app" / "setup",
        ROOT / "app" / "setup.sh",
        ROOT / "app" / "initialsetup.bash",
    ]
    suffixes = {
        ".dart",
        ".swift",
        ".kt",
        ".java",
        ".m",
        ".mm",
        ".h",
        ".plist",
        ".xml",
        ".gradle",
        ".sh",
        ".bash",
        ".ps1",
        ".json",
        ".env",
    }

    files = [
        path
        for path in git_files()
        if path.exists()
        if path in source_roots
        or any(path.is_relative_to(root) for root in source_roots if root.is_dir())
        and path.suffix in suffixes
        and not path.name.endswith(".g.dart")
        and not path.name.endswith(".gen.dart")
    ]

    for path in files:
        text = read_text(path)
        rel = path.relative_to(ROOT)
        rel_text = str(rel)
        for name in exact:
            if name in text and name not in allowed_build_secret_source_refs and name not in allowed_public:
                errors.append(f"{rel}: references server-only env name {name}")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not line_reads_env_or_config(line):
                continue
            for token in variable_like_tokens(line):
                if (
                    token not in allowed_build_secret_source_refs
                    and token not in allowed_public
                    and name_is_denied(token, exact, patterns)
                ):
                    errors.append(f"{rel}:{lineno}: references server-only env-like token {token}")
        for domain in denied_domains:
            if domain in text and rel_text not in legacy_domain_exceptions:
                errors.append(f"{rel}: directly references denied provider domain {domain}")
    generated = [ROOT / "app" / "lib" / "env" / "prod_env.g.dart", ROOT / "app" / "lib" / "env" / "dev_env.g.dart"]
    for path in generated:
        if not path.exists():
            continue
        text = read_text(path)
        rel = path.relative_to(ROOT)
        for name in exact:
            if name in text and name not in allowed_public:
                errors.append(f"{rel}: generated Envied output contains server-only env name {name}")
        for token in variable_like_tokens(text):
            if token not in allowed_public and name_is_denied(token, exact, patterns):
                errors.append(f"{rel}: generated Envied output contains server-only env-like token {token}")

    return errors


PUBLIC_ENV_FILE_RE = re.compile(r"(?:^|/)(?:\.client(?:\.dev)?\.env|\.env)(?:[\"']|\s|$)")
ENV_WRITE_RE = re.compile(
    r"\b(?:echo|printf)\b.*(?:>|>>)\s*[\"']?(?:[^\"'\s>]*/)?(\.client(?:\.dev)?\.env|\.env)[\"']?"
)
PUBLIC_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?(PUBLIC_[A-Z0-9_]*)=(.+?)(?:\s*\\)?$")
PUBLIC_ASSIGNMENT_ANYWHERE_RE = re.compile(r"(?:^|\s)(PUBLIC_[A-Z0-9_]*)=(\"[^\"]*\"|'[^']*'|[^\s\\]+)")
ENV_REF_RE = re.compile(r"\$(?:\{?([A-Z][A-Z0-9_]*)\}?|{{\s*secrets\.([A-Z][A-Z0-9_]*)\s*}})")
PRINTENV_REF_RE = re.compile(r"printenv\s+([A-Z][A-Z0-9_]*)")
GITHUB_SECRET_RE = re.compile(r"secrets(?:\.|\[['\"])([A-Z][A-Z0-9_]*)")
SHELL_ASSIGNMENT_RE = re.compile(r"(?:^|\s)([A-Z][A-Z0-9_]*)=(\"[^\"]*\"|'[^']*'|[^\s\\]+)")
PUBLIC_ENV_TARGET_RE = re.compile(
    r"(?:^|[\s/\"'])(?:\.client(?:\.dev)?\.env|\.env|\.env\.production|\.env\.local)(?:[\"']|\s|$)"
)
SENSITIVE_ECHO_RE = re.compile(r"\b(?:echo|printf)\b")
SHELL_TRACE_RE = re.compile(r"(^|\s|[;&|]\s*)set\s+(?:-[A-Za-z]*x[A-Za-z]*|-o\s+xtrace)(\s|$|[;&|])")
SHELL_TRACE_OFF_RE = re.compile(r"(^|\s|[;&|]\s*)set\s+\+x(\s|$)")
STDOUT_REDIRECT_RE = re.compile(r"(^|\s|[;&|]\s*)(?:1?>|1?>>|&>|&>>)\s*\S")
SAFE_STDIN_SECRET_SINK_RE = re.compile(
    r"\|\s*(?:\"[^\"]*sign_update\"|\S*sign_update)\b[^|]*--ed-key-file\s+-"
    r"|\|\s*docker\s+login\b[^|]*--password-stdin"
)


def check_codemagic(policy: dict) -> list[str]:
    errors: list[str] = []
    path = ROOT / "codemagic.yaml"
    if not path.exists():
        return errors

    allowed = allowed_names(policy)
    allowed_public = allowed_public_names(policy)
    allowed_public_sources = set(policy.get("public_client_env_sources", {}).get("allowed", []))
    exact = denied_names(policy)
    patterns = compile_patterns(policy)
    text = read_text(path)
    pending_public_assignments: list[tuple[int, str, str]] = []

    errors.extend(check_duplicate_yaml_keys(path))

    for lineno, line in enumerate(text.splitlines(), start=1):
        assignment_match = PUBLIC_ASSIGNMENT_RE.match(line)
        if assignment_match:
            pending_public_assignments.append((lineno, assignment_match.group(1), assignment_match.group(2)))

        if "create-public-client-env.sh" in line:
            for inline_assignment in PUBLIC_ASSIGNMENT_ANYWHERE_RE.finditer(line):
                pending_public_assignments.append((lineno, inline_assignment.group(1), inline_assignment.group(2)))
            for assignment_lineno, public_name, rhs in pending_public_assignments:
                if public_name not in allowed_public:
                    errors.append(
                        f"{path.relative_to(ROOT)}:{assignment_lineno}: {public_name} is not allowlisted public config"
                    )
                if "$(" in rhs or "`" in rhs:
                    errors.append(
                        f"{path.relative_to(ROOT)}:{assignment_lineno}: {public_name} uses command substitution"
                    )
                for printenv_match in PRINTENV_REF_RE.finditer(rhs):
                    ref_name = printenv_match.group(1)
                    if ref_name != public_name and ref_name not in allowed_public_sources:
                        errors.append(
                            f"{path.relative_to(ROOT)}:{assignment_lineno}: maps non-approved source {ref_name} into {public_name}"
                        )
                for ref_match in ENV_REF_RE.finditer(rhs):
                    ref_name = ref_match.group(1) or ref_match.group(2)
                    if not ref_name:
                        continue
                    if ref_name != public_name and ref_name not in allowed_public_sources:
                        errors.append(
                            f"{path.relative_to(ROOT)}:{assignment_lineno}: maps non-approved source {ref_name} into {public_name}"
                        )
                    if (
                        ref_name not in allowed_public
                        and ref_name not in allowed_public_sources
                        and name_is_denied(ref_name, exact, patterns)
                    ):
                        errors.append(
                            f"{path.relative_to(ROOT)}:{assignment_lineno}: maps server-only {ref_name} into {public_name}"
                        )
            pending_public_assignments.clear()
        elif line.strip() and not line.rstrip().endswith("\\") and not assignment_match:
            pending_public_assignments.clear()

        env_write = ENV_WRITE_RE.search(line) or ("tee" in line and PUBLIC_ENV_FILE_RE.search(line))
        if env_write or PUBLIC_ENV_FILE_RE.search(line):
            for token in variable_like_tokens(line):
                if token in allowed_public:
                    continue
                if name_is_denied(token, exact, patterns):
                    errors.append(f"{path.relative_to(ROOT)}:{lineno}: public env write references server-only {token}")
            for ref_match in ENV_REF_RE.finditer(line):
                ref_name = ref_match.group(1) or ref_match.group(2)
                if ref_name and ref_name not in allowed_public and name_is_denied(ref_name, exact, patterns):
                    errors.append(f"{path.relative_to(ROOT)}:{lineno}: public env write reads server-only {ref_name}")

        if "Set up App .env" in line:
            errors.append(
                f"{path.relative_to(ROOT)}:{lineno}: use Generate public client config, not hand-written App .env"
            )

    return errors


def line_env_refs(line: str) -> set[str]:
    refs: set[str] = set()
    for ref_match in ENV_REF_RE.finditer(line):
        ref_name = ref_match.group(1) or ref_match.group(2)
        if ref_name:
            refs.add(ref_name)
    for secret_match in GITHUB_SECRET_RE.finditer(line):
        refs.add(secret_match.group(1))
    return refs


def denied_refs_in_line(
    line: str,
    exact: set[str],
    patterns: list[re.Pattern[str]],
    allowed_public: set[str],
    allowed_secret_sources: set[str],
) -> set[str]:
    refs = set(line_env_refs(line))
    for assignment_match in SHELL_ASSIGNMENT_RE.finditer(line):
        refs.add(assignment_match.group(1))
    return {
        ref
        for ref in refs
        if ref not in allowed_public
        and ref not in allowed_secret_sources
        and not ref.endswith(("_NAME", "_PATH", "_FILE"))
        and name_is_denied(ref, exact, patterns)
    }


def release_hygiene_files() -> list[Path]:
    files: list[Path] = []
    for path in git_files():
        if not path.exists():
            continue
        rel = path.relative_to(ROOT)
        if rel == Path("codemagic.yaml"):
            files.append(path)
        elif path.match(".github/workflows/*.y*ml"):
            files.append(path)
        elif path.name == "release.sh" and (
            path.is_relative_to(ROOT / "app")
            or path.is_relative_to(ROOT / "mcp")
            or path.is_relative_to(ROOT / "plugins")
            or path.is_relative_to(ROOT / "sdks")
            or path.is_relative_to(ROOT / "web")
        ):
            files.append(path)
    return files


def logical_shell_line(lines: list[str], line_index: int) -> str:
    command_parts = [lines[line_index]]
    for next_line in lines[line_index + 1 : line_index + 8]:
        if not command_parts[-1].rstrip().endswith("\\"):
            break
        command_parts[-1] = command_parts[-1].rstrip()[:-1]
        command_parts.append(next_line)
    return " ".join(part.strip() for part in command_parts)


def redirects_stdout(line: str) -> bool:
    return bool(STDOUT_REDIRECT_RE.search(line))


def check_release_log_secret_hygiene(policy: dict) -> list[str]:
    errors: list[str] = []
    exact = denied_names(policy)
    patterns = compile_patterns(policy)
    allowed_public = allowed_public_names(policy)
    allowed_secret_sources = set(policy.get("allowed_build_secret_source_references", []))

    for path in release_hygiene_files():
        rel = path.relative_to(ROOT)
        lines = read_text(path).splitlines()
        for line_index, line in enumerate(lines):
            lineno = line_index + 1
            denied_refs = denied_refs_in_line(line, exact, patterns, allowed_public, allowed_secret_sources)
            if PUBLIC_ENV_TARGET_RE.search(line) and denied_refs:
                errors.append(
                    f"{rel}:{lineno}: public env file write references server-only {', '.join(sorted(denied_refs))}"
                )
            logical_line = logical_shell_line(lines, line_index)
            writes_to_stdout = not redirects_stdout(logical_line) and not SAFE_STDIN_SECRET_SINK_RE.search(logical_line)
            if SENSITIVE_ECHO_RE.search(line) and denied_refs and writes_to_stdout and "::add-mask::" not in line:
                errors.append(
                    f"{rel}:{lineno}: shell output command references server-only {', '.join(sorted(denied_refs))}"
                )
            if not SHELL_TRACE_RE.search(line):
                continue

            trace_refs: set[str] = set()
            for offset, traced_line in enumerate(lines[lineno:], start=lineno + 1):
                if SHELL_TRACE_OFF_RE.search(traced_line):
                    break
                if offset - lineno > 80:
                    break
                trace_refs.update(
                    denied_refs_in_line(traced_line, exact, patterns, allowed_public, allowed_secret_sources)
                )
            if trace_refs:
                errors.append(f"{rel}:{lineno}: set -x traces nearby server-only refs {', '.join(sorted(trace_refs))}")

    return errors


LEGACY_SETUP_ENV_RE = re.compile(
    r"(?:^|[\s/\"'>=:\\(])(?:\.env|\.dev\.env|\.prod\.env|\.env\.local|\.env\.production)(?=[\"'\s),;]|$)"
)
APPROVED_SETUP_ENV_RE = re.compile(r"(?:^|[\s/\"'>=:\\(])\.client(?:\.dev)?\.env(?=[\"'\s),;]|$)")
ENV_WRITE_COMMAND_RE = re.compile(
    r"\b(?:echo|printf|cat|cp|copy|copy-item|set-content|out-file|tee|writealltext)\b", re.IGNORECASE
)


def check_setup_env_writes() -> list[str]:
    errors: list[str] = []
    setup_paths = [
        ROOT / "app" / "setup.sh",
        ROOT / "app" / "initialsetup.bash",
        ROOT / "app" / "setup" / "scripts" / "setup.ps1",
        ROOT / "app" / "setup" / "scripts" / "initialsetup.ps1",
    ]
    for path in setup_paths:
        if not path.exists():
            continue
        rel = path.relative_to(ROOT)
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            if not ENV_WRITE_COMMAND_RE.search(line):
                continue
            if LEGACY_SETUP_ENV_RE.search(line):
                errors.append(f"{rel}:{lineno}: setup scripts must not write legacy public env files")
            if ".client" in line and not APPROVED_SETUP_ENV_RE.search(line):
                errors.append(f"{rel}:{lineno}: setup scripts may only write .client.env or .client.dev.env")
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
        for token in variable_like_tokens(text):
            if token not in allowed_names(policy) and name_is_denied(token, exact, compile_patterns(policy)):
                errors.append(f"{rel}: public app env template references server-only env-like token {token}")
    return errors


def check_docker_secret_baking(policy: dict) -> list[str]:
    errors: list[str] = []
    exact = denied_names(policy)
    patterns = compile_patterns(policy)
    allowed_public = allowed_public_names(policy)
    allowed_build_secret_source_refs = set(policy.get("allowed_build_secret_source_references", []))

    dockerfiles = [
        path
        for path in git_files()
        if path.exists()
        and (path.name == "Dockerfile" or path.name.startswith("Dockerfile."))
        and (
            path.is_relative_to(ROOT / "web")
            or path.is_relative_to(ROOT / "plugins")
            or path.is_relative_to(ROOT / "mcp")
            or path.is_relative_to(ROOT / "desktop")
        )
    ]
    for path in dockerfiles:
        text = read_text(path)
        rel = path.relative_to(ROOT)
        secret_args: set[str] = set()
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for token in variable_like_tokens(stripped):
                if token in allowed_public or token in allowed_build_secret_source_refs:
                    continue
                if name_is_denied(token, exact, patterns):
                    errors.append(f"{rel}:{lineno}: Dockerfile references server-only env-like token {token}")
            if (
                re.search(r"--(?:secret|ssh|build-context)(?:\s|=|$)", stripped)
                or "type=secret" in stripped
                or "type=ssh" in stripped
            ):
                errors.append(
                    f"{rel}:{lineno}: Docker build-time secret/context mount is not allowed in public client images"
                )
            arg_match = re.match(r"(?i)^ARG\s+([A-Z0-9_]+)(?:=.*)?$", stripped)
            if arg_match:
                name = arg_match.group(1)
                if name not in allowed_public:
                    errors.append(f"{rel}:{lineno}: build ARG {name} is not allowlisted as public client config")
                if name not in allowed_public and name_is_denied(name, exact, patterns):
                    secret_args.add(name)
                    errors.append(f"{rel}:{lineno}: server-only build ARG {name} can leak through image history")
            if re.match(r"(?i)^ENV\s+", stripped):
                for name in exact | secret_args:
                    if name in stripped and name not in allowed_public:
                        errors.append(f"{rel}:{lineno}: server-only {name} is promoted into final image ENV")

    workflow_files = [path for path in git_files() if path.exists() and path.match(".github/workflows/*.y*ml")]
    for path in workflow_files:
        text = read_text(path)
        rel = path.relative_to(ROOT)
        errors.extend(check_duplicate_yaml_keys(path))
        in_docker_build = False
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "docker build" in line or "docker/build-push-action" in line:
                in_docker_build = True
            if in_docker_build and re.search(r"--(?:secret|ssh|build-context)(?:\s|=|$)", line):
                errors.append(
                    f"{rel}:{lineno}: docker build secret/context flags are not allowed for public client builds"
                )
            if "--build-arg" not in line:
                if in_docker_build and not line.rstrip().endswith("\\"):
                    in_docker_build = False
                continue
            for name in exact:
                if name in line and name not in allowed_public:
                    errors.append(f"{rel}:{lineno}: server-only {name} is passed as docker build-arg")
            for match in re.finditer(r"--build-arg(?:=|\s+)([A-Z0-9_]+)(?:=(.*?))?(?=\s+-{1,2}[A-Za-z]|\s*\\?$)", line):
                name = match.group(1)
                rhs = match.group(2) or f"${name}"
                if name not in allowed_public:
                    errors.append(f"{rel}:{lineno}: build arg {name} is not allowlisted as public client config")
                if name not in allowed_public and name_is_denied(name, exact, patterns):
                    errors.append(f"{rel}:{lineno}: server-only {name} is passed as docker build-arg")
                for ref_match in ENV_REF_RE.finditer(rhs):
                    ref_name = ref_match.group(1) or ref_match.group(2)
                    if ref_name and ref_name not in allowed_public and name_is_denied(ref_name, exact, patterns):
                        errors.append(f"{rel}:{lineno}: build arg {name} reads server-only {ref_name}")
                for secret_match in GITHUB_SECRET_RE.finditer(rhs):
                    ref_name = secret_match.group(1)
                    if ref_name != name:
                        errors.append(f"{rel}:{lineno}: build arg {name} reads non-matching GitHub secret {ref_name}")
            if in_docker_build and not line.rstrip().endswith("\\"):
                in_docker_build = False

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", action="append", default=[], help="public client env file to validate")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="run the full legacy-baseline scan; default hook mode checks only clean policy/env-file contracts",
    )
    args = parser.parse_args()

    policy = load_policy()
    errors: list[str] = []

    env_files = [Path(raw).resolve() for raw in args.env_file]
    env_files.extend(
        [ROOT / "app" / ".client.env", ROOT / "app" / ".client.dev.env", ROOT / "app" / ".client.env.example"]
    )
    for path in env_files:
        errors.extend(check_env_file(path, policy))

    if args.strict:
        errors.extend(check_policy_shape(policy))
        errors.extend(check_app_source(policy))
        errors.extend(check_codemagic(policy))
        errors.extend(check_setup_env_writes())
        errors.extend(check_public_templates(policy))
        errors.extend(check_release_log_secret_hygiene(policy))
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
