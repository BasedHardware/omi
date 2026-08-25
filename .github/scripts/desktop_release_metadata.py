#!/usr/bin/env python3
"""Shared parsing and lifecycle helpers for desktop release metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

TRUE_VALUES = {"true", "1", "yes"}


@dataclass(frozen=True)
class DesktopQualification:
    qualified: bool
    sha: str
    qualified_at: str
    tier: str
    evidence: str
    source: str


def fail(message: str) -> NoReturn:
    raise SystemExit(f"FAIL: {message}")


def normalize_metadata_line(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("<!--"):
        stripped = stripped[4:].strip()
    if stripped.endswith("-->"):
        stripped = stripped[:-3].strip()
    return stripped


def parse_metadata(body: str) -> dict[str, str]:
    in_block = False
    metadata: dict[str, str] = {}

    for line in body.splitlines():
        stripped = normalize_metadata_line(line)
        if stripped == "KEY_VALUE_START":
            in_block = True
            continue
        if stripped == "KEY_VALUE_END":
            return metadata
        if not in_block or not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            fail(f"invalid release metadata line: {stripped}")
        key, value = stripped.split(":", 1)
        metadata[key.strip()] = value.strip()

    fail("release body is missing KEY_VALUE_START/KEY_VALUE_END metadata block")


def desktop_qualification_from_metadata(metadata: dict[str, str]) -> DesktopQualification:
    """Read canonical qualification keys, falling back to legacy blessed keys."""
    if "qualifiedBeta" in metadata:
        return DesktopQualification(
            qualified=metadata.get("qualifiedBeta", "").strip().lower() in TRUE_VALUES,
            sha=metadata.get("qualifiedBetaSha", "").strip(),
            qualified_at=metadata.get("qualifiedBetaAt", "").strip(),
            tier=metadata.get("qualifiedBetaTier", "").strip(),
            evidence=metadata.get("qualifiedBetaEvidence", "").strip(),
            source="canonical",
        )
    return DesktopQualification(
        qualified=metadata.get("blessed", "").strip().lower() in TRUE_VALUES,
        sha=metadata.get("blessedSha", "").strip(),
        qualified_at=metadata.get("blessedAt", "").strip(),
        tier=metadata.get("blessedTier", "").strip(),
        evidence=metadata.get("blessedEvidence", "").strip(),
        source="legacy",
    )


def require_desktop_qualification(
    qualification: DesktopQualification,
    *,
    target_sha: str,
    asset_names: set[str],
) -> None:
    if not qualification.qualified:
        fail("release must have qualifiedBeta: true (legacy blessed metadata is also accepted)")
    if qualification.tier != "2":
        fail(f"release qualification tier must be 2, got {qualification.tier!r}")
    if qualification.sha != target_sha:
        fail("release qualification SHA does not match the release tag commit")
    if not qualification.qualified_at:
        fail("release qualification is missing its timestamp")
    if not qualification.evidence:
        fail("release qualification is missing its evidence asset")
    if qualification.evidence not in asset_names:
        fail(f"release is missing qualification evidence asset {qualification.evidence!r}")


def update_metadata(body: str, values: dict[str, str]) -> str:
    """Replace or append keys inside the release metadata block."""
    if any("\n" in value or "\r" in value for value in values.values()):
        fail("release metadata values must be single-line strings")

    lines = body.splitlines()
    output: list[str] = []
    in_block = False
    saw_block = False
    seen: set[str] = set()
    for line in lines:
        stripped = normalize_metadata_line(line)
        if stripped == "KEY_VALUE_START":
            if in_block:
                fail("release body has nested KEY_VALUE_START blocks")
            in_block = True
            saw_block = True
            output.append(line)
            continue
        if stripped == "KEY_VALUE_END":
            if not in_block:
                fail("release body has KEY_VALUE_END without KEY_VALUE_START")
            for key, value in values.items():
                if key not in seen:
                    output.append(f"{key}: {value}")
            in_block = False
            output.append(line)
            continue
        if in_block and ":" in stripped:
            key = stripped.split(":", 1)[0].strip()
            if key in values:
                output.append(f"{key}: {values[key]}")
                seen.add(key)
                continue
        output.append(line)

    if in_block:
        fail("release body metadata block is missing KEY_VALUE_END")
    if not saw_block:
        fail("release body is missing KEY_VALUE_START/KEY_VALUE_END metadata block")
    return "\n".join(output) + ("\n" if body.endswith("\n") else "")
