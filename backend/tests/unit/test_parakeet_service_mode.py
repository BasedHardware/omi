"""Behavioral tests for the shared Parakeet image's serving-mode contract."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

SERVICE_MODE = Path(__file__).resolve().parents[2] / "parakeet" / "service_mode.py"


@pytest.fixture
def mode():
    return runpy.run_path(str(SERVICE_MODE))


@pytest.mark.parametrize(
    ("env", "expected"),
    [({}, "mixed"), ({"PARAKEET_SERVICE_MODE": "BATCH"}, "batch"), ({"PARAKEET_SERVICE_MODE": " stream "}, "stream")],
)
def test_mode_is_normalized_and_defaults_to_legacy_mixed(mode, env, expected):
    assert mode["get_service_mode"](env) == expected


def test_unknown_mode_fails_closed(mode):
    with pytest.raises(ValueError, match="PARAKEET_SERVICE_MODE"):
        mode["get_service_mode"]({"PARAKEET_SERVICE_MODE": "gpu"})
