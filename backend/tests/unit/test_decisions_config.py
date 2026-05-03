"""Unit tests for the Decisions dogfood allowlist parsing.

`utils.decisions._parse_uids` is the helper that reads the
`DECISIONS_DOGFOOD_UIDS` env var format. Tests target the helper directly so
we don't have to reload modules.
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.decisions import _parse_uids  # noqa: E402


def test_unset_env_returns_empty_set():
    assert _parse_uids("") == set()


def test_single_uid_parsed():
    assert _parse_uids("uid1") == {"uid1"}


def test_multiple_uids_with_whitespace_trimmed():
    assert _parse_uids("uid1,uid2,uid3") == {"uid1", "uid2", "uid3"}
    assert _parse_uids(" uid1 , uid2 ,uid3 ") == {"uid1", "uid2", "uid3"}


def test_empty_segments_dropped():
    assert _parse_uids("uid1,,uid2,") == {"uid1", "uid2"}
