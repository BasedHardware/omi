from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from omi.bluetooth import main, print_devices


def test_print_devices_preserves_human_readable_output() -> None:
    devices = [SimpleNamespace(name="Omi", address="AA:BB")]
    with (
        patch("omi.bluetooth.BleakScanner.discover", return_value=devices) as discover,
        patch("builtins.print") as output,
    ):
        print_devices()

    discover.assert_called_once_with(timeout=5.0)
    output.assert_called_once_with("0. Omi [AA:BB]")


def test_cli_json_output_is_a_clean_array_and_forwards_timeout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    devices = [
        SimpleNamespace(name="Omi", address="AA:BB"),
        SimpleNamespace(name=None, address="CC:DD"),
    ]
    with (
        patch("omi.bluetooth.BleakScanner.discover", return_value=devices) as discover,
        patch("sys.argv", ["omi-scan", "--json", "--timeout", "3"]),
    ):
        main()

    discover.assert_called_once_with(timeout=3.0)
    assert json.loads(capsys.readouterr().out) == [
        {"name": "Omi", "address": "AA:BB"},
        {"name": None, "address": "CC:DD"},
    ]


def test_cli_json_empty_scan_prints_empty_array(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch("omi.bluetooth.BleakScanner.discover", return_value=[]),
        patch("sys.argv", ["omi-scan", "--json"]),
    ):
        main()

    assert capsys.readouterr().out == "[]\n"


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_cli_rejects_invalid_timeout(value: str) -> None:
    with (
        patch("sys.argv", ["omi-scan", "--timeout", value]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 2


def test_cli_propagates_adapter_errors() -> None:
    with (
        patch(
            "omi.bluetooth.BleakScanner.discover",
            side_effect=RuntimeError("adapter unavailable"),
        ),
        patch("sys.argv", ["omi-scan"]),
        pytest.raises(RuntimeError, match="adapter unavailable"),
    ):
        main()
