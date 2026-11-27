#!/usr/bin/env python3
"""Decide whether a protected Pusher image-only run pages Release, and write its summary.

The workflow runs this after the image-only step whatever its outcome. Inputs are
the receipt that `pusher_image_only.py` prints (through `tee`) and the write-attempt
marker it makes durable before each live patch. A marker with a missing, empty or
invalid receipt means the writer died after a patch could have been sent: that is
an UNCERTAIN_AFTER_WRITE HOLD and pages, like every other HOLD.

Standard library only, so the page cannot be lost to an import failure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

UNCERTAIN_AFTER_WRITE = "UNCERTAIN_AFTER_WRITE"
FINAL = {"PASS", "HOLD", "REVERSED"}
BASELINE = "gcr.io/based-hardware/pusher@sha256:f26e8757759fe6907a9ef0e4c31d0a08a8ed527d777db5f472b33bffcff6d925"
NAMESPACE = "prod-omi-backend"
TARGET = "prod-omi-pusher"
RUNBOOK = "backend/docs/runbooks/pusher-image-preservation-proposal.md"
PAGE_FIELDS = (
    "reason",
    "hold_stage",
    "reverse_patch",
    "deployment_uid_before",
    "deployment_uid_observed",
    "serving_image_observed",
)
SUMMARY_FIELDS = (
    "stage",
    "hold_stage",
    "reason",
    "post_write_failure",
    "inverse_refusal",
    "live_inverse_server_dry_run",
    "reverse_patch",
    "reverse_refusal",
    "deployment_uid_before",
    "deployment_uid_observed",
    "patched_deployment_uid",
    "requested_image",
    "serving_image_observed",
    "serving_image",
    "serving_deployment_uid",
    "ready_replicas",
    "write_marker",
)


def load(receipt_path: Path, marker_path: Path) -> dict:
    """The effective outcome: the receipt, or an UNCERTAIN_AFTER_WRITE HOLD when it cannot be trusted."""
    marker = marker_path.exists()
    try:
        text = receipt_path.read_text(encoding="utf-8")
        receipt = json.loads(text) if text.strip() else None
    except (OSError, ValueError):
        receipt = None
    if not isinstance(receipt, dict) or not isinstance(receipt.get("status"), str):
        if not marker:
            return {}
        return {
            "status": "HOLD",
            "reason": UNCERTAIN_AFTER_WRITE,
            "hold_stage": "receipt_missing_after_write",
            "reverse_patch": "unknown",
            "deployment_uid_before": "unknown",
            "deployment_uid_observed": "unread",
            "serving_image_observed": "unread",
            "write_marker": "present",
        }
    if marker and receipt["status"] not in FINAL:
        # pusher_image_only.main() already turns this into a HOLD; keep it so here too.
        return receipt | {
            "status": "HOLD",
            "reason": UNCERTAIN_AFTER_WRITE,
            "post_write_failure": receipt.get("reason"),
            "hold_stage": receipt.get("hold_stage") or "refused_after_write_marker",
            "write_marker": "present",
        }
    return receipt | ({"write_marker": "present"} if marker else {})


def safe(value) -> str:
    """The page is interpolated by the notifier: keep a closed character set."""
    return re.sub(r"[^A-Za-z0-9 ._:/=@,-]", "_", str(value))[:120]


def page(outcome: dict) -> str:
    status = outcome.get("status")
    if status not in {"HOLD", "REVERSED"}:
        return ""
    details = ", ".join(f"{key}={safe(outcome.get(key, 'n/a'))}" for key in PAGE_FIELDS)
    if status == "REVERSED":
        return f"REVERSED, promote did not complete. {details}. See the run summary."
    return (
        f"HOLD, no further patch. {details}. Restore only per the runbook Manual recovery after a HOLD: "
        "confirm the Deployment UID, if it already specifies the pinned baseline digest do not patch, otherwise "
        "rollout undo --to-revision of the revision verified to hold that digest, never an unpinned undo. "
        "See the run summary."
    )


def summary(outcome: dict) -> str:
    held = outcome.get("status") == "HOLD"
    lines = [
        f"### Pusher image-only {'HOLD' if held else 'REVERSED'}: `{outcome.get('reason')}`",
        "",
        (
            "Recovery after the forward write could not prove the baseline, so the job held with no further patch."
            if held
            else "The one guarded reverse restored the pinned baseline with every replica ready; the promote did not complete."
        ),
        "",
    ]
    lines += [f"- `{key}`: `{outcome[key]}`" for key in SUMMARY_FIELDS if key in outcome]
    if held:
        uid = outcome.get("deployment_uid_before", "unknown")
        image = "{.spec.template.spec.containers[?(@.name==\"pusher\")].image}{\"\\n\"}"
        lines += [
            "",
            "**Manual restore (Release prod-operator).** "
            + str(outcome.get("manual_restore_path") or f"Follow {RUNBOOK}, Manual recovery after a HOLD."),
            "",
            "```sh",
            f"# 1. Stop and escalate unless this prints the receipt's deployment_uid_before: {uid}",
            f"kubectl -n {NAMESPACE} get deployment {TARGET} -o jsonpath='{{.metadata.uid}}{{\"\\n\"}}'",
            f"# 2. If this prints the pinned baseline {BASELINE},",
            "#    do not patch: skip to step 4.",
            f"kubectl -n {NAMESPACE} get deployment {TARGET} -o jsonpath='{image}'",
            "# 3. Otherwise pick the revision N whose pusher image reads that baseline digest, and restore only it:",
            f"kubectl -n {NAMESPACE} rollout history deployment/{TARGET}",
            f"kubectl -n {NAMESPACE} rollout history deployment/{TARGET} --revision=N -o jsonpath='{image}'",
            f"kubectl -n {NAMESPACE} rollout undo deployment/{TARGET} --to-revision=N",
            "# 4. Wait and read back: the baseline digest on every ready pod and a clean status report.",
            f"kubectl -n {NAMESPACE} rollout status deployment/{TARGET} --timeout=160m",
            "python3 backend/scripts/deploy_status_report.py --env prod --include-gke --gke-service pusher",
            "```",
            "",
            f"Runbook: {RUNBOOK}, Manual recovery after a HOLD.",
        ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("output", "summary"))
    parser.add_argument("receipt", type=Path)
    parser.add_argument("marker", type=Path)
    args = parser.parse_args(argv)
    outcome = load(args.receipt, args.marker)
    if args.action == "output":
        print(f"status={safe(outcome.get('status') or '')}")
        print(f"page={page(outcome)}")
    elif outcome.get("status") in {"HOLD", "REVERSED"}:
        print(summary(outcome))
    return 0


if __name__ == "__main__":
    sys.exit(main())
