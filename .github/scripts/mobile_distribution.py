#!/usr/bin/env python3
"""Validate the provider-neutral evidence used by mobile build baselines.

The Codemagic build status is not distribution evidence: a build may be
``finished`` while a store task failed.  This module deliberately accepts only
the small normalized evidence contract below.  An adapter that reads a
provider response may produce this object, but this module does not guess at
provider-specific fields.

    {
        "schema": "omi-mobile-distribution/v1",
        "platform": "ios" | "android",
        "source_sha": "<40 lowercase hexadecimal characters>",
        "outcome": "distributed" | "no-op",
        "verification": "verified" | "not_applicable"
    }

``distributed`` requires a verified distribution and a settled successful
build.  ``no-op`` is valid only for an explicitly skipped build.  Missing,
unknown, or malformed evidence is never eligible for a release baseline.
"""

from __future__ import annotations

import re
from typing import Any, Optional

SCHEMA = "omi-mobile-distribution/v1"
PLATFORMS = frozenset({"ios", "android"})
SUCCESS_STATUSES = frozenset({"finished", "success", "succeeded"})
SETTLED_STATUSES = SUCCESS_STATUSES | {"skipped"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE_FIELDS = frozenset({"schema", "platform", "source_sha", "outcome", "verification"})
# Codemagic has returned child status under a few provider-shaped names over time.  These
# are deliberately structural names, rather than a recursive scan of every nested mapping:
# unrelated metadata must not turn a successful provider action into a false negative, while
# an explicitly reported child/subaction must be settled successfully before it can support
# distribution evidence.
CHILD_EVIDENCE_KEYS = frozenset(
    {
        "action",
        "actions",
        "child",
        "childaction",
        "childactions",
        "children",
        "appstoreconnecttask",
        "appstoreconnecttasks",
        "subaction",
        "subactions",
        "subtask",
        "subtasks",
        "steps",
        "task",
        "tasks",
    }
)


class DistributionDecision:
    __slots__ = ("eligible", "reason")

    def __init__(self, eligible: bool, reason: str) -> None:
        self.eligible = eligible
        self.reason = reason


def _source_sha(build: dict[str, Any]) -> Optional[str]:
    """Read the already-used commit spellings without interpreting provider evidence."""
    for key in ("commit", "commitId", "commitHash"):
        value = build.get(key)
        if isinstance(value, dict):
            value = value.get("hash") or value.get("sha")
        if isinstance(value, str) and SHA_RE.fullmatch(value):
            return value
    return None


def _invalid(reason: str) -> DistributionDecision:
    return DistributionDecision(False, reason)


def _canonical_key(key: Any) -> str:
    if not isinstance(key, str):
        return ""
    return key.replace("_", "").replace("-", "").lower()


def _child_records_are_successful(value: Any) -> bool:
    """Require every explicitly reported child record to be an object with status success."""
    if isinstance(value, list):
        return bool(value) and all(_child_record_is_successful(child) for child in value)
    if isinstance(value, dict):
        return _child_record_is_successful(value)
    return False


def _child_record_is_successful(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("status") != "success":
        return False
    for key, child_records in value.items():
        if _canonical_key(key) in CHILD_EVIDENCE_KEYS and not _child_records_are_successful(child_records):
            return False
    return True


def _publishing_action_is_successful(action: Any) -> bool:
    """Accept a parent only when all of its explicit child evidence is successful."""
    if not isinstance(action, dict) or action.get("status") != "success":
        return False
    for key, child_records in action.items():
        if _canonical_key(key) in CHILD_EVIDENCE_KEYS and not _child_records_are_successful(child_records):
            return False
    return True


def distribution_decision(build: Any, *, platform: str) -> DistributionDecision:
    """Return whether a build may advance the named platform baseline.

    ``distribution_evidence`` is an Omi-owned normalized contract, not a
    claim about any provider's wire payload.  Unknown fields are rejected so
    a provider response cannot accidentally look verified after a schema
    change.
    """
    if platform not in PLATFORMS:
        return _invalid("unknown platform")
    if not isinstance(build, dict):
        return _invalid("build is not an object")

    status = build.get("status")
    if not isinstance(status, str):
        return _invalid("build status is missing or malformed")
    status = status.lower()
    if status not in SETTLED_STATUSES:
        return _invalid("build has not settled")

    source_sha = _source_sha(build)
    evidence = build.get("distribution_evidence")
    if not isinstance(evidence, dict):
        return _invalid("distribution evidence is missing or malformed")
    if set(evidence) != EVIDENCE_FIELDS:
        return _invalid("distribution evidence fields are not exact")

    if evidence.get("schema") != SCHEMA:
        return _invalid("distribution evidence schema is unknown")
    if evidence.get("platform") != platform:
        return _invalid("distribution evidence platform does not match")
    evidence_sha = evidence.get("source_sha")
    if not isinstance(evidence_sha, str) or not SHA_RE.fullmatch(evidence_sha):
        return _invalid("distribution evidence source is malformed")
    if source_sha is None or source_sha != evidence_sha:
        return _invalid("distribution evidence source does not match the build")

    outcome = evidence.get("outcome")
    verification = evidence.get("verification")
    if status == "skipped":
        if outcome == "no-op" and verification == "not_applicable":
            return DistributionDecision(True, "explicit no-op")
        return _invalid("skipped build lacks an explicit no-op decision")
    if outcome == "distributed" and verification == "verified":
        return DistributionDecision(True, "verified distribution")
    return _invalid("distribution was not verified")


def is_baseline_eligible(build: Any, *, platform: str) -> bool:
    """Boolean convenience wrapper for baseline selection."""
    return distribution_decision(build, platform=platform).eligible


def normalize_codemagic_build(build: Any, *, platform: str, workflow_id: str | None = None) -> Any:
    """Attach verified evidence from a Codemagic build-detail response.

    The list-build response only says that the build finished. The detail
    response has a settled ``Publishing`` action; iOS additionally exposes the
    App Store Connect task list whose failure was the original false-green
    incident. Android's current Codemagic response has no separate Play task
    list, so its settled publishing action is the provider evidence there.
    """
    if not isinstance(build, dict):
        return build
    if "distribution_evidence" in build:
        return build
    actions = build.get("buildActions")
    if not isinstance(actions, list) or not all(isinstance(action, dict) for action in actions):
        return build
    publishing_actions = [
        action
        for action in actions
        if action.get("type") == "publishing" or action.get("name") == "Publishing"
    ]
    if len(publishing_actions) != 1 or not _publishing_action_is_successful(publishing_actions[0]):
        return build
    if platform == "ios":
        tasks = build.get("appStoreConnectTasks")
        if (
            not isinstance(tasks, list)
            or len(tasks) != 1
            or not isinstance(tasks[0], dict)
            or tasks[0].get("name") != "App Store Connect distribution"
            or tasks[0].get("status") != "success"
        ):
            return build
    elif workflow_id != "android-internal-auto":
        # The current Android response has no separate Play task list. Bind the
        # fallback to this exact internal workflow instead of accepting a
        # generic Codemagic publishing action from another workflow.
        return build
    if platform == "ios" and workflow_id not in {None, "ios-internal-auto"}:
        return build
    result = dict(build)
    source_sha = _source_sha(build)
    if source_sha is None:
        return build
    result["distribution_evidence"] = {
        "schema": SCHEMA,
        "platform": platform,
        "source_sha": source_sha,
        "outcome": "distributed",
        "verification": "verified",
    }
    return result
