#!/usr/bin/env python3
"""Create a credential-safe, agent-readable recovery capsule for a failed desktop release."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

APP_ID = "66c95e6ec76853c447b8bcbb"
WORKFLOW_ID = "omi-desktop-swift-release"
CHECK_NAME = "Release OMI Desktop (Swift)"
BUILD_ID_RE = re.compile(r"^[0-9a-f]{24}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
DETAILS_RE = re.compile(
    rf"^https://codemagic\.io/app/{APP_ID}/build/(?P<build_id>[0-9a-f]{{24}})(?:[?#].*)?$"
)
LOG_RE = re.compile(
    r"^https://api\.codemagic\.io/builds/(?P<build_id>[0-9a-f]{24})/"
    r"(?:step/[0-9a-f]{24}|logs/[0-9]+)$"
)
LOG_TAIL_LINES = 200
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
DIAGNOSTIC_RE = re.compile(r"^(?:FAIL|ERROR|WARN):\s+.{1,600}$")
AUTHORIZATION_RE = re.compile(r"(?i)(\bauthorization\b\s*[:=]\s*)(?:bearer\s+)?\S+")
CREDENTIAL_HEADER_RE = re.compile(r"(?i)(\b(?:cookie|set-cookie)\b\s*:\s*).*$")
ENV_ASSIGNMENT_RE = re.compile(
    r"((?<![?&])\b[A-Z][A-Z0-9_]{1,127}\s*=\s*)(?:\"[^\"]*\"|'[^']*'|\S+)"
)
CREDENTIAL_RE = re.compile(
    r"(?i)((?<![?&])\b(?:"
    r"x-auth-token|api[\s_-]?key|client[\s_-]?secret|"
    r"(?:[a-z0-9]+_)*(?:key|token|secret|password)"
    r")\b\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|\S+)"
)
BEARER_RE = re.compile(r"(?i)(\bbearer\s+)\S+")
URL_CREDENTIAL_RE = re.compile(
    r"(?i)([?&#](?:access_token|refresh_token|id_token|api_key|key|signature|x-goog-signature)=)[^&#\s]+"
)
QUERY_ASSIGNMENT_RE = re.compile(
    r"(?i)([?&#](?:[A-Za-z0-9_.%-]*(?:token|key|secret|sign|auth|credential|password|pass|code)[A-Za-z0-9_.%-]*)=)[^&#\s]+"
)
GITHUB_TOKEN_RE = re.compile(r"\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


class RecoveryError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def request_bytes(
    url: str,
    *,
    token: str,
    opener: Callable[..., Any] | None = None,
) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json, text/plain", "x-auth-token": token},
        method="GET",
    )
    if opener is None:
        opener = urllib.request.build_opener(NoRedirect()).open
    try:
        with opener(request, timeout=30) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise RecoveryError("Codemagic API response exceeded the safe size limit")
            return body
    except urllib.error.HTTPError as error:
        raise RecoveryError(f"Codemagic API returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RecoveryError(f"Codemagic API unavailable: {type(error).__name__}") from error


def request_json(url: str, *, token: str, opener: Callable[..., Any] | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(request_bytes(url, token=token, opener=opener).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecoveryError("Codemagic API returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise RecoveryError("Codemagic API returned an unexpected payload")
    return payload


def build_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    build = payload.get("build", payload)
    if not isinstance(build, dict):
        raise RecoveryError("Codemagic build payload is missing build metadata")
    return build


def commit_sha(build: dict[str, Any]) -> str:
    commit = build.get("commit")
    if isinstance(commit, str):
        return commit
    if isinstance(commit, dict):
        for key in ("hash", "sha", "id"):
            value = commit.get(key)
            if isinstance(value, str):
                return value
    return ""


def first_string(build: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = build.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def flattened_actions(build: dict[str, Any]) -> list[dict[str, Any]]:
    actions = build.get("buildActions")
    if not isinstance(actions, list):
        return []
    result: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        subactions = action.get("subactions")
        if isinstance(subactions, list) and subactions:
            for item in subactions:
                if not isinstance(item, dict):
                    continue
                inherited = dict(item)
                for key in ("name", "status", "logUrl"):
                    if not isinstance(inherited.get(key), str) and isinstance(action.get(key), str):
                        inherited[key] = action[key]
                result.append(inherited)
        else:
            result.append(action)
    return result


def failed_action(build: dict[str, Any]) -> dict[str, Any]:
    failed = [action for action in flattened_actions(build) if action.get("status") == "failed"]
    if len(failed) != 1:
        raise RecoveryError(f"expected exactly one failed Codemagic step, found {len(failed)}")
    return failed[0]


def sanitize_line(line: str) -> str:
    line = CREDENTIAL_HEADER_RE.sub(lambda match: f"{match.group(1)}<redacted>", line)
    line = AUTHORIZATION_RE.sub(lambda match: f"{match.group(1)}<redacted>", line)
    line = ENV_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}<redacted>", line)
    line = CREDENTIAL_RE.sub(lambda match: f"{match.group(1)}<redacted>", line)
    line = BEARER_RE.sub(lambda match: f"{match.group(1)}<redacted>", line)
    line = URL_CREDENTIAL_RE.sub(lambda match: f"{match.group(1)}<redacted>", line)
    line = QUERY_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}<redacted>", line)
    line = GITHUB_TOKEN_RE.sub("<redacted>", line)
    line = JWT_RE.sub("<redacted>", line)
    return line


def sanitize_diagnostics(log: bytes) -> list[str]:
    text = log.decode("utf-8", errors="replace")
    diagnostics: list[str] = []
    for raw_line in text.splitlines():
        line = ANSI_RE.sub("", raw_line).strip()
        if not DIAGNOSTIC_RE.fullmatch(line):
            continue
        diagnostics.append(sanitize_line(line)[:600])
        if len(diagnostics) == 20:
            break
    return diagnostics


def sanitize_log_tail(log: bytes, *, max_lines: int = LOG_TAIL_LINES) -> list[str]:
    text = log.decode("utf-8", errors="replace")
    tail = text.splitlines()[-max_lines:]
    sanitized: list[str] = []
    for raw_line in tail:
        line = sanitize_line(ANSI_RE.sub("", raw_line))
        sanitized.append(line[:2000])
    return sanitized


def load_profiles(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "desktop-codemagic-recovery-profiles/v1":
        raise RecoveryError("unsupported recovery profile schema")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        raise RecoveryError("recovery profiles must be an object")
    return {key: value for key, value in profiles.items() if isinstance(key, str) and isinstance(value, dict)}


def event_build_id(event: dict[str, Any]) -> str:
    check = event.get("check_run")
    if not isinstance(check, dict):
        raise RecoveryError("check_run event is missing")
    app = check.get("app")
    app_slug = app.get("slug") if isinstance(app, dict) else None
    repository = event.get("repository")
    repository_name = repository.get("full_name") if isinstance(repository, dict) else None
    if (
        check.get("status") != "completed"
        or check.get("name") != CHECK_NAME
        or check.get("conclusion") != "failure"
        or app_slug != "codemagic-ci-cd"
        or repository_name != "BasedHardware/omi"
    ):
        raise RecoveryError("event is not a failed canonical desktop Codemagic check")
    details_url = check.get("details_url")
    match = DETAILS_RE.fullmatch(details_url if isinstance(details_url, str) else "")
    if match is None:
        raise RecoveryError("check_run details URL is not the canonical Codemagic desktop app")
    return match.group("build_id")


def event_source_sha(event: dict[str, Any]) -> str:
    check = event.get("check_run")
    sha = check.get("head_sha") if isinstance(check, dict) else None
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise RecoveryError("check_run event has an invalid source SHA")
    return sha


def build_capsule(
    *,
    build_id: str,
    token: str,
    profiles: dict[str, dict[str, Any]],
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if not BUILD_ID_RE.fullmatch(build_id):
        raise RecoveryError("build id must be 24 lowercase hexadecimal characters")
    payload = request_json(f"https://api.codemagic.io/builds/{build_id}", token=token, opener=opener)
    build = build_from_payload(payload)
    observed_id = first_string(build, "_id", "id", "buildId")
    workflow_id = first_string(build, "fileWorkflowId", "workflowId", "workflow_id")
    tag = build.get("tag")
    sha = commit_sha(build)
    if observed_id != build_id or build.get("appId") != APP_ID or workflow_id != WORKFLOW_ID:
        raise RecoveryError("Codemagic build identity does not match the canonical desktop release workflow")
    if not isinstance(tag, str) or not TAG_RE.fullmatch(tag):
        raise RecoveryError("Codemagic build has an invalid release tag")
    if not SHA_RE.fullmatch(sha):
        raise RecoveryError("Codemagic build has an invalid source SHA")
    if build.get("status") != "failed":
        raise RecoveryError(f"Codemagic build is not failed: {build.get('status')}")

    action = failed_action(build)
    step_name = action.get("name") if isinstance(action.get("name"), str) else ""
    log_url = action.get("logUrl") if isinstance(action.get("logUrl"), str) else ""
    match = LOG_RE.fullmatch(log_url)
    if match is None or match.group("build_id") != build_id:
        raise RecoveryError("failed-step log URL is missing or unsafe")
    log_bytes = request_bytes(log_url, token=token, opener=opener)
    diagnostics = sanitize_diagnostics(log_bytes)
    log_tail = sanitize_log_tail(log_bytes)

    profile = profiles.get(step_name, {})
    failure_profile = profile.get("failure_profile", "unclassified")
    if not isinstance(failure_profile, str) or not failure_profile:
        failure_profile = "unclassified"
    if failure_profile == "unclassified":
        print("::warning::failure_profile unclassified", flush=True)
    locally_reproducible = profile.get("locally_reproducible") is True
    arguments = profile.get("rehearsal_arguments") if locally_reproducible else []
    if not isinstance(arguments, list) or not all(isinstance(value, str) for value in arguments):
        raise RecoveryError("recovery profile rehearsal arguments must be strings")
    command = None
    if locally_reproducible:
        rendered = " ".join(["desktop/macos/scripts/rehearse-desktop-release.sh", "--codemagic-build-id", build_id, *arguments])
        command = rendered

    return {
        "schema": "desktop-codemagic-failure-recovery/v1",
        "build_id": build_id,
        "release_tag": tag,
        "source_sha": sha,
        "failed_step": step_name,
        "failure_profile": failure_profile,
        "locally_reproducible": locally_reproducible,
        "rehearsal_command": command,
        "diagnostics": diagnostics,
        "log_tail": log_tail,
        "codemagic_url": f"https://codemagic.io/app/{APP_ID}/build/{build_id}",
    }


def markdown_summary(capsule: dict[str, Any]) -> str:
    lines = [
        "## Desktop Release Recovery Required",
        "",
        f"- Candidate: `{capsule['release_tag']}`",
        f"- Source: `{capsule['source_sha']}`",
        f"- Codemagic build: [`{capsule['build_id']}`]({capsule['codemagic_url']})",
        f"- Failed step: `{capsule['failed_step']}`",
        f"- Failure profile: `{capsule['failure_profile']}`",
    ]
    diagnostics = capsule.get("diagnostics") or []
    if diagnostics:
        lines.extend(["", "### Credential-safe diagnostics", ""])
        lines.extend(f"- `{line}`" for line in diagnostics)
    log_tail = capsule.get("log_tail") or []
    if log_tail:
        lines.extend(["", "### Failed-step log tail (last 200 lines)", "", "```"])
        lines.extend(str(line).replace("```", "'''") for line in log_tail)
        lines.append("```")
    command = capsule.get("rehearsal_command")
    if isinstance(command, str):
        lines.extend(
            [
                "",
                "### Manual clean rehearsal",
                "",
                "Do not cut another candidate until this command passes or the failure is proven provider-only.",
                "",
                "```bash",
                '. "$HOME/.config/omi/codemagic-env.sh"',
                command,
                "```",
            ]
        )
    else:
        lines.extend(["", "This failure is classified as provider-only; do not run the local clean rehearsal automatically."])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event")
    parser.add_argument("--build-id")
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get("CODEMAGIC_API_TOKEN", "")
    if not token:
        raise RecoveryError("CODEMAGIC_API_TOKEN is required")
    build_id = args.build_id or ""
    expected_source_sha = ""
    if args.event:
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
        build_id = event_build_id(event)
        expected_source_sha = event_source_sha(event)
    capsule = build_capsule(build_id=build_id, token=token, profiles=load_profiles(args.profiles))
    if expected_source_sha and capsule["source_sha"] != expected_source_sha:
        raise RecoveryError("Codemagic build source does not match the triggering check run")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(capsule, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.write_text(markdown_summary(capsule), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RecoveryError, OSError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=os.sys.stderr)
        raise SystemExit(1)
