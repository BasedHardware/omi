#!/usr/bin/env python3
"""Check or reconcile Cloud Scheduler jobs declared in deploy/scheduler/jobs.yaml.

The script never deletes Scheduler jobs. Check output is deliberately redacted:
secret header values and request bodies are never displayed.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "deploy" / "scheduler" / "jobs.yaml"
SCHEDULER_API = "https://cloudscheduler.googleapis.com/v1"
SECRET_API = "https://secretmanager.googleapis.com/v1"
UPDATE_MASK = "schedule,timeZone,httpTarget,retryConfig,attemptDeadline"
SERVER_HEADERS = {"user-agent"}


class ReconcileError(RuntimeError):
    pass


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def load_manifest(path: Path = MANIFEST) -> Mapping[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping) or data.get("version") != 1:
        raise ReconcileError("scheduler manifest must be a version 1 mapping")
    environments = _mapping(data.get("environments"))
    for env, config in environments.items():
        if not isinstance(env, str) or not isinstance(_mapping(config).get("project"), str):
            raise ReconcileError("each environment must declare a project")
        jobs = _mapping(config).get("jobs")
        if not isinstance(jobs, list):
            raise ReconcileError(f"{env}: jobs must be a list")
        names: set[str] = set()
        for job in jobs:
            if not isinstance(job, Mapping) or not isinstance(job.get("name"), str):
                raise ReconcileError(f"{env}: each job must have a name")
            if job["name"] in names:
                raise ReconcileError(f"{env}: duplicate job {job['name']}")
            names.add(job["name"])
            if job.get("state") not in {"ENABLED", "PAUSED"}:
                raise ReconcileError(f"{env}/{job['name']}: state must be ENABLED or PAUSED")
            lifecycle = job.get("lifecycle")
            if lifecycle is not None and lifecycle != "planned":
                raise ReconcileError(f"{env}/{job['name']}: lifecycle must be planned when specified")
            if not all(job.get(field) for field in ("region", "schedule", "time_zone", "attempt_deadline")):
                raise ReconcileError(f"{env}/{job['name']}: missing schedule fields")
            target = _mapping(job.get("target"))
            if (
                target.get("type") != "http"
                or not target.get("uri")
                or target.get("method") not in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            ):
                raise ReconcileError(f"{env}/{job['name']}: unsupported or incomplete HTTP target")
            auth = [key for key in ("oidc", "oauth") if key in target]
            if len(auth) > 1:
                raise ReconcileError(f"{env}/{job['name']}: choose only one auth token type")
            for key, value in _mapping(target.get("headers")).items():
                if not isinstance(value, Mapping) or set(value) != {"secret", "version"}:
                    raise ReconcileError(f"{env}/{job['name']}: header {key} must use a Secret Manager reference")
    return data


def _job_resource(project: str, job: Mapping[str, Any]) -> str:
    return f"projects/{project}/locations/{job['region']}/jobs/{job['name']}"


def _secret_value(session: Any, project: str, reference: Mapping[str, Any]) -> str:
    secret = quote(str(reference["secret"]), safe="-_.")
    version = quote(str(reference["version"]), safe="-_.")
    resource = f"projects/{project}/secrets/{secret}/versions/{version}:access"
    response = session.get(f"{SECRET_API}/{resource}")
    response.raise_for_status()
    try:
        value = base64.b64decode(response.json()["payload"]["data"], validate=True).decode("utf-8")
    except (KeyError, ValueError, UnicodeError) as exc:
        raise ReconcileError(f"Secret Manager reference {secret}:{version} is unavailable or not UTF-8") from exc
    if not value:
        raise ReconcileError(f"Secret Manager reference {secret}:{version} is empty")
    return value


def desired_resource(session: Any, project: str, job: Mapping[str, Any]) -> dict[str, Any]:
    target = _mapping(job["target"])
    http: dict[str, Any] = {"uri": target["uri"], "httpMethod": target["method"]}
    headers: dict[str, str] = {}
    for key, value in _mapping(target.get("headers")).items():
        if "secret" in value:
            headers[key] = _secret_value(session, project, value)
        else:
            headers[key] = str(value)
    if headers:
        http["headers"] = headers
    for auth_type in ("oidc", "oauth"):
        if auth_type in target:
            auth = _mapping(target[auth_type])
            token_key = "oidcToken" if auth_type == "oidc" else "oauthToken"
            token: dict[str, str] = {"serviceAccountEmail": str(auth["service_account"])}
            token_field = "audience" if auth_type == "oidc" else "scope"
            token_value = auth.get(token_field)
            if token_value:
                token[token_field] = str(token_value)
            http[token_key] = token
    retry = _mapping(job.get("retry"))
    resource: dict[str, Any] = {
        "schedule": job["schedule"],
        "timeZone": job["time_zone"],
        "httpTarget": http,
        "attemptDeadline": job["attempt_deadline"],
    }
    if retry:
        resource["retryConfig"] = {
            "maxBackoffDuration": retry["max_backoff"],
            "maxDoublings": int(retry["max_doublings"]),
            "maxRetryDuration": retry["max_retry"],
            "minBackoffDuration": retry["min_backoff"],
        }
    return resource


def _normalized_http(value: Any) -> dict[str, Any]:
    current = dict(_mapping(value))
    headers = {
        str(key): val for key, val in _mapping(current.get("headers")).items() if str(key).lower() not in SERVER_HEADERS
    }
    current["headers"] = headers
    return current


def diff_fields(current: Mapping[str, Any] | None, desired: Mapping[str, Any]) -> list[str]:
    if current is None:
        return ["missing"]
    changed: list[str] = []
    for field in ("schedule", "timeZone", "attemptDeadline", "retryConfig"):
        if current.get(field) != desired.get(field):
            changed.append(field)
    have_http = _normalized_http(current.get("httpTarget"))
    want_http = _normalized_http(desired.get("httpTarget"))
    for field in sorted(set(have_http) | set(want_http)):
        if have_http.get(field) != want_http.get(field):
            # Never include either side of a header comparison in diagnostics.
            changed.append("httpTarget.headers" if field == "headers" else f"httpTarget.{field}")
    return changed


def _request(session: Any, method: str, url: str, **kwargs: Any) -> Any:
    response = getattr(session, method)(url, **kwargs)
    response.raise_for_status()
    return response


def _get_job(session: Any, resource_name: str) -> Mapping[str, Any] | None:
    response = session.get(f"{SCHEDULER_API}/{resource_name}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _all_jobs(session: Any, project: str) -> list[Mapping[str, Any]]:
    locations_response = _request(session, "get", f"{SCHEDULER_API}/projects/{project}/locations")
    locations = locations_response.json().get("locations", [])
    jobs: list[Mapping[str, Any]] = []
    for location in locations:
        region = str(location.get("locationId") or str(location.get("name", "")).rsplit("/", 1)[-1])
        page_token = ""
        while True:
            params = {"pageSize": 500}
            if page_token:
                params["pageToken"] = page_token
            response = _request(
                session,
                "get",
                f"{SCHEDULER_API}/projects/{project}/locations/{region}/jobs",
                params=params,
            )
            page = response.json()
            jobs.extend(page.get("jobs", []))
            page_token = page.get("nextPageToken", "")
            if not page_token:
                break
    return jobs


def _pause_state(session: Any, resource_name: str, desired_state: str, current_state: str | None) -> None:
    if current_state == desired_state:
        return
    action = "pause" if desired_state == "PAUSED" else "resume"
    _request(session, "post", f"{SCHEDULER_API}/{resource_name}:{action}")


def reconcile(
    session: Any,
    manifest: Mapping[str, Any],
    environment: str,
    project_override: str,
    *,
    apply: bool,
    selected_jobs: set[str] | None = None,
    include_unlisted: bool = True,
) -> tuple[list[str], list[str]]:
    environments = _mapping(manifest.get("environments"))
    config = _mapping(environments.get(environment))
    if not config:
        raise ReconcileError(f"environment {environment!r} is not declared")
    project = config.get("project")
    if project_override != project:
        raise ReconcileError(f"project mismatch: manifest requires {project}; received {project_override}")
    jobs = [job for job in config["jobs"] if selected_jobs is None or job["name"] in selected_jobs]
    selected_names = {job["name"] for job in jobs}
    if selected_jobs is not None and selected_names != selected_jobs:
        missing = sorted(selected_jobs - selected_names)
        raise ReconcileError(f"jobs are not declared for {environment}: {', '.join(missing)}")

    differences: list[str] = []
    messages: list[str] = []
    for job in jobs:
        resource_name = _job_resource(project, job)
        if apply and job.get("lifecycle") == "planned" and selected_jobs is None:
            messages.append(f"PLANNED {resource_name}: skipped; select it explicitly with --jobs to deploy")
            continue
        current = _get_job(session, resource_name)
        if not apply and current is None and job.get("lifecycle") == "planned":
            messages.append(f"PLANNED {resource_name}: not deployed")
            continue
        desired = desired_resource(session, project, job)
        fields = diff_fields(current, desired)
        live_state = current.get("state") if current else None
        if live_state != job["state"]:
            fields.append("state")
        if not fields:
            messages.append(f"MATCH {resource_name}")
            continue
        differences.append(resource_name)
        messages.append(f"DIFF {resource_name}: {', '.join(fields)}")
        if not apply:
            continue
        if current is None:
            parent = f"projects/{project}/locations/{job['region']}"
            _request(
                session,
                "post",
                f"{SCHEDULER_API}/{parent}/jobs",
                params={"jobId": job["name"]},
                json=desired,
            )
            if job["state"] == "PAUSED":
                _pause_state(session, resource_name, "PAUSED", "ENABLED")
        else:
            _request(
                session,
                "patch",
                f"{SCHEDULER_API}/{resource_name}",
                params={"updateMask": UPDATE_MASK},
                json=desired,
            )
            _pause_state(session, resource_name, job["state"], live_state)
        messages[-1] = f"APPLIED {resource_name}: {', '.join(fields)}"

    if include_unlisted:
        listed_resources = {_job_resource(project, job) for job in config["jobs"]}
        for current in _all_jobs(session, project):
            resource_name = str(current.get("name", ""))
            name = resource_name.rsplit("/", 1)[-1]
            region = resource_name.split("/locations/")[-1].split("/", 1)[0]
            if resource_name not in listed_resources:
                messages.append(f"UNLISTED {resource_name}: retained; no delete performed")
                if not apply:
                    differences.append(f"unlisted:{region}/{name}")
    return differences, messages


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("dev", "prod"), required=True)
    parser.add_argument("--project", required=True, help="Required explicit GCP project; checked against the manifest")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only diff; exits nonzero on drift")
    mode.add_argument("--apply", action="store_true", help="Create or update listed jobs; never deletes")
    parser.add_argument("--jobs", nargs="+", help="Limit reconciliation to these declared job names")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        from google.auth import default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(credentials)
        manifest = load_manifest(args.manifest)
        differences, messages = reconcile(
            session,
            manifest,
            args.environment,
            args.project,
            apply=args.apply,
            selected_jobs=set(args.jobs) if args.jobs else None,
            include_unlisted=not args.jobs,
        )
        for message in messages:
            print(message)
        if args.check:
            print(
                "scheduler check: ZERO DIFF"
                if not differences
                else f"scheduler check: {len(differences)} difference(s)"
            )
            return 0 if not differences else 1
        print(f"scheduler reconcile: applied {len(differences)} change(s); unlisted jobs retained")
        return 0
    except Exception as exc:
        # HTTP exceptions may contain request URLs but not response payloads. Avoid
        # echoing arbitrary exception text because a provider can include headers.
        if isinstance(exc, ReconcileError):
            message = str(exc)
        else:
            message = f"{type(exc).__name__}; inspect redacted runner diagnostics"
        print(f"scheduler reconcile: ERROR: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
