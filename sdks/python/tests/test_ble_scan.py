"""Hermetic tests for the ``omi-scan`` CLI (JSON output + configurable timeout).

No physical adapter is required: ``BleakScanner.discover`` is mocked in every
test, so this suite runs in CI with no Bluetooth hardware or network access.
"""

import asyncio
import json
import math
from unittest import mock

import pytest

from omi import bluetooth


class FakeDevice:
    """Minimal stand-in for bleak's BLEDevice."""

    def __init__(self, name, address):
        self.name = name
        self.address = address


def patch_discover(result=None, exc=None, timeout_capture=None):
    """Replace BleakScanner.discover with a hermetic stand-in.

    Mirrors bleak's ``discover(timeout=5.0, return_adv=False, scanning_mode=...)``
    signature. ``timeout_capture`` (a list) records the timeout each call got.
    """

    async def fake_discover(timeout=5.0, **kwargs):
        if timeout_capture is not None:
            timeout_capture.append(timeout)
        if exc is not None:
            raise exc
        return result if result is not None else []

    return mock.patch.object(bluetooth.BleakScanner, "discover", new=fake_discover)


# --- Discovery results -------------------------------------------------------


def test_human_listing_named_devices(capsys):
    with patch_discover(result=[FakeDevice("Omi", "AA:BB:CC:DD:EE:FF"), FakeDevice("Phone", "11:22:33:44:55:66")]):
        rc = bluetooth.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == "0. Omi [AA:BB:CC:DD:EE:FF]\n1. Phone [11:22:33:44:55:66]\n"


def test_json_output_named_devices(capsys):
    with patch_discover(result=[FakeDevice("Omi", "AA:BB:CC:DD:EE:FF"), FakeDevice("Phone", "11:22:33:44:55:66")]):
        rc = bluetooth.main(["--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out) == [
        {"name": "Omi", "id": "AA:BB:CC:DD:EE:FF"},
        {"name": "Phone", "id": "11:22:33:44:55:66"},
    ]


def test_json_output_unnamed_device_uses_null(capsys):
    with patch_discover(result=[FakeDevice(None, "AA:BB:CC:DD:EE:FF")]):
        rc = bluetooth.main(["--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out) == [{"name": None, "id": "AA:BB:CC:DD:EE:FF"}]


def test_human_listing_unnamed_device(capsys):
    with patch_discover(result=[FakeDevice(None, "AA:BB:CC:DD:EE:FF")]):
        rc = bluetooth.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == "0. None [AA:BB:CC:DD:EE:FF]\n"


def test_empty_scan_emits_empty_json_array(capsys):
    with patch_discover(result=[]):
        rc = bluetooth.main(["--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out) == []
    assert out.strip() == "[]"


def test_empty_scan_human_listing_is_quiet(capsys):
    with patch_discover(result=[]):
        rc = bluetooth.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == ""


# --- Timeout forwarding ------------------------------------------------------


def test_timeout_forwarded_to_bleak():
    capture = []
    with patch_discover(result=[], timeout_capture=capture):
        rc = bluetooth.main(["--timeout", "3"])
    assert rc == 0
    assert capture == [3.0]


def test_timeout_float_values_forwarded():
    capture = []
    with patch_discover(result=[], timeout_capture=capture):
        rc = bluetooth.main(["--timeout", "0.5"])
    assert rc == 0
    assert capture == [0.5]


def test_default_timeout_keeps_bleak_default():
    capture = []
    with patch_discover(result=[], timeout_capture=capture):
        rc = bluetooth.main([])
    assert rc == 0
    # No explicit timeout passed -> Bleak's own default applies.
    assert capture == [5.0]


# --- Invalid arguments -------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["-1", "0", "nan", "inf", "-inf", "abc"],
)
def test_invalid_timeout_rejected_before_scan(capsys, bad):
    capture = []
    with patch_discover(result=[], timeout_capture=capture):
        with pytest.raises(SystemExit) as exc:
            bluetooth.main(["--timeout", bad])
    assert exc.value.code == 2
    # Discovery never ran: the timeout was rejected before any scan.
    assert capture == []
    assert capsys.readouterr().out == ""


def test_unknown_flag_rejected():
    capture = []
    with patch_discover(result=[], timeout_capture=capture):
        with pytest.raises(SystemExit) as exc:
            bluetooth.main(["--bogus"])
    assert exc.value.code == 2
    assert capture == []


# --- Adapter failures --------------------------------------------------------


def test_adapter_failure_returns_nonzero_and_stays_off_stdout(capsys):
    with patch_discover(exc=OSError("Bluetooth adapter not found")):
        rc = bluetooth.main(["--json"])
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""  # no partial/diagnostic JSON on stdout
    assert "Bluetooth scan failed" in captured.err
    assert "Bluetooth adapter not found" in captured.err


# --- Preserved callable behavior --------------------------------------------


def test_print_devices_callable_preserved(capsys):
    with patch_discover(result=[FakeDevice("Omi", "AA:BB:CC:DD:EE:FF")]):
        bluetooth.print_devices()
    assert capsys.readouterr().out == "0. Omi [AA:BB:CC:DD:EE:FF]\n"


def test_print_devices_accepts_timeout_argument():
    capture = []
    with patch_discover(result=[], timeout_capture=capture):
        bluetooth.print_devices(timeout=2.0)
    assert capture == [2.0]


def test_devices_to_json_is_deterministic():
    payload = bluetooth.devices_to_json([FakeDevice("Omi", "AA:BB:CC:DD:EE:FF")])
    assert json.loads(payload) == [{"name": "Omi", "id": "AA:BB:CC:DD:EE:FF"}]
