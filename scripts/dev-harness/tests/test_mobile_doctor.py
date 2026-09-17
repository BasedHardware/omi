from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import mobile_doctor as md

REPO_ROOT = Path(__file__).resolve().parents[3]


class FakeRunner(md.Runner):
    """Scripted probe results; path existence comes from a dict of fakes."""

    def __init__(
        self,
        outputs: dict[tuple[str, ...], tuple[int, str]] | None = None,
        which_results: dict[str, str | None] | None = None,
        paths: set[Path] | None = None,
        free_bytes: int = 20 * 1000**3,
    ) -> None:
        self.outputs = outputs or {}
        self.which_results = which_results or {}
        self.paths = paths or set()
        self._free_bytes = free_bytes

    def run(self, command: Sequence[str], timeout: float = 15.0) -> tuple[int, str]:
        return self.outputs.get(tuple(command), (0, ""))

    def which(self, name: str) -> str | None:
        return self.which_results.get(name)

    def exists(self, path: Path) -> bool:
        return Path(path) in self.paths

    def free_bytes(self, path: Path) -> int:
        return self._free_bytes


def _provisioned_runner(tmp_path: Path, *, flutter_version: str | None = "3.44.5") -> FakeRunner:
    workflow = tmp_path / ".github" / "workflows" / "mobile-app-checks.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("jobs:\n  build:\n    steps:\n      - flutter-version: 3.44.5\n", "utf-8")
    venv = tmp_path / "backend" / ".venv" / "bin" / "python"
    return FakeRunner(
        outputs={
            ("git", "-C", str(tmp_path), "rev-parse", "--is-inside-work-tree"): (0, "true\n"),
            ("python3.11", "--version"): (0, "Python 3.11.15\n"),
            (str(venv), "--version"): (0, "Python 3.11.15\n"),
            ("/opt/flutter/bin/flutter", "--version"): (0, f"Flutter {flutter_version} • channel stable\n"),
            ("java", "-version"): (0, 'openjdk version "21.0.2" 2024-01-16\n'),
            ("/usr/local/bin/firebase", "--version"): (0, "15.29.0\n"),
            ("/usr/local/bin/docker", "info", "--format", "{{.ServerVersion}}"): (0, "29.4.0\n"),
            ("xcrun", "simctl", "list", "runtimes"): (0, "iOS 26.5 (com.apple.core.simulator.simruntime.iOS-26-5)\n"),
            ("/usr/bin/xcodebuild", "-version"): (0, "Xcode 26.6\nBuild version 26.6\n"),
        },
        which_results={
            "flutter": "/opt/flutter/bin/flutter" if flutter_version else None,
            "firebase": "/usr/local/bin/firebase",
            "redis-server": "/opt/homebrew/bin/redis-server",
            "docker": "/usr/local/bin/docker",
            "xcodebuild": "/usr/bin/xcodebuild",
        },
        paths={venv},
    )


