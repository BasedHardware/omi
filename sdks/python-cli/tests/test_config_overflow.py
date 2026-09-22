import tempfile
from pathlib import Path

import pytest

from omi_cli import config as cfg

@pytest.mark.parametrize(
    "large_int",
    [
        int("9" * 400),   # positive oversized integer
        -int("9" * 400),  # negative oversized integer
    ],
)
def test_overflow_expiry_value(large_int):
    """
    An oversized integer for `id_token_expires_at` should not raise
    `OverflowError`.  Instead, the configuration should load with a
    `load_error` set and contain no data.
    """
    path = Path(tempfile.mkdtemp()) / "config.toml"
    path.write_text(
        f"[profiles.default]\nid_token_expires_at = {large_int}\n",
        encoding="utf-8",
    )
    cfg_obj = cfg.load(path)
    assert cfg_obj.load_error is not None
    assert cfg_obj.data == {}

def test_valid_expiry_value():
    """
    A normal integer expiry should load successfully.
    """
    path = Path(tempfile.mkdtemp()) / "config.toml"
    path.write_text(
        "[profiles.default]\nid_token_expires_at = 123456\n",
        encoding="utf-8",
    )
    cfg_obj = cfg.load(path)
    assert cfg_obj.load_error is None
    assert cfg_obj.data["profiles"]["default"]["id_token_expires_at"] == 123456
