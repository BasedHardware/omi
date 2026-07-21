"""Runtime adapter for the canonical trusted qualification-run admission contract."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_production_source = Path(__file__).with_name("desktop_qualification_admission_contract.py")
_source = (
    _production_source
    if _production_source.exists()
    else Path(__file__).resolve().parents[1] / ".github/scripts/desktop_qualification_admission.py"
)
_spec = importlib.util.spec_from_file_location("desktop_qualification_admission_contract", _source)
assert _spec is not None and _spec.loader is not None
_contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contract)


def validate_qualification_run(run: object, repository: str, release_tag: str, candidate_sha: str) -> None:
    _contract.validate_qualification_run(run, repository, release_tag, candidate_sha)
