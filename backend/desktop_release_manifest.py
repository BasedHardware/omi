"""Runtime adapter for the canonical desktop release manifest contract.

The executable source of truth is copied unchanged from
``.github/scripts/desktop_release_manifest.py`` into the production image as
``desktop_release_manifest_contract.py``.  Local checkouts load that same
file directly, so registration and retained-manifest reads cannot grow a
second schema.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_production_source = Path(__file__).with_name("desktop_release_manifest_contract.py")
_source = (
    _production_source
    if _production_source.exists()
    else Path(__file__).resolve().parents[1] / ".github/scripts/desktop_release_manifest.py"
)
_spec = importlib.util.spec_from_file_location("desktop_release_manifest_contract", _source)
assert _spec is not None and _spec.loader is not None
_contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contract)

ManifestError: type[ValueError] = _contract.ManifestError


def validate_manifest(value: object) -> dict[str, Any]:
    return _contract.validate_manifest(value)
