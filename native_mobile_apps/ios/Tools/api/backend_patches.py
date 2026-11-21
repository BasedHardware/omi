"""The app-client spec as the patched backend serves it: upstream's spec plus each
docs/backend-patches/*.openapi.json, the schema half of a backend patch (its .patch is the code half).

The DTO generators of both apps read the spec through `apply`, so a field a backend patch adds is
generated, not edited into the generated file by hand. Properties stay in name order, as the
upstream export writes them.
"""

import json
from pathlib import Path
from typing import Any

PATCH_DIR = Path(__file__).resolve().parents[2] / "docs" / "backend-patches"


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    if "properties" in patch and isinstance(base.get("properties"), dict):
        base["properties"] = dict(sorted(base["properties"].items()))


def apply(spec: dict[str, Any], patch_dir: Path = PATCH_DIR) -> tuple[dict[str, Any], list[str]]:
    """Merges every patch into `spec` in place; returns it and the patch file names, sorted."""
    names = []
    for path in sorted(patch_dir.glob("*.openapi.json")):
        _merge(spec, json.loads(path.read_text(encoding="utf-8")))
        names.append(path.name)
    return spec, names
