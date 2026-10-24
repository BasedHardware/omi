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

    discover.assert_called_once_with()
    output.assert_called_once_with("0. Omi [AA:BB]")


def test_print_devices_json_output_reports_name_and_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    devices = [SimpleNamespace(name="Omi", address="AA:BB")]
    with patch("omi.bluetooth.BleakScanner.discover", return_value=devices):
        print_devices(json_output=True)

    assert json.loads(capsys.readouterr().out) == [{"name": "Omi", "id": "AA:BB"}]


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
        exit_code = main()

    discover.assert_called_once_with(timeout=3.0)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == [
        {"name": "Omi", "id": "AA:BB"},
        {"name": None, "id": "CC:DD"},
    ]
    assert captured.err == ""


def test_cli_json_empty_scan_prints_empty_array(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch("omi.bluetooth.BleakScanner.discover", return_value=[]),
        patch("sys.argv", ["omi-scan", "--json"]),
    ):
        exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "[]\n"


def test_cli_without_timeout_defers_to_bleak_default() -> None:
    with (
        patch("omi.bluetooth.BleakScanner.discover", return_value=[]) as discover,
        patch("sys.argv", ["omi-scan"]),
    ):
        main()

    discover.assert_called_once_with()


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf", "abc"])
def test_cli_rejects_invalid_timeout_before_scanning(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with (
        patch("omi.bluetooth.BleakScanner.discover") as discover,
        patch("sys.argv", ["omi-scan", "--timeout", value]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 2
    discover.assert_not_called()
    assert capsys.readouterr().out == ""


def test_cli_reports_adapter_failure_on_stderr_and_exits_nonzero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch(
            "omi.bluetooth.BleakScanner.discover",
            side_effect=RuntimeError("adapter unavailable"),
        ),
        patch("sys.argv", ["omi-scan", "--json"]),
    ):
        exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "adapter unavailable" in captured.err
