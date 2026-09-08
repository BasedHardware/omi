#!/usr/bin/env python3
"""The desktop release manifest schema admits exactly one app artifact pair.

`desktop-release-manifest-v1.schema.json` is what a published Stable manifest is
validated against. The invariant it carries is that a Stable manifest describes
*one* app: `zip_url`/`dmg_url` pointing at `Omi.zip`/`omi.dmg`, with no parallel
beta artifact fields. A `beta_zip_url` re-entering the schema is how a beta build
becomes describable as Stable, so the absence of those fields is load-bearing
rather than tidiness.

This suite is stdlib-only and unittest-style on purpose. It previously imported
`jsonschema` and relied on pytest, and no lane in the repository installs either
-- it had no manifest entry, no workflow step, and nothing referenced it, so it
ran nowhere and could not fail. (#10351 is the same class: a guard whose
self-suite has no blocking audience is a dead check.) Both `$defs` it exercises
are plain `{"type": "string", "pattern": "^...$"}` schemas, and JSON Schema
`pattern` semantics are a regex search -- anchored here -- so `re.search`
validates them exactly as `Draft202012Validator` did, with nothing to install.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/desktop-release-manifest-v1.schema.json"

STABLE_ZIP = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/Omi.zip"
STABLE_DMG = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/omi.dmg"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _matches(subschema: dict, value: str) -> bool:
    """Validate `value` against a string-with-pattern subschema.

    Mirrors the two keywords these `$defs` actually use. A richer subschema would
    be silently under-validated, so the type is asserted rather than assumed.
    """
    assert set(subschema) == {"type", "pattern"}, f"unsupported string subschema shape: {subschema!r}"
    assert subschema["type"] == "string", f"expected a string subschema, got {subschema['type']!r}"
    pattern = subschema["pattern"]
    assert isinstance(pattern, str), f"expected a string pattern, got {type(pattern).__name__}"
    return isinstance(value, str) and re.search(pattern, value) is not None


class ArtifactUrlDefinitions(unittest.TestCase):
    def test_rejects_a_richer_subschema(self):
        with self.assertRaisesRegex(AssertionError, "unsupported string subschema shape"):
            _matches({"type": "string", "pattern": "^value$", "minLength": 1}, "value")

    def test_accepts_the_canonical_stable_artifact_urls(self):
        defs = _load_schema()["$defs"]
        self.assertTrue(_matches(defs["zipUrl"], STABLE_ZIP), "zipUrl rejected the canonical Stable zip")
        self.assertTrue(_matches(defs["dmgUrl"], STABLE_DMG), "dmgUrl rejected the canonical Stable dmg")

    def test_rejects_a_beta_named_artifact(self):
        """The pattern, not just the field list, is what keeps a beta build out."""
        defs = _load_schema()["$defs"]
        beta_zip = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/Omi-Beta.zip"
        beta_dmg = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/omi-beta.dmg"
        self.assertFalse(_matches(defs["zipUrl"], beta_zip), "zipUrl accepted a beta-named zip")
        self.assertFalse(_matches(defs["dmgUrl"], beta_dmg), "dmgUrl accepted a beta-named dmg")

    def test_rejects_an_artifact_from_another_host_or_repo(self):
        defs = _load_schema()["$defs"]
        for bad in (
            "https://example.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/Omi.zip",
            "https://github.com/attacker/omi/releases/download/v0.12.64+12064-macos/Omi.zip",
        ):
            self.assertFalse(_matches(defs["zipUrl"], bad), f"zipUrl accepted {bad}")


class BetaFieldsStayOutOfTheStableSchema(unittest.TestCase):
    def test_t2_evidence_asset_rule_matches_the_executable_contract(self):
        schema = _load_schema()
        t2_rule = next(
            rule
            for rule in schema["allOf"]
            if rule.get("if", {}).get("properties", {}).get("qualification_tier") == {"const": "T2"}
        )
        evidence = t2_rule["then"]["properties"]["qualification_evidence_asset"]
        self.assertTrue(re.fullmatch(evidence["pattern"], "qualification-evidence-0.12.159+12159.json"))
        self.assertIsNone(re.fullmatch(evidence["pattern"], "desktop-smoke-result-beta.json"))

    def test_no_beta_artifact_properties(self):
        schema = _load_schema()
        self.assertNotIn("beta_zip_url", schema["properties"])
        self.assertNotIn("beta_dmg_url", schema["properties"])

    def test_no_beta_artifact_definitions(self):
        defs = _load_schema()["$defs"]
        self.assertNotIn("betaZipUrl", defs)
        self.assertNotIn("betaDmgUrl", defs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
