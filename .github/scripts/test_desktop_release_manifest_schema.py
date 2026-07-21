from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/desktop-release-manifest-v1.schema.json"


def test_beta_artifact_schema_accepts_beta_names_and_keeps_stable_names_distinct():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    stable_zip = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/Omi.zip"
    stable_dmg = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/omi.dmg"
    beta_zip = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/Omi.Beta.zip"
    beta_dmg = "https://github.com/BasedHardware/omi/releases/download/v0.12.64+12064-macos/omi-beta.dmg"

    Draft202012Validator(definitions["zipUrl"]).validate(stable_zip)
    Draft202012Validator(definitions["dmgUrl"]).validate(stable_dmg)
    Draft202012Validator(definitions["betaZipUrl"]).validate(beta_zip)
    Draft202012Validator(definitions["betaDmgUrl"]).validate(beta_dmg)

    assert list(Draft202012Validator(definitions["zipUrl"]).iter_errors(beta_zip))
    assert list(Draft202012Validator(definitions["dmgUrl"]).iter_errors(beta_dmg))
    assert schema["properties"]["beta_zip_url"]["$ref"] == "#/$defs/betaZipUrl"
    assert schema["properties"]["beta_dmg_url"]["$ref"] == "#/$defs/betaDmgUrl"
