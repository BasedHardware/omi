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


# Play's per-language What's New limit.
PLAY_NOTES_LIMIT = 500


def github_json(path: str) -> object:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "omi-android-rollout-brake"}
    # Codemagic's shared runners exhaust GitHub's anonymous rate limit; the
    # read-only mobile_release_admission token lifts it.
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"https://api.github.com/repos/BasedHardware/omi/{path}", headers=headers)
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


def parse_stage_fraction(value: str) -> float:
    try:
        fraction = float(value)
    except ValueError:
        raise BrakeError("BRAKE_USER_FRACTION must be a number strictly between 0 and 1") from None
    if not math.isfinite(fraction) or not 0 < fraction < 1:
        raise BrakeError("BRAKE_USER_FRACTION must be a number strictly between 0 and 1")
    return fraction


def staged_source_version(sources: dict[str, object], version_code: str) -> str:
    """X.Y.Z of the uploaded test-track build that carries exactly this code."""
    versions = set()
    for track_name, track in sources.items():
        for release in train._releases(track, track_name):
            codes = promote.release_codes(release)
            if version_code not in codes:
                continue
            name = release.get("name")
            version = promote.production_release_version(name) if isinstance(name, str) else None
            if codes != [version_code] or version is None:
                raise BrakeError(f"{track_name} release for the stage code must carry only that code and a version")
            versions.add(version)
    if len(versions) != 1:
        raise BrakeError("stage code must be on internal or alpha with exactly one marketing version")
    return versions.pop()


def stage_notes(halted: dict, fix_line: str) -> list[dict]:
    """The halted release's What's New, with the English fix line added.

    The line is appended, or replaces the last line when appending would pass
    Play's limit. It goes on en-US and on every locale carrying the identical
    English text (the train copies it to each locale); real translations stay as-is.
    """
    notes = copy.deepcopy(halted.get("releaseNotes"))
    if not isinstance(notes, list) or any(not isinstance(entry, dict) for entry in notes):
        raise BrakeError("halted release has no readable release notes")
    english = [entry for entry in notes if entry.get("language") == "en-US"]
    if len(english) != 1 or not isinstance(english[0].get("text"), str) or not english[0]["text"].strip():
        raise BrakeError("halted release must carry exactly one non-empty en-US note")
    source = english[0]["text"]
    # Android store notes are one "; "-joined line (mobile-changelog android_notes);
    # hand-written ones may be newline bullets. Keep whichever shape Play holds.
    separator = "\n" if "\n" in source.strip() else "; "
    lines = source.strip().split(separator)
    updated = separator.join([*lines, fix_line])
    if len(updated) > PLAY_NOTES_LIMIT and len(lines) > 1:
        updated = separator.join([*lines[:-1], fix_line])
    if len(updated) > PLAY_NOTES_LIMIT:
        raise BrakeError(
            f"en-US release notes would exceed Play's {PLAY_NOTES_LIMIT} characters "
            f"(current={len(source.rstrip())} line={len(fix_line)})"
        )
    for entry in notes:
        if entry.get("text") == source:
            entry["text"] = updated
    return notes


def stage_track(
    production: object, sources: dict[str, object], version_code: str, supersedes: str, fraction: float, fix_line: str
):
    """Expected production track: the halted release replaced by a new staged one.

    Every other release (the completed one still serving most users) stays as
    Play returned it, so the commit changes only the superseded entry.
    """
    releases = train._releases(production, "production")
    if any(version_code in promote.release_codes(release) for release in releases):
        raise BrakeError("stage code is already on production")
    halted = selected_release(production, supersedes)
    if halted.get("status") != "halted":
        raise BrakeError("stage requires the superseded release to be status=halted")
    if any(release is not halted and release.get("status") != "completed" for release in releases):
        raise BrakeError("stage requires production to hold only completed releases besides the halted one")
    if "countryTargeting" in halted:
        raise BrakeError("country-targeted releases require Play Console handling; stage refused")
    halted_fraction = halted.get("userFraction")
    if isinstance(halted_fraction, bool) or not isinstance(halted_fraction, (int, float)) or fraction > halted_fraction:
        raise BrakeError("stage fraction must not exceed the halted release's userFraction")
    halted_version = promote.production_release_version(str(halted.get("name") or ""))
    version = staged_source_version(sources, version_code)
    if halted_version is None or promote.version_parts(version) <= promote.version_parts(halted_version):
        raise BrakeError("stage version must be newer than the halted release")
    release = {
        "name": train._staged_name_with_receipt(version),
        "versionCodes": [version_code],
        "status": "inProgress",
        "userFraction": fraction,
        "releaseNotes": stage_notes(halted, fix_line),
    }
    expected = copy.deepcopy(production)
    expected["releases"] = [release if old is halted else copy.deepcopy(old) for old in releases]
    return expected, halted_fraction


