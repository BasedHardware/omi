#!/usr/bin/env python3
"""Every People-Intelligence field the UI decodes must have a writer, or be a declared gap.

People Intelligence shipped a profile UI for data no code in this repository produced.
`who`, `now`, `overall` and `facts` had decoders, renderers and zero writers; the only
machine the feature was reviewed on had a `people_intelligence.json` written by an
out-of-tree prototype, so nobody saw the empty card a new user actually gets.

This is the mechanical version of the rule that was violated. For every JSON key that
`PeopleIntelPerson` / `PersonExtrasRow` / `PersonConnectionDetail` / `PeopleExtrasFile`
decodes it requires two things:

  1. **A writer, or an explicit gap.** Some People/Person source file must write the key,
     or the key must appear in NOT_IMPLEMENTED below with a reason. The allowlist is a
     ratchet: a listed field that acquires a writer must be removed from it.
  2. **A cold-start classification.** The key must be classified in
     `Desktop/Tests/PeopleColdStartContractTests.swift`, which asserts a first run either
     produces it or provably does not. That is what ties a new renderer to the question
     "does anything write this on the only path a new user takes?".

Layer status and phase ownership: desktop/macos/docs/people-intelligence-productization.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DESKTOP_DIR = SCRIPT_DIR.parent
PAGES_DIR = DESKTOP_DIR / "Desktop" / "Sources" / "MainWindow" / "Pages"
PROVIDERS_DIR = DESKTOP_DIR / "Desktop" / "Sources" / "Providers"
COLD_START_TEST = DESKTOP_DIR / "Desktop" / "Tests" / "PeopleColdStartContractTests.swift"
DOC = "desktop/macos/docs/people-intelligence-productization.md"

# The decoders whose fields the People list and profile render, and the Swift type inside
# each file whose `CodingKeys` define the on-disk key names.
DECODERS = (
    ("PeoplePage.swift", "PeopleIntelPerson"),
    ("PersonProfileExtras.swift", "PersonExtrasRow"),
    ("PersonProfileExtras.swift", "PersonConnectionDetail"),
    ("PersonProfileExtras.swift", "PeopleExtrasFile"),
)

# Fields with no in-repo writer, deliberately. Each entry states the layer that owns it.
# This list may only shrink: acquiring a writer means the field moved out of it.
NOT_IMPLEMENTED = {
    "role": "Phase 3 model-backed relationship role; produced only out-of-tree today",
    "linkedin": "no LinkedIn connector in-repo; Phase 2 'Affiliations from LinkedIn' is next",
    "network_insights": "file-level network summary; Phase 3, nothing writes it",
}

# Key names a nested value object also uses, so a source-wide search cannot tell which
# surface a write belongs to. `PersonAffiliation` decodes `type` and `confidence` and the
# affiliation writer emits both, which makes the identically-named connection-level keys
# indistinguishable here. The cold-start contract test *is* per-surface (it walks
# connections[] specifically), so these keys are checked there and only classification is
# enforced below.
AMBIGUOUS = {
    "type": "PersonAffiliation.type is written; connections[].type is Phase 3",
    "confidence": "PersonAffiliation.confidence is written; connections[].confidence is Phase 3",
}

# Structural keys that are the container rather than a rendered value.
STRUCTURAL = {"people"}

# A key is "written" when a People/Person source assigns it into a dictionary that becomes
# part of people_intelligence.json, or hands it to the narrative's key-setters.
WRITE_PATTERNS = (
    r"\w+\[{key}\]\s*=",  # person["relationship"] = ...
    r"{key}\s*:",  # dictionary literal entry
    r"\({key}\s*,",  # setText("who", ...) / setList("facts", ...)
    r"removeValue\(forKey:\s*{key}\)",  # narrative clears the key it owns
)


def swift_sources() -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for directory in (PAGES_DIR, PROVIDERS_DIR):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.swift")):
            if path.name.startswith(("People", "Person")):
                files.append((path.name, path.read_text(encoding="utf-8")))
    return files


def coding_keys(source: str, type_name: str) -> set[str]:
    """JSON key names from `type_name`'s CodingKeys enum.

    Handles both forms Swift allows: bare cases (`case id, name, relationship`) where the
    case name is the key, and renamed cases (`case historyGrounded = "history_grounded"`).
    """
    declaration = re.search(
        rf"(?:struct|final class|class)\s+{re.escape(type_name)}\b", source
    )
    if not declaration:
        raise SystemExit(
            f"check_people_intel_field_writers: {type_name} not found — update DECODERS"
        )
    tail = source[declaration.end() :]
    enum = re.search(r"enum\s+CodingKeys\s*:[^{]*\{(.*?)\n\s*\}", tail, re.DOTALL)
    if not enum:
        # Single-line form: `enum CodingKeys: String, CodingKey { case name, category }`
        enum = re.search(r"enum\s+CodingKeys\s*:[^{]*\{([^}]*)\}", tail)
    if not enum:
        raise SystemExit(
            f"check_people_intel_field_writers: {type_name} has no CodingKeys — update DECODERS"
        )
    keys: set[str] = set()
    for line in enum.group(1).splitlines():
        line = line.split("//")[0].strip()
        if not line.startswith("case "):
            continue
        for item in line[len("case ") :].split(","):
            item = item.strip()
            if not item:
                continue
            renamed = re.match(r"\w+\s*=\s*\"([^\"]+)\"", item)
            keys.add(renamed.group(1) if renamed else item)
    return keys


def has_writer(key: str, sources: list[tuple[str, str]]) -> str | None:
    literal = re.escape(f'"{key}"')
    patterns = [re.compile(p.format(key=literal)) for p in WRITE_PATTERNS]
    for name, source in sources:
        # A decoder's own CodingKeys renaming is not a writer.
        body = re.sub(r"enum\s+CodingKeys\s*:[^{]*\{[^}]*\}", "", source, flags=re.DOTALL)
        if any(pattern.search(body) for pattern in patterns):
            return name
    return None


def classified_keys() -> set[str]:
    if not COLD_START_TEST.is_file():
        raise SystemExit(
            "check_people_intel_field_writers: the cold-start contract test is missing; it is "
            "what proves a first run either produces each field or provably does not"
        )
    source = COLD_START_TEST.read_text(encoding="utf-8")
    return set(
        re.findall(
            r"\"([A-Za-z_][A-Za-z0-9_]*)\"\s*:\s*\.(?:produced|absentByDesign|notAssertableHermetically)",
            source,
        )
    )


def main() -> int:
    sources = swift_sources()
    if not sources:
        print("check_people_intel_field_writers: no People/Person sources found", file=sys.stderr)
        return 2

    decoded: dict[str, set[str]] = {}
    for file_name, type_name in DECODERS:
        path = PAGES_DIR / file_name
        if not path.is_file():
            raise SystemExit(f"check_people_intel_field_writers: missing {path}")
        for key in coding_keys(path.read_text(encoding="utf-8"), type_name):
            decoded.setdefault(key, set()).add(type_name)

    classified = classified_keys()
    failures: list[str] = []

    for key in sorted(decoded):
        owners = ", ".join(sorted(decoded[key]))
        writer = has_writer(key, sources) if key not in AMBIGUOUS else None
        if key in AMBIGUOUS:
            pass  # writer ownership is proven per-surface by the cold-start contract test
        elif key in NOT_IMPLEMENTED:
            if writer:
                failures.append(
                    f"'{key}' ({owners}) is on the not-implemented allowlist but {writer} now "
                    f"writes it. Remove it from NOT_IMPLEMENTED and update {DOC}."
                )
        elif not writer and key not in STRUCTURAL:
            failures.append(
                f"'{key}' is decoded by {owners} and rendered by the People UI, but nothing in "
                f"this repository writes it. Either write it, or add it to NOT_IMPLEMENTED with "
                f"the layer that owns it and record that in {DOC}."
            )
        if key not in classified and key not in STRUCTURAL:
            failures.append(
                f"'{key}' ({owners}) is not classified in {COLD_START_TEST.name}. Every field the "
                f"profile decodes must declare whether a cold start produces it — that test is the "
                f"only thing that runs the create path a new user takes."
            )

    stale = sorted(set(NOT_IMPLEMENTED) - set(decoded))
    for key in stale:
        failures.append(
            f"'{key}' is on the not-implemented allowlist but no decoder reads it any more; "
            f"drop the entry."
        )

    if failures:
        print("People Intelligence decoded-field contract violations:\n", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(f"\nLayer status and phase ownership: {DOC}", file=sys.stderr)
        return 1

    print(
        f"check_people_intel_field_writers: {len(decoded)} decoded fields — all have a writer or a "
        f"declared gap, and all are classified for cold start"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
