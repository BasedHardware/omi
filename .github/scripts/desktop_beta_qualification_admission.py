#!/usr/bin/env python3
"""Fail-closed admission for an exact desktop Beta qualification candidate.

The dispatcher is allowed to request qualification more than once: this check
is the authority that rejects a duplicate only after GitHub has serialized the
workflow and returned the complete exact-candidate run set.  It deliberately
allows a new bounded attempt after an older failed/cancelled run, but never
after an active or successful exact-candidate run.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


QUALIFICATION_WORKFLOW = ".github/workflows/desktop_qualify_beta.yml"
TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_EXACT_CANDIDATE_ATTEMPTS = 3


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _positive_id(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase 40-character commit SHA")
    return value


def candidate_sha(ref: Any, release_tag: str, annotated_tag: Any | None) -> str:
    """Resolve a lightweight or one-level annotated tag from GitHub API JSON."""
    if not TAG_RE.fullmatch(release_tag):
        raise ValueError("release tag is not an exact macOS candidate tag")
    if not isinstance(ref, dict) or ref.get("ref") != f"refs/tags/{release_tag}":
        raise ValueError("GitHub tag ref is malformed or does not bind the requested tag")
    target = ref.get("object")
    if not isinstance(target, dict):
        raise ValueError("GitHub tag ref is missing its object")
    kind = target.get("type")
    object_sha = _sha(target.get("sha"), "GitHub tag ref object SHA")
    if kind == "commit":
        return object_sha
    if kind != "tag":
        raise ValueError("GitHub tag ref must point to a commit or annotated tag")
    if not isinstance(annotated_tag, dict) or annotated_tag.get("sha") != object_sha:
        raise ValueError("annotated GitHub tag response does not bind the requested tag object")
    nested = annotated_tag.get("object")
    if not isinstance(nested, dict) or nested.get("type") != "commit":
        raise ValueError("annotated GitHub tag must peel directly to a commit")
    return _sha(nested.get("sha"), "annotated GitHub tag commit SHA")


def _workflow_runs(runs_response: Any) -> list[dict[str, Any]]:
    """Normalize every `gh api --paginate --slurp` page, or fail closed.

    The API includes a total_count on every page. Requiring the concatenated
    page length to match it rejects a partial page set, including an accidental
    regression back to the first 100 records only.
    """
    pages = [runs_response] if isinstance(runs_response, dict) else runs_response
    if not isinstance(pages, list) or not pages:
        raise ValueError("GitHub workflow-runs response is malformed")
    total_count: int | None = None
    all_runs: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict) or not isinstance(page.get("workflow_runs"), list):
            raise ValueError(f"GitHub workflow-runs page {page_index} is malformed")
        page_total = page.get("total_count")
        if not isinstance(page_total, int) or isinstance(page_total, bool) or page_total < 0:
            raise ValueError(f"GitHub workflow-runs page {page_index} total_count is malformed")
        if total_count is None:
            total_count = page_total
        elif page_total != total_count:
            raise ValueError("GitHub workflow-runs pagination total_count changed during retrieval")
        for run_index, run in enumerate(page["workflow_runs"]):
            absolute_index = len(all_runs)
            if not isinstance(run, dict):
                raise ValueError(f"GitHub workflow-runs response contains non-object entry {absolute_index}")
            run_id = _positive_id(run.get("id"), f"workflow run {absolute_index} id")
            if run_id in seen_ids:
                raise ValueError(f"GitHub workflow-runs response contains duplicate run id {run_id}")
            seen_ids.add(run_id)
            all_runs.append(run)
    if total_count != len(all_runs):
        raise ValueError("GitHub workflow-runs pagination is incomplete")
    return all_runs


def _exact_runs(runs_response: Any, release_tag: str, source_sha: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for index, run in enumerate(_workflow_runs(runs_response)):
        if not isinstance(run, dict):
            raise ValueError(f"GitHub workflow-runs response contains non-object entry {index}")
        # These are core fields on every actions workflow-run response. Reject
        # malformed data instead of treating it as evidence that no run exists.
        _positive_id(run.get("id"), f"workflow run {index} id")
        for field in ("path", "event", "head_branch", "head_sha", "status"):
            if not isinstance(run.get(field), str):
                raise ValueError(f"workflow run {index} {field} is malformed")
        conclusion = run.get("conclusion")
        if conclusion is not None and not isinstance(conclusion, str):
            raise ValueError(f"workflow run {index} conclusion is malformed")
        if (
            run["path"] == QUALIFICATION_WORKFLOW
            and run["event"] == "workflow_dispatch"
            and run["head_branch"] == release_tag
            and run["head_sha"] == source_sha
        ):
            selected.append(run)
    return selected


def decide(
    ref: Any,
    runs_response: Any,
    *,
    release_tag: str,
    current_run_id: int | None = None,
    annotated_tag: Any | None = None,
) -> dict[str, Any]:
    """Return an admission decision or raise for malformed GitHub API data."""
    source_sha = candidate_sha(ref, release_tag, annotated_tag)
    if current_run_id is not None:
        current_run_id = _positive_id(current_run_id, "current workflow run id")
    prior_runs = [run for run in _exact_runs(runs_response, release_tag, source_sha) if run["id"] != current_run_id]
    active = next((run for run in prior_runs if run["status"] != "completed"), None)
    if active is not None:
        return {
            "admitted": False,
            "release_tag": release_tag,
            "source_sha": source_sha,
            "reason": f"exact candidate already has active qualification run {active['id']}",
        }
    successful = next((run for run in prior_runs if run["conclusion"] == "success"), None)
    if successful is not None:
        return {
            "admitted": False,
            "release_tag": release_tag,
            "source_sha": source_sha,
            "reason": f"exact candidate already succeeded in qualification run {successful['id']}",
        }
    if len(prior_runs) >= MAX_EXACT_CANDIDATE_ATTEMPTS:
        return {
            "admitted": False,
            "release_tag": release_tag,
            "source_sha": source_sha,
            "reason": (
                f"exact candidate has reached the {MAX_EXACT_CANDIDATE_ATTEMPTS}-attempt qualification bound"
            ),
        }
    return {
        "admitted": True,
        "release_tag": release_tag,
        "source_sha": source_sha,
        "reason": "no active or successful prior exact-candidate qualification run",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref-json", type=Path, required=True)
    parser.add_argument("--annotated-tag-json", type=Path)
    parser.add_argument("--runs-json", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--current-run-id", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-admitted", action="store_true")
    args = parser.parse_args()

    decision = decide(
        _load(args.ref_json),
        _load(args.runs_json),
        release_tag=args.release_tag,
        current_run_id=args.current_run_id,
        annotated_tag=_load(args.annotated_tag_json) if args.annotated_tag_json else None,
    )
    rendered = json.dumps(decision, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(decision["reason"])
    return 0 if decision["admitted"] or not args.require_admitted else 1


if __name__ == "__main__":
    raise SystemExit(main())
