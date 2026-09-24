"""Build attribution regressions with fake compilers; no SDK, signing or device."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildAttributionTests(unittest.TestCase):
    def exercise(self, lane, mutate=False, commit_changes=False):
        relative = f"app/ios/test/{lane}/build.py"
        module = load("build_" + lane, relative)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            here = root / f"app/ios/test/{lane}"
            here.mkdir(parents=True)
            (here / "build.py").write_bytes((ROOT / relative).read_bytes())
            name = "Probe.swift" if lane == "phone_mic_probe" else "Driver.swift"
            source = here / name
            source.write_text("original compiler input")
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            output = root / "output"
            calls = []
            git_reads = []

            def check_output(command, **kwargs):
                if command[0] == "git":
                    git_reads.append(command)
                    return (("b" if commit_changes and len(git_reads) > 1 else "a") * 40) + "\n"
                if command[0] == "security":
                    return plistlib.dumps({"Entitlements": {"get-task-allow": True, "application-identifier": "TEAM.*"},
                                            "TeamIdentifier": ["TEAM"], "ProvisionedDevices": ["synthetic-device"]})
                if command[0] == "xcodebuild":
                    return "synthetic Xcode"
                return "/synthetic-sdk"

            def run(command, **kwargs):
                calls.append(command)
                if "swiftc" in command:
                    # The executable is bound to what the compiler read before
                    # another agent edits the source, not the later file bytes.
                    Path(command[command.index("-o") + 1]).write_bytes(source.read_bytes())
                    if mutate:
                        source.write_text("changed while compiler was running")
                return None

            overrides = {"HERE": here}
            if lane == "phone_mic_probe":
                mic = root / "app/ios/Runner/PhoneMic"
                mic.mkdir(parents=True)
                (mic / "PhoneMicPigeon.g.swift").write_text(
                    "enum PhoneMicCaptureState: Int {\n}\nenum PhoneMicCaptureMode: Int {\n}\n"
                    "final class PhoneMicPigeonError: Error {\n}\n")
                (here / "WearableProbe.swift").write_text("synthetic wearable source")
                models = root / "app/lib/services/devices/models.dart"
                models.parent.mkdir(parents=True)
                models.write_text("const String omiServiceUuid = 'a-b';\n"
                                  "const String audioDataStreamCharacteristicUuid = 'c-d';\n")
                overrides.update(ROOT=root, MIC=mic, SOURCES=[], __file__=str(here / "build.py"))
                profile = root / "synthetic-profile"
                profile.write_bytes(b"synthetic")
                args = argparse.Namespace(check=False, profile=profile, identity="synthetic-identity")
                invoke = lambda: module.build(argparse.ArgumentParser(), args, output)
                app = output / "OmiMicProbe.app"
                manifest_key = str(source.relative_to(root))
            else:
                invoke = lambda: module.build(output)
                app = output / "OmiAudioInterruption.app"
                manifest_key = name

            with patch.multiple(module, **overrides), patch.object(module.subprocess, "run", side_effect=run), \
                    patch.object(module.subprocess, "check_output", side_effect=check_output):
                if mutate or commit_changes:
                    with self.assertRaisesRegex(RuntimeError, "changed during compilation"):
                        invoke()
                    self.assertFalse((app / "build.json").exists())
                    self.assertFalse(any(c[0] == "codesign" for c in calls))
                else:
                    invoke()
                    manifest = json.loads((app / "build.json").read_text())
                    self.assertEqual(manifest["inputs"][manifest_key], original_hash)

    def test_capture_build_pins_the_diagnostic_lifecycle_helper(self):
        module = load("capture_build_inputs", "scripts/dev-harness/physical_capture_build.py")
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            helper = app / "integration_test/support/physical_capture_lifecycle.dart"
            helper.parent.mkdir(parents=True)
            helper.write_text("original lifecycle")
            before = module.input_hashes(app)
            helper.write_text("changed lifecycle")
            after = module.input_hashes(app)
            self.assertNotEqual(before[str(helper.relative_to(app))], after[str(helper.relative_to(app))])

    def test_phone_source_changed_during_compilation_cannot_get_receipt_or_sign(self):
        self.exercise("phone_mic_probe", mutate=True)

    def test_driver_source_changed_during_compilation_cannot_get_receipt(self):
        self.exercise("audio_interruption_driver", mutate=True)

    def test_phone_commit_changed_during_compilation_cannot_get_receipt_or_sign(self):
        self.exercise("phone_mic_probe", commit_changes=True)

    def test_stable_phone_build_attributes_compiler_input(self):
        self.exercise("phone_mic_probe")

    def test_stable_driver_build_attributes_compiler_input(self):
        self.exercise("audio_interruption_driver")


if __name__ == "__main__":
    unittest.main()
