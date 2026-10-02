#!/usr/bin/env python3
"""Collect and normalize GitHub evidence for a Codemagic mobile tag build.

The caller supplies a GitHub token with read-only Actions/check access. This
module performs the authenticated reads and emits the bounded input consumed by
``verify_mobile_release_admission.py``; the verifier itself stays hermetic.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

from verify_mobile_release_admission import (
    EXPECTED_REPOSITORY,
    MOBILE_CHECK_NAME,
    MOBILE_WORKFLOW_NAME,
    MOBILE_WORKFLOW_PATH,
    RELEASE_WORKFLOW_NAME,
    RELEASE_WORKFLOW_PATH,
    validate_admission,
)

API_ROOT = "https://api.github.com"
JsonGetter = Callable[[str], dict[str, Any]]
GITHUB_PAGE_SIZE = 100
MAX_PAGINATION_PAGES = 10
_MISSING = object()


class AdmissionCollectionError(RuntimeError):
    """GitHub did not provide complete, trusted admission evidence."""


def _one(items: object, *, label: str, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    if not isinstance(items, list):
        raise AdmissionCollectionError(f"{label} response is malformed")
    matches = [item for item in items if isinstance(item, dict) and predicate(item)]
    if len(matches) != 1:
        raise AdmissionCollectionError(f"expected one {label}, found {len(matches)}")
    return matches[0]


def _paginated_items(
    get: JsonGetter,
    path: str,
    *,
    key: str,
    label: str,
) -> list[dict[str, Any]]:
    """Read one bounded GitHub list endpoint without trusting page-one ordering.

    These endpoints return ``total_count`` in normal GitHub responses, but the
    existing hermetic getter intentionally exposes only JSON objects (not HTTP
    headers).  We therefore use that count when present and also follow a full
    page when a fixture or compatible endpoint omits it.  A short page without
    enough declared results, malformed data, a changing count, or a full page
    at the bound is an admission failure rather than an implicit success.
    """
    items: list[dict[str, Any]] = []
    declared_total: object = _MISSING

    for page_number in range(1, MAX_PAGINATION_PAGES + 1):
        page_path = path if page_number == 1 else f"{path}&page={page_number}"
        try:
            response = get(page_path)
        except AdmissionCollectionError:
            raise
        except Exception as error:
            raise AdmissionCollectionError(f"{label} page {page_number} read failed") from error
        if not isinstance(response, dict):
            raise AdmissionCollectionError(f"{label} page {page_number} response is malformed")

        page_items = response.get(key)
        if not isinstance(page_items, list) or not all(isinstance(item, dict) for item in page_items):
            raise AdmissionCollectionError(f"{label} page {page_number} response is malformed")

        page_total = response.get("total_count", _MISSING)
        if page_total is not _MISSING:
            if type(page_total) is not int or page_total < 0:
                raise AdmissionCollectionError(f"{label} page {page_number} total_count is malformed")
            if declared_total is _MISSING:
                declared_total = page_total
            elif page_total != declared_total:
                raise AdmissionCollectionError(f"{label} pagination total_count changed")

        items.extend(page_items)
        if declared_total is not _MISSING:
            if declared_total > GITHUB_PAGE_SIZE * MAX_PAGINATION_PAGES:
                raise AdmissionCollectionError(f"{label} pagination exceeds the bounded page limit")
            if len(items) > declared_total:
                raise AdmissionCollectionError(f"{label} pagination returned too many items")
            if len(items) == declared_total:
                return items
            if not page_items:
                raise AdmissionCollectionError(f"{label} pagination ended before total_count was collected")
            continue

        if len(page_items) < GITHUB_PAGE_SIZE:
            return items

    raise AdmissionCollectionError(f"{label} pagination exceeded the bounded page limit")


def collect_from_github(get: JsonGetter, *, repository: str, source_sha: str) -> dict[str, Any]:
    if repository != EXPECTED_REPOSITORY:
        raise AdmissionCollectionError(f"repository must be {EXPECTED_REPOSITORY}")

    main_ref = get(f"/repos/{repository}/git/ref/heads/main")
    current_main_sha = main_ref.get("object", {}).get("sha") if isinstance(main_ref.get("object"), dict) else None
    if not isinstance(current_main_sha, str):
        raise AdmissionCollectionError("main ref did not return a SHA")
    if current_main_sha == source_sha:
        is_ancestor = True
    else:
        compare = get(f"/repos/{repository}/compare/{source_sha}...{current_main_sha}")
        is_ancestor = compare.get("status") == "ahead"
    if not is_ancestor:
        raise AdmissionCollectionError("source SHA is not an ancestor of current main")

    release_runs_path = (
        f"/repos/{repository}/actions/runs?head_sha={urllib.parse.quote(source_sha)}"
        "&event=push&branch=main&per_page=100"
    )
    release_runs = _paginated_items(
        get, release_runs_path, key="workflow_runs", label="Release Eligibility runs"
    )
    release = _one(
        release_runs,
        label="Release Eligibility run",
        predicate=lambda run: run.get("name") == RELEASE_WORKFLOW_NAME
        and run.get("path") == RELEASE_WORKFLOW_PATH
        and run.get("event") == "push"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("run_attempt") == 1
        and run.get("head_branch") == "main"
        and run.get("head_sha") == source_sha
        and run.get("repository", {}).get("full_name") == repository,
    )

    check_runs = _paginated_items(
        get,
        f"/repos/{repository}/commits/{source_sha}/check-runs?per_page=100",
        key="check_runs",
        label="commit check runs",
    )
    aggregate = _one(
        check_runs,
        label="Mobile Release Eligibility check",
        predicate=lambda check: check.get("name") == MOBILE_CHECK_NAME
        and check.get("status") == "completed"
        and check.get("conclusion") == "success"
        and check.get("head_sha") == source_sha
        and isinstance(check.get("details_url"), str)
        and re.search(r"/actions/runs/[0-9]+(?:/|$)", check["details_url"]) is not None,
    )
    expected_prefix = f"https://github.com/{repository}/actions/runs/"
    if not aggregate["details_url"].startswith(expected_prefix):
        raise AdmissionCollectionError("mobile aggregate check URL is not the canonical repository URL")
    run_id_match = re.search(r"/actions/runs/([0-9]+)/job/([0-9]+)(?:/|$)", aggregate["details_url"])
    if run_id_match is None:
        raise AdmissionCollectionError("mobile aggregate check is not linked to an Actions run")
    mobile_run = get(f"/repos/{repository}/actions/runs/{run_id_match.group(1)}")
    if not (
        mobile_run.get("name") == MOBILE_WORKFLOW_NAME
        and mobile_run.get("path") == MOBILE_WORKFLOW_PATH
        and mobile_run.get("event") == "push"
        and mobile_run.get("status") == "completed"
        and mobile_run.get("conclusion") == "success"
        and mobile_run.get("run_attempt") == 1
        and mobile_run.get("head_branch") == "main"
        and mobile_run.get("head_sha") == source_sha
        and mobile_run.get("repository", {}).get("full_name") == repository
    ):
        raise AdmissionCollectionError("mobile aggregate is not a first-attempt successful push run for the source")
    jobs = _paginated_items(
        get,
        f"/repos/{repository}/actions/runs/{run_id_match.group(1)}/jobs?per_page=100",
        key="jobs",
        label="Mobile Release Eligibility jobs",
    )
    _one(
        jobs,
        label="Mobile Release Eligibility job",
        predicate=lambda job: str(job.get("id")) == run_id_match.group(2)
        and job.get("name") == MOBILE_CHECK_NAME
        and job.get("status") == "completed"
        and job.get("conclusion") == "success",
    )
    proof = {
        "schema_version": 1,
        "repository": repository,
        "source_sha": source_sha,
        "current_main": {
            "branch": "main",
            "sha": current_main_sha,
            "source_sha_is_ancestor_of_current_main": True,
        },
        "release_eligibility": {
            "workflow_name": release["name"],
            "workflow_path": release["path"],
            "event": release["event"],
            "status": release["status"],
            "conclusion": release["conclusion"],
            "run_attempt": release["run_attempt"],
            "head_branch": release["head_branch"],
            "head_sha": release["head_sha"],
            "repository": repository,
        },
        "mobile_aggregate": {
            "check_name": aggregate["name"],
            "workflow_name": mobile_run["name"],
            "workflow_path": mobile_run["path"],
            "event": mobile_run["event"],
            "status": aggregate["status"],
            "conclusion": aggregate["conclusion"],
            "run_attempt": mobile_run["run_attempt"],
            "head_branch": mobile_run["head_branch"],
            "head_sha": mobile_run["head_sha"],
            "repository": repository,
        },
    }
    validate_admission(proof, sha=source_sha, repository=repository)
    return proof


def github_getter(token: str) -> JsonGetter:
    if not token:
        raise AdmissionCollectionError("a read-only GitHub token is required")

    def get(path: str) -> dict[str, Any]:
        request = urllib.request.Request(
            API_ROOT + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise AdmissionCollectionError(f"GitHub admission read failed: {error}") from error
        if not isinstance(value, dict):
            raise AdmissionCollectionError("GitHub admission response is not an object")
        return value

    return get


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=EXPECTED_REPOSITORY)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        proof = collect_from_github(github_getter(args.token), repository=args.repository, source_sha=args.sha)
        args.output.write_text(json.dumps(proof, sort_keys=True), encoding="utf-8")
    except (AdmissionCollectionError, OSError) as error:
        print(f"mobile release admission collection failed: {error}", file=sys.stderr)
        return 1
    print(f"mobile release admission proof written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