def commit_expected(client: object, edit_id: str, expected: object, open_edits: list) -> None:
    updated = client.edits().tracks().update(
        packageName=promote.PACKAGE_NAME, editId=edit_id, track="production", body=expected
    ).execute()
    if updated != expected:
        raise BrakeError("Play update response did not match the intended change; edit not committed")
    commit = client.edits().commit(packageName=promote.PACKAGE_NAME, editId=edit_id)
    # The runner's pinned discovery document predates this query option.
    # Attach it to the authenticated request without depending on SDK schema age.
    # changesNotSentForReview follows promote.CHANGES_NOT_SENT_FOR_REVIEW so a
    # brake edit joins the same held-changes queue (and the same Play Console
    # -> Publishing overview -> Send for review step) as every other committed
    # Play edit, and unholds with them when the constant flips back.
    separator = "&" if "?" in commit.uri else "?"
    commit_params = {"changesInReviewBehavior": "ERROR_IF_IN_REVIEW"}
    if promote.CHANGES_NOT_SENT_FOR_REVIEW:
        commit_params["changesNotSentForReview"] = "true"
    commit.uri += separator + urllib.parse.urlencode(commit_params)
    commit.execute()
    open_edits.remove(edit_id)
    # A committed edit cannot be reused. Open a fresh edit to read live state.
    read_id = client.edits().insert(packageName=promote.PACKAGE_NAME, body={}).execute()["id"]
    open_edits.append(read_id)
    actual = promote.play_track(client, read_id, "production")
    if actual != expected:
        raise BrakeError("post-commit production readback mismatch; inspect live status before retrying")


def run_brake(
    action: str,
    version_code: str,
    confirm: str = "",
    *,
    user_fraction: str = "",
    supersedes: str = "",
    notes_line: str = "",
    edit_factory=None,
    quiescence_check=None,
) -> str:
    # Validate before authenticating or opening any edit.
    if action not in ("halt", "resume", "status", "stage"):
        raise BrakeError("BRAKE_ACTION must be halt, resume, status, or stage")
    if not promote.BUILD_RE.fullmatch(version_code):
        raise BrakeError("BRAKE_VERSION_CODE must be a positive integer")
    if action != "status" and confirm != "brake":
        raise BrakeError("mutation requires CONFIRM=brake")
    if action == "stage":
        fraction_target = parse_stage_fraction(user_fraction)
        if not promote.BUILD_RE.fullmatch(supersedes) or supersedes == version_code:
            raise BrakeError("stage requires BRAKE_SUPERSEDES_VERSION_CODE naming the halted release")
        if not notes_line.strip() or "\n" in notes_line:
            raise BrakeError("stage requires a one-line BRAKE_NOTES_LINE for the en-US What's New")
    (quiescence_check or require_quiesced_writers)()
    edit_factory = edit_factory or promote.play_edit
    client, edit_id = edit_factory()
    open_edits = [edit_id]
    try:
        production = promote.play_track(client, edit_id, "production")
        if action == "stage":
            sources = {name: promote.play_track(client, edit_id, name) for name in ("internal", "alpha")}
            expected, halted_fraction = stage_track(
                production, sources, version_code, supersedes, fraction_target, notes_line.strip()
            )
            commit_expected(client, edit_id, expected, open_edits)
            staged = selected_release(expected, version_code)
            return (
                f"BRAKE_RESULT action=stage versionCode={version_code} status_before=absent "
                f"status_after=inProgress userFraction={fraction_target} supersedes={supersedes} "
                f"superseded_status=halted superseded_userFraction={halted_fraction} name={staged['name']!r}"
            )
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
            commit_expected(client, edit_id, expected, open_edits)
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
            user_fraction=os.environ.get("BRAKE_USER_FRACTION", ""),
            supersedes=os.environ.get("BRAKE_SUPERSEDES_VERSION_CODE", ""),
            notes_line=os.environ.get("BRAKE_NOTES_LINE", ""),
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
