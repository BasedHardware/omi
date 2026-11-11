"""Shared fixture for the storm-alignment family parity grid.

Loads the real contention-family sources from THIS checkout, judges every
function with the real scanner (``scripts/scan_storm_alignment.py``) in two
postures, and caches both catalogs at import so each grid cell is a dict
lookup -- no per-cell I/O or parsing:

- FIXED: the tree as landed. The family-wide contract is that this posture
  has zero findings: every contention re-offer surface consumes the
  measured storm window (or waits none).
- ABLATED: every alignment helper name rewritten to a dead
  ``__dealigned`` form. Functions whose alignment rides those helper names
  flip to a bare-ladder finding -- the blackout regression surface. The
  pinned flip set is exactly the publication re-strike lane.

Failure-Class: FC-publication-restrike-collides-inside-the-armed-storm-window
"""

from scripts.scan_storm_alignment import (
    BACKEND_ROOT,
    FAMILY_FILES,
    ablate_source,
    catalog_source,
    scan_tree_catalog,
)

FIXED = "fixed"
ABLATED = "ablated"


def _catalog(posture: str) -> dict:
    if posture == FIXED:
        return scan_tree_catalog(BACKEND_ROOT, FAMILY_FILES)
    ablated = {}
    for rel in FAMILY_FILES:
        path = BACKEND_ROOT / rel
        if not path.is_file():
            ablated[f"<missing:{rel}>"] = "family file missing from this checkout"
            continue
        source = ablate_source(path.read_text(encoding="utf-8"))
        for qualname, finding in catalog_source(source, rel).items():
            ablated[f"{rel}::{qualname}"] = finding
    return ablated


_FIXED_CATALOG = _catalog(FIXED)
_ABLATED_CATALOG = _catalog(ABLATED)

# The functions whose alignment the helper names carry: the only verdicts
# allowed to flip under ablation. Anything else flipping means a hidden
# alignment dependence the contract below fails on.
EXPECTED_ABLATED_FLIPS = frozenset({"utils/batch_pipeline/pump.py::Pump._restrike_publication"})


def ablated_findings() -> dict:
    """The ABLATED posture's findings: {rel::qualname: message}."""
    return {key: finding for key, finding in _ABLATED_CATALOG.items() if finding}


def fixed_findings() -> dict:
    """The FIXED posture's findings: the contract is that this is empty."""
    return {key: finding for key, finding in _FIXED_CATALOG.items() if finding}


def finding_for(posture: str, module: str, qualname: str):
    """One function's verdict in one posture (None = clean)."""
    key = f"{module}::{qualname}"
    catalog = _FIXED_CATALOG if posture == FIXED else _ABLATED_CATALOG
    return catalog.get(key)


def inventory():
    """Every judged (module, qualname) pair, sorted -- the grid's cell list."""
    keys = set(_FIXED_CATALOG) | set(_ABLATED_CATALOG)
    return sorted(key.split("::", 1) for key in keys if not key.startswith("<"))
