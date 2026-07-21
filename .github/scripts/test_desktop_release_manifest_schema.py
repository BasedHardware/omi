from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/desktop-release-manifest-v1.schema.json"


def test_artifact_schema_accepts_only_the_single_app_artifact_names():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    stable_zip = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/Omi.zip"
    stable_dmg = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/omi.dmg"

    Draft202012Validator(definitions["zipUrl"]).validate(stable_zip)
    Draft202012Validator(definitions["dmgUrl"]).validate(stable_dmg)
    assert "beta_zip_url" not in schema["properties"]
    assert "beta_dmg_url" not in schema["properties"]
    assert "betaZipUrl" not in definitions
    assert "betaDmgUrl" not in definitions