class TestOverallClassification:
    def test_fully_provisioned_host_is_ready_on_the_backend_lane(self, tmp_path: Path) -> None:
        report = md.run_doctor(tmp_path, env={}, runner=_provisioned_runner(tmp_path))
        assert report.overall == "ready", [c.as_dict() for c in report.checks]

    def test_missing_flutter_is_agent_remediable_and_names_the_pin(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path, flutter_version=None)
        report = md.run_doctor(tmp_path, runner=runner, platforms=("android",), skip_capacity=True)
        flutter = next(c for c in report.checks if c.check == "flutter")
        assert flutter.status == md.AGENT_REMEDIABLE
        assert md.flutter_pin(REPO_ROOT) in flutter.remedy
        assert report.overall == "degraded"

    def test_wrong_flutter_version_is_remediable_not_ready(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path, flutter_version="3.35.1")
        report = md.run_doctor(tmp_path, runner=runner, env={})
        flutter = next(c for c in report.checks if c.check == "flutter")
        assert flutter.status == md.AGENT_REMEDIABLE
        assert "pin" in flutter.remedy

    def test_operator_gate_blocks_the_whole_report(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        runner.which_results["xcodebuild"] = None
        report = md.run_doctor(tmp_path, runner=runner, platforms=("ios",))
        assert report.overall == "blocked"
        xcode = next(c for c in report.checks if c.check == "xcode")
        assert xcode.status == md.OPERATOR

    def test_backend_lane_ignores_device_only_failures(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        runner.which_results["xcodebuild"] = None
        report = md.run_doctor(tmp_path, env={}, runner=runner, platforms=())
        assert all(c.check != "xcode" for c in report.checks)
        assert report.overall == "ready"

    def test_ios_simulator_is_an_alias_for_the_ios_lane(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        runner.which_results["xcodebuild"] = None
        report = md.run_doctor(tmp_path, runner=runner, platforms=("ios-simulator",), skip_capacity=True)
        xcode = next(c for c in report.checks if c.check == "xcode")
        assert xcode.status == md.OPERATOR
        assert xcode.lanes == (md.LANE_IOS,)

    def test_unknown_platform_is_refused_with_valid_values(self, tmp_path: Path) -> None:
        with pytest.raises(md.DoctorError, match="ios-simulator is an alias for ios"):
            md.run_doctor(tmp_path, platforms=("iphone",))


class TestIndividualChecks:
    def test_capacity_below_threshold_is_an_operator_gate(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        runner._free_bytes = int(5 * 1000**3)
        report = md.run_doctor(tmp_path, runner=runner, platforms=("android",))
        capacity = next(c for c in report.checks if c.check == "disk-capacity")
        assert capacity.status == md.OPERATOR
        assert "not delete unrelated" in capacity.remedy
        assert report.overall == "blocked"

    def test_capacity_check_can_be_skipped_for_contract_lanes(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        runner._free_bytes = int(1 * 1000**3)
        sdk = tmp_path / "android-sdk"
        sdkmanager = sdk / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
        runner.paths.update({sdk, sdk / "emulator" / "emulator", sdkmanager, sdk / "platform-tools" / "adb"})
        runner.outputs[(str(sdkmanager), "--list_installed")] = (0, "system-images;android-36;google_apis;arm64-v8a\n")
        report = md.run_doctor(
            tmp_path, env={"ANDROID_HOME": str(sdk)}, runner=runner, platforms=("android",), skip_capacity=True
        )
        assert all(c.check != "disk-capacity" for c in report.checks)
        assert report.overall == "ready"

    def test_docker_daemon_down_with_no_native_typesense_is_operator(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        runner.outputs[("/usr/local/bin/docker", "info", "--format", "{{.ServerVersion}}")] = (
            1,
            "Cannot connect to the Docker daemon",
        )
        runner.which_results["docker"] = "/usr/local/bin/docker"
        report = md.run_doctor(tmp_path, runner=runner, env={})
        typesense = next(c for c in report.checks if c.check == "typesense")
        assert typesense.status == md.OPERATOR

    def test_production_api_override_in_env_is_reported(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        report = md.run_doctor(tmp_path, env={"OMI_LOCAL_API_BASE_URL": "https://api.omi.me/"}, runner=runner)
        egress = next(c for c in report.checks if c.check == "egress-env")
        assert egress.status == md.OPERATOR

    def test_android_sdk_without_env_is_remediable(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        report = md.run_doctor(tmp_path, runner=runner, platforms=("android",), skip_capacity=True)
        sdk = next(c for c in report.checks if c.check == "android-sdk")
        assert sdk.status == md.AGENT_REMEDIABLE
        assert "ANDROID_HOME" in sdk.remedy

    def test_android_image_missing_names_the_exact_package(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        sdk = tmp_path / "android-sdk"
        emulator = sdk / "emulator" / "emulator"
        sdkmanager = sdk / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
        adb = sdk / "platform-tools" / "adb"
        runner.paths.update({sdk, emulator, sdkmanager, adb})
        runner.outputs[(str(sdkmanager), "--list_installed")] = (0, "platform-tools\nplatforms;android-36\n")
        report = md.run_doctor(
            tmp_path,
            env={"ANDROID_HOME": str(sdk)},
            runner=runner,
            platforms=("android",),
            skip_capacity=True,
        )
        image = next(c for c in report.checks if c.check == "android-image")
        assert image.status == md.AGENT_REMEDIABLE
        assert "system-images;android-36;google_apis;arm64-v8a" in image.remedy
        assert "capacity-gated" in image.remedy

    def test_android_image_on_disk_is_ready_even_when_sdkmanager_omits_it(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        sdk = tmp_path / "android-sdk"
        image = sdk / "system-images" / "android-36" / "google_apis" / "arm64-v8a"
        sdkmanager = sdk / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
        runner.paths.update(
            {sdk, sdk / "emulator" / "emulator", sdkmanager, sdk / "platform-tools" / "adb", image}
        )
        runner.outputs[(str(sdkmanager), "--list_installed")] = (0, "platform-tools\nplatforms;android-36\n")
        report = md.run_doctor(
            tmp_path,
            env={"ANDROID_HOME": str(sdk)},
            runner=runner,
            platforms=("android",),
            skip_capacity=True,
        )
        check = next(c for c in report.checks if c.check == "android-image")
        assert check.status == md.READY
        assert "system-images;android-36;google_apis;arm64-v8a" in check.detail

    def test_android_image_slash_list_installed_is_ready(self, tmp_path: Path) -> None:
        runner = _provisioned_runner(tmp_path)
        sdk = tmp_path / "android-sdk"
        sdkmanager = sdk / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
        runner.paths.update({sdk, sdk / "emulator" / "emulator", sdkmanager, sdk / "platform-tools" / "adb"})
        runner.outputs[(str(sdkmanager), "--list_installed")] = (
            0,
            "system-images/android-36/google_apis/arm64-v8a         7.0.0            Google APIs ARM 64 v8a System Image\n",
        )
        report = md.run_doctor(
            tmp_path,
            env={"ANDROID_HOME": str(sdk)},
            runner=runner,
            platforms=("android",),
            skip_capacity=True,
        )
        check = next(c for c in report.checks if c.check == "android-image")
        assert check.status == md.READY
        assert "system-images;android-36;google_apis;arm64-v8a" in check.detail


class TestFlutterPin:
    def test_pin_comes_from_the_repo_workflow(self) -> None:
        pin = md.flutter_pin(REPO_ROOT)
        assert pin is not None
        assert pin.count(".") == 2  # a real x.y.z pin, not "latest"

    def test_inconsistent_pins_are_refused_rather_than_guessed(self, tmp_path: Path) -> None:
        workflow = tmp_path / ".github" / "workflows" / "mobile-app-checks.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("a: flutter-version: 3.44.5\nb: flutter-version: 3.50.0\n", "utf-8")
        assert md.flutter_pin(tmp_path) is None
