"""Runtime adapter for the canonical desktop qualification evidence contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_production_source = Path(__file__).with_name("desktop_qualification_evidence_contract.py")
_source = (
    _production_source
    if _production_source.exists()
    else Path(__file__).resolve().parents[1] / ".github/scripts/desktop_qualification_evidence.py"
)
_spec = importlib.util.spec_from_file_location("desktop_qualification_evidence_contract", _source)
assert _spec is not None and _spec.loader is not None
_contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contract)


def verify_evidence(
    evidence: dict[str, Any], release: dict[str, Any], release_tag: str, source_sha: str, digests: dict[str, str]
) -> None:
    _contract.verify_evidence(evidence, release, release_tag, source_sha, digests)
