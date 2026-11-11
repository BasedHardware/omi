"""Discover the protected C10 oracle in the real backend's existing E2E lane."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/dev-harness'))
sys.path.insert(0, str(ROOT / 'scripts/dev-harness/tests'))
from spine.c10_backend_contract import (  # noqa: E402,F401
    test_backend_break_is_not_hidden_by_canned_success,
    test_released_decoders_read_real_router_responses,
)
