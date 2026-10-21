#!/usr/bin/env python3
"""Explicit operator brake for one existing Android production staged release."""

from __future__ import annotations

import copy
import json
import math
import os
import sys
from pathlib import Path
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mobile_daily_train as train  # noqa: E402
import mobile_store_promote as promote  # noqa: E402


class BrakeError(ValueError):
    pass


def github_json(path: str) -> object:
    request = urllib.request.Request(
        f"https://api.github.com/repos/BasedHardware/omi/{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "omi-android-rollout-brake"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def require_quiesced_writers(fetch=github_json) -> None:
    """Opening even a read edit invalidates another edit by this API user."""
    try:
        for workflow in ("mobile_rollout_watch.yml", "mobile_daily_train.yml"):
            metadata = fetch(f"actions/workflows/{workflow}")
            if not isinstance(metadata, dict) or metadata.get("state") != "disabled_manually":
                raise BrakeError("disable both mobile Play writer workflows before using the brake")
            payload = fetch(f"actions/workflows/{workflow}/runs?per_page=100")
            if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
                raise BrakeError("cannot verify Play writer workflows are drained")
            if any(not isinstance(run, dict) or run.get("status") != "completed" for run in payload["workflow_runs"]):
                raise BrakeError("wait for all mobile Play writer workflow runs to finish before using the brake")
    except BrakeError:
        raise
    except Exception as exc:
        raise BrakeError("cannot verify Play writers are disabled and drained; no edit opened") from exc


def selected_release(track: object, version_code: str) -> dict:
    releases = train._releases(track, "production")
    matches = [release for release in releases if version_code in promote.release_codes(release)]
    if len(matches) != 1:
        raise BrakeError("production must contain exactly one matching release")
    release = matches[0]
    if release.get("status") not in ("draft", "inProgress", "halted", "completed"):
        raise BrakeError("production release status is invalid")
    return release


def run_brake(action: str, version_code: str, confirm: str = "", *, edit_factory=None, quiescence_check=None) -> str:
    # Validate before authenticating or opening any edit.
    if action not in ("halt", "resume", "status"):
        raise BrakeError("BRAKE_ACTION must be halt, resume, or status")
    if not promote.BUILD_RE.fullmatch(version_code):
        raise BrakeError("BRAKE_VERSION_CODE must be a positive integer")
    if action != "status" and confirm != "brake":
        raise BrakeError("mutation requires CONFIRM=brake")
    (quiescence_check or require_quiesced_writers)()
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
            if "countryTargeting" in selected:
                raise BrakeError("country-targeted releases require Play Console handling; status-only mutation refused")
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
            commit = client.edits().commit(packageName=promote.PACKAGE_NAME, editId=edit_id)
            # The runner's pinned discovery document predates this query option.
            # Attach it to the authenticated request without depending on SDK schema age.
            separator = "&" if "?" in commit.uri else "?"
            commit.uri += separator + urllib.parse.urlencode({"changesInReviewBehavior": "ERROR_IF_IN_REVIEW"})
            commit.execute()
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
            try:
                client.edits().delete(packageName=promote.PACKAGE_NAME, editId=open_id).execute()
            except Exception:
                print("BRAKE_WARNING unused edit cleanup failed; edit will expire", file=sys.stderr)


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
