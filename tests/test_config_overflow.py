import tempfile
from pathlib import Path

import pytest

from omi_cli import config as cfg


def _create_overflow_config(value: int) -> Path:
    """
    Helper that writes a config file containing an oversized integer
    for the `id_token_expires_at` field and returns the path.
    """
    tmp_dir = Path(tempfile.mkdtemp())
    cfg_path = tmp_dir / "config.toml"
    cfg_path.write_text(
        f"[profiles.default]\nid_token_expires_at = {value}\n",
        encoding="utf-8",
    )
    return cfg_path


@pytest.mark.parametrize(
    "overflow_value",
    [
        int("9" * 400),  # positive oversized integer
        -int("9" * 400),  # negative oversized integer
    ],
)
def test_overflow_expiry_does_not_crash(overflow_value: int):
    """
    Loading a config with an oversized `id_token_expires_at` should not raise
    an exception but instead set `load_error` on the Config instance.
    """
    cfg_path = _create_overflow_config(overflow_value)
    loaded_cfg = cfg.load(cfg_path)

    # The load should succeed but report an error
    assert loaded_cfg.load_error is not None
    assert "id_token_expires_at" in loaded_cfg.load_error

    # The original data should still be available for diagnostics
    assert "profiles" in loaded_cfg.data
    assert "default" in loaded_cfg.data["profiles"]
    assert loaded_cfg.data["profiles"]["default"]["id_token_expires_at"] == overflow_value


def test_save_refuses_overflow_config(tmp_path: Path):
    """
    Attempting to save a configuration that failed to load due to an
    oversized expiry should raise a RuntimeError.
    """
    cfg_path = _create_overflow_config(int("9" * 400))
    loaded_cfg = cfg.load(cfg_path)

    with pytest.raises(RuntimeError, match="Cannot save configuration"):
        loaded_cfg.save(tmp_path / "new_config.toml")
