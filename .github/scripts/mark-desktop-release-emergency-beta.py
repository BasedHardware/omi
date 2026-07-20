#!/usr/bin/env python3
"""Record the audited break-glass metadata before an emergency beta pointer move."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desktop_release_metadata import fail, normalize_metadata_line  # noqa: E402


def mark_emergency_beta(body: str, evidence: dict) -> str:
    required = {
        "release_tag",
        "source_sha",
        "incident_id",
        "reason",
        "operator",
        "expires_at",
        "operation_id",
        "approvers",
        "evidence",
    }
    if evidence.get("emergencyPromotion") is not True or not required.issubset(evidence):
        fail("validated emergency evidence is incomplete")
    approvers = evidence["approvers"]
    if not isinstance(approvers, list) or len(approvers) != 2:
        fail("emergency metadata requires exactly two approvers")
    if not isinstance(evidence["operation_id"], str) or not evidence["operation_id"]:
        fail("emergency metadata requires a durable operation identity")
    values = {
        "emergencyPromotion": "true",
        "emergencyPromotionApprovers": ",".join(str(item) for item in approvers),
        "emergencyPromotionIncident": str(evidence["incident_id"]),
        "emergencyPromotionReason": str(evidence["reason"]),
        "emergencyPromotionOperator": str(evidence["operator"]),
        "emergencyPromotionExpiresAt": str(evidence["expires_at"]),
        "emergencyPromotionOperationId": str(evidence["operation_id"]),
        "emergencyPromotionEvidence": json.dumps(evidence["evidence"], sort_keys=True, separators=(",", ":")),
    }
    lines, output, in_block, saw_block, saw_live, saw_channel = body.splitlines(), [], False, False, False, False
    for line in lines:
        stripped = normalize_metadata_line(line)
        if stripped == "KEY_VALUE_START":
            in_block, saw_block = True, True
            output.append(line)
            continue
        if stripped == "KEY_VALUE_END":
            if not in_block:
                fail("release body has KEY_VALUE_END without KEY_VALUE_START")
            if not saw_live:
                output.append("isLive: true")
            if not saw_channel:
                output.append("channel: beta")
            output.extend(f"{key}: {value}" for key, value in values.items())
            in_block = False
            output.append(line)
            continue
        if in_block and any(stripped.startswith(f"{key}:") for key in values):
            continue
        if in_block and stripped.startswith("isLive:"):
            output.append("isLive: true")
            saw_live = True
            continue
        if in_block and stripped.startswith("channel:"):
            output.append("channel: beta")
            saw_channel = True
            continue
        output.append(line)
    if in_block or not saw_block:
        fail("release body is missing a complete KEY_VALUE metadata block")
    return "\n".join(output) + ("\n" if body.endswith("\n") else "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    body = Path(args.input).read_text(encoding="utf-8")
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    Path(args.output).write_text(mark_emergency_beta(body, evidence), encoding="utf-8")
    print("desktop release metadata records emergency beta promotion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
