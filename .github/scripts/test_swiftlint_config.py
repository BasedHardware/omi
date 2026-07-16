#!/usr/bin/env python3
"""Validate the SwiftLint safety configuration (#9843 Ticket 06).

Checks that .swiftlint.yml has exactly the safety-only rules and generated-code
policy, that the baseline exists and is valid JSON, and that the explicit macOS
CI runner verifies an exact SwiftLint release artifact and fails on warnings.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP = REPO_ROOT / "desktop/macos/Desktop"
CONFIG_PATH = DESKTOP / ".swiftlint.yml"
BASELINE_PATH = DESKTOP / ".swiftlint-baseline.json"
PACKAGE_PATH = DESKTOP / "Package.swift"
WRAPPER_PATH = REPO_ROOT / "desktop/macos/scripts/swiftlint-wrapper.sh"
MANIFEST_PATH = REPO_ROOT / ".github/checks-manifest.yaml"

EXPECTED_ONLY_RULES = {
  "custom_rules",
  "fatal_error_message",
  "force_cast",
  "force_try",
  "force_unwrapping",
  "implicitly_unwrapped_optional",
  "legacy_random",
  "weak_delegate",
}


def _parse_swiftlint_yml(path: Path) -> dict:
  """Minimal YAML parser for the flat .swiftlint.yml structure."""
  result: dict = {}
  current_section: str | None = None
  current_rule: dict | None = None
  for line in path.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
      continue
    if not line.startswith(" ") and stripped.endswith(":"):
      current_section = stripped[:-1]
      result[current_section] = []
      current_rule = None
      continue
    if stripped.startswith("- "):
      val = stripped[2:].strip().strip('"').strip("'")
      if current_section == "only_rules":
        result["only_rules"].append(val)
      elif current_section and isinstance(result.get(current_section), list):
        result[current_section].append(val)
      continue
    if ":" in stripped and current_section == "custom_rules":
      key, val = stripped.split(":", 1)
      key = key.strip()
      val = val.strip().strip("'").strip('"')
      if val:
        if current_rule is None:
          current_rule = {}
          result.setdefault("custom_rules_dict", {})[key] = current_rule
        else:
          current_rule[key] = val
      else:
        current_rule = {}
        result.setdefault("custom_rules_dict", {})[key] = current_rule
  return result


class SwiftLintConfigTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.config = _parse_swiftlint_yml(CONFIG_PATH)

  def test_only_rules_has_exact_safety_set(self):
    actual = set(self.config.get("only_rules", []))
    self.assertEqual(
      actual,
      EXPECTED_ONLY_RULES,
      f"only_rules must be exactly {EXPECTED_ONLY_RULES}, got {actual}",
    )

  def test_custom_rules_present(self):
    rules = self.config.get("custom_rules_dict", {})
    self.assertIn("omi_floating_control_bar_async_after", rules)
    self.assertIn("omi_inline_userdefaults_key", rules)

  def test_async_after_rule_regex(self):
    rules = self.config.get("custom_rules_dict", {})
    rule = rules.get("omi_floating_control_bar_async_after", {})
    self.assertIn("asyncAfter", rule.get("regex", ""))

  def test_userdefaults_rule_regex(self):
    rules = self.config.get("custom_rules_dict", {})
    rule = rules.get("omi_inline_userdefaults_key", {})
    self.assertIn("forKey", rule.get("regex", ""))

  def test_baseline_file_exists_and_valid(self):
    self.assertTrue(BASELINE_PATH.exists(), "baseline file must exist")
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    self.assertIsInstance(data, list, "baseline must be a JSON array")
    self.assertGreater(len(data), 0, "baseline must contain existing violations")

  def test_no_strict_mode(self):
    content = CONFIG_PATH.read_text(encoding="utf-8")
    self.assertNotIn("strict:", content, "must not use strict: true")

  def test_package_swift_has_plugin_on_swift_targets(self):
    content = PACKAGE_PATH.read_text(encoding="utf-8")
    # Plugin must be on Swift targets
    for target in ["OmiSupport", "OmiTheme", "OmiWAL"]:
      self.assertIn(f'name: "{target}"', content)
    # SwiftLint runs as an explicit CI lane, not as a SwiftPM build-tool plugin.
    # The plugin cannot run cleanly in CI/release builds because SwiftPM rejects
    # prebuild commands that depend on executables built from source.
    count = content.count("SwiftLintBuildToolPlugin")
    self.assertEqual(count, 0, f"expected no plugin attachments, got {count}")

  def test_package_swift_excludes_objc_and_cwebp(self):
    content = PACKAGE_PATH.read_text(encoding="utf-8")
    # ObjCExceptionCatcher and CWebP sections should NOT have plugins
    objc_section = re.search(r'name: "ObjCExceptionCatcher".*?(?=\n    \),)', content, re.DOTALL)
    if objc_section:
      self.assertNotIn("SwiftLintBuildToolPlugin", objc_section.group())
    cwebp_section = re.search(r'name: "CWebP".*?(?=\n    \),)', content, re.DOTALL)
    if cwebp_section:
      self.assertNotIn("SwiftLintBuildToolPlugin", cwebp_section.group())

  def test_pinned_runner_is_the_macos_manifest_producer(self):
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    self.assertIn('SWIFTLINT_VERSION="0.65.0"', wrapper)
    self.assertIn(
      'SWIFTLINT_RELEASE_URL="https://github.com/realm/SwiftLint/releases/download/${SWIFTLINT_VERSION}/portable_swiftlint.zip"',
      wrapper,
    )
    self.assertIn(
      'SWIFTLINT_RELEASE_SHA256="d6cb0aa7a2f5f1ef306fc9e37bcb54dc9a26facc8f7784ac0c3dd3eccf5c6ba6"',
      wrapper,
    )
    self.assertIn(
      'SWIFTLINT_BINARY_SHA256="06bdd57b59087dde8680ba6a62452defd71babd0513023f19ddfc6773708ba34"',
      wrapper,
    )
    self.assertIn("curl --fail --location --proto '=https' --tlsv1.2 --retry 3", wrapper)
    self.assertIn("shasum -a 256", wrapper)
    self.assertIn('unzip -Z -1 "$archive" | sort', wrapper)
    self.assertIn('[ -f "$BINARY" ] && [ ! -L "$BINARY" ]', wrapper)
    self.assertIn('[ "$binary_sha" = "$SWIFTLINT_BINARY_SHA256" ]', wrapper)
    self.assertNotIn("swift build -c release --product swiftlint", wrapper)
    self.assertIn("--strict --config", wrapper)

    manifest = MANIFEST_PATH.read_text(encoding="utf-8")
    self.assertIn("- id: desktop-swiftlint\n", manifest)
    self.assertIn('command: ["bash", "desktop/macos/scripts/swiftlint-wrapper.sh", "lint"]', manifest)
    self.assertIn('platforms: ["macos"]', manifest[manifest.index("- id: desktop-swiftlint\n"):])

  def test_runner_exposes_only_the_pinned_artifact_digest_without_bootstrapping(self):
    result = subprocess.run(
      ["bash", str(WRAPPER_PATH), "digest"],
      check=True,
      capture_output=True,
      text=True,
    )
    self.assertEqual(
      result.stdout.strip(),
      "d6cb0aa7a2f5f1ef306fc9e37bcb54dc9a26facc8f7784ac0c3dd3eccf5c6ba6",
    )

  def test_runner_rejects_unknown_subcommands_without_bootstrapping(self):
    result = subprocess.run(
      ["bash", str(WRAPPER_PATH), "not-a-command"],
      capture_output=True,
      text=True,
    )
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("usage:", result.stderr)

  def test_runner_does_not_execute_a_tampered_cache_entry(self):
    """A cache hit must verify the binary digest before executing it."""
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      marker = root / "fake-executed"
      cache_binary = root / "0.65.0-d6cb0aa7a2f5" / "swiftlint"
      cache_binary.parent.mkdir()
      cache_binary.write_text(f"#!/bin/sh\ntouch {marker}\necho 0.65.0\n", encoding="utf-8")
      cache_binary.chmod(0o755)

      # The wrapper should reject the fake binary, then fail at the deliberately
      # unavailable downloader; it must never execute the fake cache entry.
      blocked_curl = root / "bin"
      blocked_curl.mkdir()
      curl = blocked_curl / "curl"
      curl.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
      curl.chmod(0o755)
      env = os.environ | {
        "SWIFTLINT_CACHE_DIR": str(root),
        "PATH": f"{blocked_curl}{os.pathsep}{os.environ['PATH']}",
      }
      result = subprocess.run(
        ["bash", str(WRAPPER_PATH), "version"],
        env=env,
        capture_output=True,
        text=True,
      )

      self.assertNotEqual(result.returncode, 0)
      self.assertFalse(marker.exists(), "must not execute an unverified cached binary")
      self.assertIn("cache integrity check failed", result.stderr)


if __name__ == "__main__":
  unittest.main()
