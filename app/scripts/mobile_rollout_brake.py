#!/usr/bin/env python3
"""Explicit operator brake for one existing Android production staged release."""

from __future__ import annotations

import copy
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mobile_daily_train as train  # noqa: E402
import mobile_store_promote as promote  # noqa: E402


class BrakeError(ValueError):
    pass


def selected_release(track: object, version_code: str) -> dict:
    releases = train._releases(track, "production")
    matches = [release for release in releases if version_code in promote.release_codes(release)]
    if len(matches) != 1:
        raise BrakeError("production must contain exactly one matching release")
    release = matches[0]
    if release.get("status") not in ("draft", "inProgress", "halted", "completed"):
        raise BrakeError("production release status is invalid")
    return release


def run_brake(action: str, version_code: str, confirm: str = "", *, edit_factory=None) -> str:
    # Validate before authenticating or opening any edit.
    if action not in ("halt", "resume", "status"):
        raise BrakeError("BRAKE_ACTION must be halt, resume, or status")
    if not promote.BUILD_RE.fullmatch(version_code):
        raise BrakeError("BRAKE_VERSION_CODE must be a positive integer")
    if action != "status" and confirm != "brake":
        raise BrakeError("mutation requires CONFIRM=brake")
    edit_factory = edit_factory or promote.play_edit
    client, edit_id = edit_factory()
    open_edits = [edit_id]
    try:
        production = promote.play_track(client, edit_id, "production")
        selected = selected_release(production, version_code)
        before = selected["status"]
        fraction = selected.get("userFraction")
        expected = copy.deepcopy(production)
        after = before
        if action != "status":
            required, after = ("inProgress", "halted") if action == "halt" else ("halted", "inProgress")
            if before != required:
                raise BrakeError(f"{action} requires status={required}")
            if (
                isinstance(fraction, bool)
                or not isinstance(fraction, (int, float))
                or not math.isfinite(fraction)
                or not 0 < fraction < 1
            ):
                raise BrakeError("staged release must have userFraction strictly between 0 and 1")
            selected_release(expected, version_code)["status"] = after
            updated = client.edits().tracks().update(
                packageName=promote.PACKAGE_NAME, editId=edit_id, track="production", body=expected
            ).execute()
            if updated != expected:
                raise BrakeError("Play update response did not match the status-only change; edit not committed")
            client.edits().commit(packageName=promote.PACKAGE_NAME, editId=edit_id).execute()
            open_edits.remove(edit_id)
            # A committed edit cannot be reused. Open a fresh edit to read live state.
            read_id = client.edits().insert(packageName=promote.PACKAGE_NAME, body={}).execute()["id"]
            open_edits.append(read_id)
            actual = promote.play_track(client, read_id, "production")
            if actual != expected:
                raise BrakeError("post-commit production readback mismatch; inspect live status before retrying")
        return (
            f"BRAKE_RESULT action={action} versionCode={version_code} "
            f"status_before={before} status_after={after} userFraction={fraction}"
        )
    finally:
        for open_id in open_edits:
            client.edits().delete(packageName=promote.PACKAGE_NAME, editId=open_id).execute()


def main() -> int:
    try:
        result = run_brake(
            os.environ.get("BRAKE_ACTION", ""),
            os.environ.get("BRAKE_VERSION_CODE", ""),
            os.environ.get("CONFIRM", ""),
        )
    except (BrakeError, promote.PromotionError, train.TrainError) as exc:
        print(f"BRAKE_ERROR {exc}", file=sys.stderr)
        return 1
    except Exception:
        # Google client exceptions may contain credential or request details.
        print("BRAKE_ERROR Play operation failed; inspect live status before retrying", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
