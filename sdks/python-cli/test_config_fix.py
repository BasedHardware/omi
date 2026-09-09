"""Tests for config.load with invalid profile containers."""
import tempfile
from pathlib import Path

from omi_cli.config import load


def test_profiles_string_value():
    """profiles = 'mistake' should report load error, not crash."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('profiles = "mistake"\n')
        f.flush()
        config = load(Path(f.name))
        assert config.was_load_error
        assert "profiles" in config.load_error.lower()


def test_profiles_nested_string():
    """[profiles] default = 'mistake' should report load error."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[profiles]\ndefault = "mistake"\n')
        f.flush()
        config = load(Path(f.name))
        assert config.was_load_error
        assert "default" in config.load_error


def test_valid_profiles_still_work():
    """Valid profiles should load normally."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('[profiles.default]\napi_base = "https://api.example.com"\n')
        f.flush()
        config = load(Path(f.name))
        assert not config.was_load_error
        assert "default" in config.profiles


def test_no_profiles_section():
    """Missing profiles section should load normally."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write('active_profile = "other"\n')
        f.flush()
        config = load(Path(f.name))
        assert not config.was_load_error
        assert config.active_profile == "other"
