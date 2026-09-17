"""Hermetic session-owned AVD attach/detach. No real emulator/adb."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import mobile_session as ms

REPO_ROOT = Path(__file__).resolve().parents[3]


def _sdk(tmp_path: Path) -> Path:
    home = tmp_path / "android-sdk"
    (home / "emulator").mkdir(parents=True)
    (home / "emulator" / "emulator").write_text("emu\n", encoding="utf-8")
    (home / "platform-tools").mkdir()
    (home / "platform-tools" / "adb").write_text("adb\n", encoding="utf-8")
    tools = home / "cmdline-tools" / "latest" / "bin"
    tools.mkdir(parents=True)
    (tools / "avdmanager").write_text("avd\n", encoding="utf-8")
    (tools / "sdkmanager").write_text("sdk\n", encoding="utf-8")
    image = home.joinpath(*ms.mobile_doctor.PREFERRED_ANDROID_IMAGE_DIR)
    image.mkdir(parents=True)
    (image / "kernel-ranchu").write_text("k\n", encoding="utf-8")
    return home


class Scripted:
    def __init__(self, devices_out: str = "List of devices attached\n\n", boot_token: str = "1") -> None:
        self.calls: list[dict] = []
        self.devices_out = devices_out
        self.boot_token = boot_token

    def __call__(self, command, timeout=120, env=None, input_text=None):
        argv = [str(part) for part in command]
        self.calls.append({"argv": argv, "env": dict(env) if env else None, "input": input_text, "timeout": timeout})
        text = " ".join(argv)
        if argv[-1:] == ["devices"] or text.endswith(" devices"):
            return 0, self.devices_out
        if "wait-for-device" in argv:
            return 0, ""
        if "getprop" in argv:
            return (0, f"{self.boot_token}\n") if self.boot_token else (0, "0\n")
        if "reverse" in argv:
            return 0, ""
        if "create" in argv and "avd" in argv:
            return 0, "created\n"
        if "delete" in argv and "avd" in argv:
            return 0, "deleted\n"
        return 0, ""


def _attach(tmp_path: Path, scripted: Scripted, **kwargs):
    home = _sdk(tmp_path)
    avd_home = tmp_path / "session" / "avd"
    spawned: list[list[str]] = []

    def spawn(command, **_kwargs):
        spawned.append([str(part) for part in command])
        return SimpleNamespace(pid=424242)

    devices = ms.DeviceController(runner=scripted)
    record = devices.attach_android_emulator(
        "oms-v3",
        str(home),
        avd_home=avd_home,
        ports={"backend": 8100, "auth": 9199, "firestore": 8185, "redis": 6479},
        log_path=tmp_path / "emulator.log",
        spawn=spawn,
        boot_timeout_s=kwargs.get("boot_timeout_s", 2),
        console_port=kwargs.get("console_port", 5554),
    )
    return devices, record, home, spawned, scripted


def test_attach_creates_session_avd_headless_and_reverses_session_ports(tmp_path: Path) -> None:
    scripted = Scripted()
    devices, record, home, spawned, _ = _attach(tmp_path, scripted)
    assert record["kind"] == "emulator"
    assert record["udid"] == "emulator-5554"
    assert record["avd"] == "omi-session-oms-v3"
    assert record["boot"] == "no-snapshot"
    assert Path(record["avd_home"]) == tmp_path / "session" / "avd"
    assert record["reverse"] == [
        {"device": 8100, "host": 8100, "name": "backend"},
        {"device": 9199, "host": 9199, "name": "auth"},
    ]
    create = next(call for call in scripted.calls if "create" in call["argv"] and "avd" in call["argv"])
    assert create["env"]["ANDROID_AVD_HOME"] == str(tmp_path / "session" / "avd")
    assert create["env"]["ANDROID_HOME"] == str(home)
    assert ms.ANDROID_IMAGE_PACKAGE in create["argv"]
    assert create["input"] == "no\n"
    argv = spawned[0]
    assert "-m" in argv and "dev_harness.supervise" in argv
    assert any(part.startswith("omi-dev-harness:oms-v3:android-emulator:") for part in argv)
    assert argv[argv.index("-avd") + 1] == "omi-session-oms-v3"
    assert "-no-window" in argv and "-no-audio" in argv and "-no-snapshot" in argv
    assert str(home / "cmdline-tools" / "latest" / "bin" / "avdmanager") in create["argv"]
    reverses = [call["argv"] for call in scripted.calls if "reverse" in call["argv"] and "--remove" not in call["argv"]]
    assert [row[-2:] for row in reverses] == [["tcp:8100", "tcp:8100"], ["tcp:9199", "tcp:9199"]]


def test_attach_refuses_a_second_visible_emulator(tmp_path: Path) -> None:
    scripted = Scripted(devices_out="List of devices attached\nemulator-5554\tdevice\n")
    with pytest.raises(ms.SessionError, match="one emulator at a time"):
        _attach(tmp_path, scripted)


def test_boot_wait_is_bounded(tmp_path: Path) -> None:
    scripted = Scripted(boot_token="")
    with pytest.raises(ms.SessionError, match="sys.boot_completed"):
        _attach(tmp_path, scripted, boot_timeout_s=0.4)


def test_detach_removes_only_recorded_reverses_and_deletes_the_avd(tmp_path: Path) -> None:
    scripted = Scripted()
    devices, record, home, _spawned, _ = _attach(tmp_path, scripted)
    record["android_home"] = str(home)
    devices.detach("android", record["udid"], record)
    removes = [call["argv"] for call in scripted.calls if "reverse" in call["argv"] and "--remove" in call["argv"]]
    assert removes == [
        [str(home / "platform-tools" / "adb"), "-s", "emulator-5554", "reverse", "--remove", "tcp:8100"],
        [str(home / "platform-tools" / "adb"), "-s", "emulator-5554", "reverse", "--remove", "tcp:9199"],
    ]
    deleted = next(call for call in scripted.calls if "delete" in call["argv"] and "avd" in call["argv"])
    assert "omi-session-oms-v3" in deleted["argv"]
    assert deleted["env"]["ANDROID_AVD_HOME"] == str(tmp_path / "session" / "avd")


def test_sdk_cli_tool_never_uses_homebrew_avdmanager(tmp_path: Path) -> None:
    home = _sdk(tmp_path)
    assert ms._sdk_cli_tool(home, "avdmanager") == home / "cmdline-tools" / "latest" / "bin" / "avdmanager"
