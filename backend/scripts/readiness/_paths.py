from __future__ import annotations

from pathlib import Path

READINESS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = READINESS_DIR.parents[1]
GATES_DIR = READINESS_DIR / "gates"
REGISTRIES_DIR = READINESS_DIR / "registries"
MANIFEST_PATH = READINESS_DIR / "manifest.json"
HANDLERS_DIR = READINESS_DIR / "handlers"
