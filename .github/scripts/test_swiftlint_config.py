#!/usr/bin/env python3
"""Validate the SwiftLint safety configuration (#9843 Ticket 06).

Checks that .swiftlint.yml has exactly the 7 safety rules in only_rules plus
custom_rules, that the custom_rules have proven regex patterns, that the
baseline exists and is valid JSON, and that Package.swift attaches the plugin
to all first-party Swift targets (and NOT to ObjCExceptionCatcher or CWebP).
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP = REPO_ROOT / "desktop/macos/Desktop"
CONFIG_PATH = DESKTOP / ".swiftlint.yml"
BASELINE_PATH = DESKTOP / ".swiftlint-baseline.json"
PACKAGE_PATH = DESKTOP / "Package.swift"

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
    # Count plugin attachments: existing first-party targets plus VoiceTurnDomain
    # and its dedicated test target.
    count = content.count("SwiftLintBuildToolPlugin")
    self.assertEqual(count, 10, f"expected 10 plugin attachments, got {count}")

  def test_package_swift_excludes_objc_and_cwebp(self):
    content = PACKAGE_PATH.read_text(encoding="utf-8")
    # ObjCExceptionCatcher and CWebP sections should NOT have plugins
    objc_section = re.search(r'name: "ObjCExceptionCatcher".*?(?=\n    \),)', content, re.DOTALL)
    if objc_section:
      self.assertNotIn("SwiftLintBuildToolPlugin", objc_section.group())
    cwebp_section = re.search(r'name: "CWebP".*?(?=\n    \),)', content, re.DOTALL)
    if cwebp_section:
      self.assertNotIn("SwiftLintBuildToolPlugin", cwebp_section.group())


if __name__ == "__main__":
  unittest.main()
