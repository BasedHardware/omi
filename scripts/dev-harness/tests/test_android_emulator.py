"""Hermetic session-owned AVD attach/detach. No real emulator/adb."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import fixture_audio as fa
from dev_harness import mobile_session as ms

REPO_ROOT = Path(__file__).resolve().parents[3]


def _sdk(tmp_path: Path) -> Path:
    home = tmp_path / "android-sdk"
    (home / "emulator").mkdir(parents=True, exist_ok=True)
    (home / "emulator" / "emulator").write_text("emu\n", encoding="utf-8")
    (home / "platform-tools").mkdir(exist_ok=True)
    (home / "platform-tools" / "adb").write_text("adb\n", encoding="utf-8")
    tools = home / "cmdline-tools" / "latest" / "bin"
    tools.mkdir(parents=True, exist_ok=True)
    (tools / "avdmanager").write_text("avd\n", encoding="utf-8")
    (tools / "sdkmanager").write_text("sdk\n", encoding="utf-8")
    image = home.joinpath(*ms.mobile_doctor.PREFERRED_ANDROID_IMAGE_DIR)
    image.mkdir(parents=True, exist_ok=True)
    (image / "kernel-ranchu").write_text("k\n", encoding="utf-8")
    return home


class Scripted:
    def __init__(
        self,
        devices_out: str = "List of devices attached\n\n",
        boot_token: str = "1",
        avd_names: dict[str, str] | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self.devices_out = devices_out
        self.boot_token = boot_token
        self.avd_names = dict(avd_names or {})

    def __call__(self, command, timeout=120, env=None, input_text=None):
        argv = [str(part) for part in command]
        self.calls.append({"argv": argv, "env": dict(env) if env else None, "input": input_text, "timeout": timeout})
        text = " ".join(argv)
        if argv[-1:] == ["devices"] or text.endswith(" devices"):
            return 0, self.devices_out
        if "emu" in argv and argv[-1:] == ["name"]:
            serial = argv[argv.index("-s") + 1] if "-s" in argv else ""
            return 0, f"{self.avd_names.get(serial, '')}\n"
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
    avd_home = tmp_path / kwargs.get("session_id", "oms-v3") / "avd"
    spawned: list[list[str]] = []
    spawned_env: list[dict[str, str]] = []

    def spawn(command, **spawn_kwargs):
        spawned.append([str(part) for part in command])
        spawned_env.append(dict(spawn_kwargs.get("env") or {}))
        return SimpleNamespace(pid=kwargs.get("pid", 424242))

    devices = ms.DeviceController(runner=scripted)
    record = devices.attach_android_emulator(
        kwargs.get("session_id", "oms-v3"),
        str(home),
        avd_home=avd_home,
        ports=kwargs.get("ports") or {"backend": 8100, "auth": 9199, "firestore": 8185, "redis": 6479},
        log_path=tmp_path / "emulator.log",
        spawn=spawn,
        boot_timeout_s=kwargs.get("boot_timeout_s", 2),
        console_port=kwargs.get("console_port", 5554),
        repo_root=REPO_ROOT,
    )
    return devices, record, home, spawned, spawned_env, scripted


def test_attach_creates_session_avd_headless_and_reverses_session_ports(tmp_path: Path) -> None:
    scripted = Scripted()
    devices, record, home, spawned, spawned_env, _ = _attach(tmp_path, scripted)
    assert record["kind"] == "emulator"
    assert record["udid"] == "emulator-5554"
    assert record["avd"] == "omi-session-oms-v3"
    assert record["boot"] == "no-snapshot"
    assert record["audio"] == "wav"
    assert record["mic_fixture_sha256"] == "1fb553adb5a6389eef5b7ebdbf9ed2a6082518a646ce9bf872bf33b964eedc14"
    assert Path(record["avd_home"]) == tmp_path / "oms-v3" / "avd"
    assert record["reverse"] == [
        {"device": 8100, "host": 8100, "name": "backend"},
        {"device": 9199, "host": 9199, "name": "auth"},
    ]
    create = next(call for call in scripted.calls if "create" in call["argv"] and "avd" in call["argv"])
    assert create["env"]["ANDROID_AVD_HOME"] == str(tmp_path / "oms-v3" / "avd")
    assert create["env"]["ANDROID_HOME"] == str(home)
    assert ms.ANDROID_IMAGE_PACKAGE in create["argv"]
    assert create["input"] == "no\n"
    argv = spawned[0]
    assert "-m" in argv and "dev_harness.supervise" in argv
    assert any(part.startswith("omi-dev-harness:oms-v3:android-emulator:") for part in argv)
    assert argv[argv.index("-avd") + 1] == "omi-session-oms-v3"
    assert "-no-window" in argv and "-no-snapshot" in argv
    assert "-no-audio" not in argv
    assert argv[argv.index("-audio") + 1] == "wav"
    assert spawned_env[0]["QEMU_AUDIO_DRV"] == "wav"
    assert spawned_env[0]["QEMU_WAV_IN_PATH"].endswith("transcription-release-probe.wav")
    assert str(home / "cmdline-tools" / "latest" / "bin" / "avdmanager") in create["argv"]
    reverses = [call["argv"] for call in scripted.calls if "reverse" in call["argv"] and "--remove" not in call["argv"]]
    assert [row[-2:] for row in reverses] == [["tcp:8100", "tcp:8100"], ["tcp:9199", "tcp:9199"]]


def test_attach_ignores_a_physical_phone(tmp_path: Path) -> None:
    scripted = Scripted(devices_out="List of devices attached\nR58M123ABCD\tdevice\n")
    _devices, record, _home, _spawned, _env, _ = _attach(tmp_path, scripted)
    assert record["udid"] == "emulator-5554"


def test_attach_ignores_a_foreign_emulator_and_picks_a_free_serial(tmp_path: Path) -> None:
    scripted = Scripted(
        devices_out="List of devices attached\nemulator-5554\tdevice\n",
        avd_names={"emulator-5554": "Pixel_7"},
    )
    _devices, record, _home, spawned, _env, _ = _attach(tmp_path, scripted, console_port=5554)
    assert record["udid"] == "emulator-5556"
    assert spawned[0][spawned[0].index("-port") + 1] == "5556"


def test_attach_refuses_this_session_avd_still_visible(tmp_path: Path) -> None:
    scripted = Scripted(
        devices_out="List of devices attached\nemulator-5554\tdevice\n",
        avd_names={"emulator-5554": "omi-session-oms-v3"},
    )
    with pytest.raises(ms.SessionError, match="harness-owned AVD omi-session-oms-v3"):
        _attach(tmp_path, scripted)


def test_two_session_owned_avds_coexist_with_disjoint_serials_and_reverses(tmp_path: Path) -> None:
    scripted = Scripted()
    _devices_a, first, _home, _spawned_a, _env_a, _ = _attach(
        tmp_path,
        scripted,
        session_id="oms-a",
        console_port=5554,
        ports={"backend": 8100, "auth": 9199, "firestore": 8185, "redis": 6479},
    )
    scripted.devices_out = "List of devices attached\nemulator-5554\tdevice\n"
    scripted.avd_names = {"emulator-5554": "omi-session-oms-a"}
    _devices_b, second, _home_b, _spawned_b, _env_b, _ = _attach(
        tmp_path,
        scripted,
        session_id="oms-b",
        console_port=5554,
        ports={"backend": 8200, "auth": 9299, "firestore": 8285, "redis": 6579},
    )
    assert first["udid"] == "emulator-5554"
    assert second["udid"] == "emulator-5556"
    assert first["avd"] != second["avd"]
    assert first["console_port"] != second["console_port"]
    first_ports = {(row["name"], row["host"]) for row in first["reverse"]}
    second_ports = {(row["name"], row["host"]) for row in second["reverse"]}
    assert first_ports.isdisjoint(second_ports)
    assert first_ports == {("backend", 8100), ("auth", 9199)}
    assert second_ports == {("backend", 8200), ("auth", 9299)}


def test_boot_wait_is_bounded(tmp_path: Path) -> None:
    scripted = Scripted(boot_token="")
    with pytest.raises(ms.SessionError, match="sys.boot_completed"):
        _attach(tmp_path, scripted, boot_timeout_s=0.4)


def test_detach_removes_only_recorded_reverses_and_deletes_the_avd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripted = Scripted()
    devices, record, home, _spawned, _env, _ = _attach(tmp_path, scripted)
    record["android_home"] = str(home)
    monkeypatch.setattr("dev_harness.safety.process_exists", lambda pid: False)
    devices.detach("android", record["udid"], device=record)
    removes = [call["argv"] for call in scripted.calls if "reverse" in call["argv"] and "--remove" in call["argv"]]
    assert removes == [
        [str(home / "platform-tools" / "adb"), "-s", "emulator-5554", "reverse", "--remove", "tcp:8100"],
        [str(home / "platform-tools" / "adb"), "-s", "emulator-5554", "reverse", "--remove", "tcp:9199"],
    ]
    deleted = next(call for call in scripted.calls if "delete" in call["argv"] and "avd" in call["argv"])
    assert "omi-session-oms-v3" in deleted["argv"]
    assert deleted["env"]["ANDROID_AVD_HOME"] == str(tmp_path / "oms-v3" / "avd")


def test_failed_kill_does_not_delete_the_avd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scripted = Scripted()
    devices, record, home, _spawned, _env, _ = _attach(tmp_path, scripted)
    record["android_home"] = str(home)
    monkeypatch.setattr("dev_harness.safety.process_exists", lambda pid: True)
    monkeypatch.setattr("dev_harness.safety.command_line_for_pid", lambda pid: "qemu-system foreign")
    before = [call for call in scripted.calls if "delete" in call["argv"] and "avd" in call["argv"]]
    with pytest.raises(ms.SessionError, match="ownership marker"):
        devices.detach("android", record["udid"], device=record)
    after = [call for call in scripted.calls if "delete" in call["argv"] and "avd" in call["argv"]]
    assert after == before


def test_sdk_cli_tool_never_uses_homebrew_avdmanager(tmp_path: Path) -> None:
    home = _sdk(tmp_path)
    assert ms._sdk_cli_tool(home, "avdmanager") == home / "cmdline-tools" / "latest" / "bin" / "avdmanager"


def test_wav_backend_receipt_is_platform_mic_only_with_content_evidence() -> None:
    fixture = fa.load_known_audio_fixture(REPO_ROOT)
    fa.refuse_platform_mic_without_host_audio(False)
    ok = {
        "fixture_audio": {
            "injection_kind": fa.INJECTION_PLATFORM_MIC,
            "fixture_sha256": fixture.sha256,
            "heard": True,
            "content_evidence": fa.CONTENT_EVIDENCE_CAPTURED_PCM,
            "platform_path_proven": True,
            "stt_ran": False,
        }
    }
    assert fa.validate_injection_receipt(ok) == []
    argv = fa.emulator_audio_argv(audio_disabled=False)
    assert argv == ["-audio", "wav"]
    env = fa.qemu_wav_input_env(fixture.path)
    assert env["QEMU_WAV_IN_PATH"] == str(fixture.path)
