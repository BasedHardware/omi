"""Guard: every tiktoken encoding production code requests must be baked into the image.

WHY: the on-prem runtime is hermetic (ADR-0001/ADR-0035, D32) — the `omi` network has no egress,
so tiktoken cannot fetch a BPE encoding from openaipublic.blob.core.windows.net on first use; it
raises. backend/Dockerfile pre-bakes exactly ``scripts.prewarm_tiktoken_cache.BAKED_ENCODINGS`` at
build time. If a future call site requests an encoding (directly via ``get_encoding`` or indirectly
via ``encoding_for_model``) that is not in that set, review would pass and the runtime would break on
first use. This test parses production code statically and asserts the baked set covers every
statically-resolvable encoding it requests, so the hermetic guarantee cannot silently drift.

The runtime-image contract test stubs ``tiktoken.encoding_for_model`` and so cannot catch this.
Model→encoding is resolved through tiktoken's own static maps (no encoding is loaded → no network).
"""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.prewarm_tiktoken_cache import BAKED_ENCODINGS

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Production trees only — tests/testing/scripts are not part of the deployed runtime image.
PROD_DIRS = ("utils", "routers", "jobs", "database", "config", "models")

_ENCODING_FNS = frozenset({"get_encoding", "encoding_for_model"})


def _real_model_encoding_maps() -> tuple[dict, dict]:
    """Read tiktoken's real model→encoding maps, bypassing tests/conftest.py's tiktoken stub.

    conftest installs a bare ``tiktoken`` ModuleType (only ``encoding_for_model``) with no ``.model``
    submodule, so we temporarily evict it, import the real package to copy its data maps, then restore
    the stub so the rest of the process (e.g. the single-process-safe subset) sees the same state."""
    import importlib
    import sys

    keys = [m for m in list(sys.modules) if m == "tiktoken" or m.startswith("tiktoken.")]
    saved = {k: sys.modules.pop(k) for k in keys}
    try:
        model_mod = importlib.import_module("tiktoken.model")
        return dict(model_mod.MODEL_TO_ENCODING), dict(model_mod.MODEL_PREFIX_TO_ENCODING)
    finally:
        for k in [m for m in list(sys.modules) if m == "tiktoken" or m.startswith("tiktoken.")]:
            del sys.modules[k]
        sys.modules.update(saved)


def _encoding_name_for_model(model: str, model_to_encoding: dict, prefix_to_encoding: dict) -> str:
    """Resolve a model id to its encoding name via tiktoken's static maps (no encoding load, no network)."""
    if model in model_to_encoding:
        return model_to_encoding[model]
    for prefix, encoding in prefix_to_encoding.items():
        if model.startswith(prefix):
            return encoding
    raise KeyError(f"tiktoken has no encoding mapping for model {model!r}")


def _is_tiktoken_call(func: ast.expr) -> str | None:
    """Return the encoding-fn name if this call is tiktoken.get_encoding/encoding_for_model."""
    # tiktoken.get_encoding(...) / tiktoken.encoding_for_model(...)
    if isinstance(func, ast.Attribute) and func.attr in _ENCODING_FNS:
        return func.attr
    # bare get_encoding(...) after `from tiktoken import get_encoding`
    if isinstance(func, ast.Name) and func.id in _ENCODING_FNS:
        return func.id
    return None


def _referenced_encodings() -> tuple[set[str], list[str]]:
    """Return (statically-resolved encodings, call sites with a non-literal arg we could not resolve)."""
    encodings: set[str] = set()
    dynamic: list[str] = []
    model_to_encoding, prefix_to_encoding = _real_model_encoding_maps()
    for tree_dir in PROD_DIRS:
        for path in sorted((BACKEND_DIR / tree_dir).rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if not isinstance(node, ast.Call):
                    continue
                fn = _is_tiktoken_call(node.func)
                if fn is None or not node.args:
                    continue
                arg = node.args[0]
                where = f"{path.relative_to(BACKEND_DIR)}:{node.lineno}"
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    dynamic.append(f"{where} ({fn} with a non-literal argument)")
                    continue
                if fn == "get_encoding":
                    encodings.add(arg.value)
                else:
                    encodings.add(_encoding_name_for_model(arg.value, model_to_encoding, prefix_to_encoding))
    return encodings, dynamic


def test_tiktoken_baked_encodings_cover_usage():
    referenced, dynamic = _referenced_encodings()
    # A literal call site is expected — if this drops to zero the scan is broken, not the code clean.
    assert referenced, "no tiktoken get_encoding/encoding_for_model literal call sites found in production code"
    missing = referenced - set(BAKED_ENCODINGS)
    assert not missing, (
        "production code requests tiktoken encodings that backend/Dockerfile does not bake "
        f"(hermetic on-prem runtime would fail on first use): {sorted(missing)}; "
        f"BAKED_ENCODINGS={BAKED_ENCODINGS}. Add them to BAKED_ENCODINGS in "
        "scripts/prewarm_tiktoken_cache.py.\n"
        f"Call sites with a non-literal encoding argument (not statically verifiable): {dynamic}"
    )
