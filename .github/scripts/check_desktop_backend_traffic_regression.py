#!/usr/bin/env python3
"""Admit a desktop-backend traffic promotion unless it would move the service backwards.

The deploy pipeline serialises runs on one concurrency group and never cancels
in progress (``desktop-backend-auto-dev``). That ordering already prevents a
newer run from routing while an older one holds the lock, so the property worth
enforcing before ``update-traffic`` is *lineage*, not *recency*: the candidate
must not be an ancestor of whatever is serving today.

Comparing the candidate against ``origin/main`` instead fails whenever any
commit lands during the build, which under sustained merge pressure is every
run. That check discards builds that already passed acceptance without
preventing a single Cloud Build, because the build is long finished by the time
traffic is routed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable


# Git exports GIT_DIR & friends while running hooks; the ancestry probes below
# must always target the repository containing the current directory instead.
_GIT_ENV = {
    key: value
    for key, value in os.environ.items()
    if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE"}
}


@dataclass(frozen=True)
class PromotionDecision:
    allowed: bool
    reason: str


#: Returned when the serving revision predates SHA-stamped revisions, or its
#: commit is not reachable in the checkout. Lineage is unprovable, so it is not
#: evidence that the promotion regresses anything.
UNKNOWN_LINEAGE = "unknown-lineage"


def evaluate_traffic_promotion(
    *,
    candidate_sha: str,
    serving_sha: str | None,
    is_ancestor: Callable[[str, str], bool | None],
) -> PromotionDecision:
    """Decide whether ``candidate_sha`` may take 100% traffic from ``serving_sha``.

    ``is_ancestor(a, b)`` reports whether commit ``a`` is an ancestor of commit
    ``b``, or ``None`` when either commit is unresolvable.
    """
    if not candidate_sha:
        raise ValueError("candidate SHA is required to evaluate a traffic promotion")

    if not serving_sha:
        return PromotionDecision(
            allowed=True,
            reason=(
                f"{UNKNOWN_LINEAGE}: serving revision records no release SHA; "
                "cannot prove the promotion moves traffic backwards"
            ),
        )

    if serving_sha == candidate_sha:
        return PromotionDecision(
            allowed=True,
            reason="serving revision is already this candidate's commit; promotion is idempotent",
        )

    ancestry = is_ancestor(serving_sha, candidate_sha)
    if ancestry is None:
        return PromotionDecision(
            allowed=True,
            reason=(
                f"{UNKNOWN_LINEAGE}: {serving_sha} is not reachable in this checkout; "
                "cannot prove the promotion moves traffic backwards"
            ),
        )
    if ancestry:
        return PromotionDecision(
            allowed=True,
            reason=f"candidate {candidate_sha} descends from serving {serving_sha}",
        )

    return PromotionDecision(
        allowed=False,
        reason=(
            f"candidate {candidate_sha} does not descend from serving {serving_sha}; "
            "routing it would move desktop-backend backwards"
        ),
    )


def _git_is_ancestor(repo_ancestor: str, repo_descendant: str) -> bool | None:
    for commit in (repo_ancestor, repo_descendant):
        resolved = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            capture_output=True,
            env=_GIT_ENV,
        )
        if resolved.returncode != 0:
            return None
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", repo_ancestor, repo_descendant],
        capture_output=True,
        env=_GIT_ENV,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    stderr = completed.stderr.decode("utf-8", "replace").strip()
    raise RuntimeError(f"git merge-base --is-ancestor failed: {stderr}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument(
        "--serving-release-sha",
        default="",
        help="Release SHA recorded on the revision serving 100%% traffic; empty when unknown.",
    )
    args = parser.parse_args(argv)

    decision = evaluate_traffic_promotion(
        candidate_sha=args.candidate_sha,
        serving_sha=args.serving_release_sha.strip() or None,
        is_ancestor=_git_is_ancestor,
    )
    if not decision.allowed:
        print(f"ERROR: {decision.reason}; traffic remains unchanged.", file=sys.stderr)
        return 1
    if decision.reason.startswith(UNKNOWN_LINEAGE):
        print(f"::warning title=Unproven traffic lineage::{decision.reason}")
    print(decision.reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
