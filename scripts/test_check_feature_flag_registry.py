#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import date
from unittest import mock
from pathlib import Path

from check_feature_flag_registry import check
from feature_flag_registry import load_registry, validate_registry
from render_feature_flag_registry import render


def flag(key: str = "EXAMPLE_ENABLED", **overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "key": key, "aliases": [], "kind": "env", "lifecycle": "rollout",
        "surfaces": ["backend"], "summary": "Fixture gate", "fail": "closed",
        "owner": "unowned", "created": "2026-08-01", "review_by": "2026-10-15", "decision": "pending",
    }
    entry.update(overrides)
    return entry


class RegistryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="omi-flag-registry-")
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, env={key: value for key, value in os.environ.items() if not key.startswith("GIT_")})
        self.write("backend/service.py", "import os\nENABLED_NAME = 'EXAMPLE_ENABLED'\nos.getenv(ENABLED_NAME)\n")
        self.write("config/feature-flags.yaml", self.yaml([flag()]))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def yaml(flags: list[dict[str, object]], ignore: list[dict[str, str]] | None = None, retired: list[dict[str, object]] | None = None) -> str:
        return "\n".join(
            ["flags:", *(f"  - {json.dumps(entry)}" for entry in flags), "ignore:",
             *(f"  - {json.dumps(entry)}" for entry in (ignore or [])), "retired:",
             *(f"  - {json.dumps(entry)}" for entry in (retired or [])), ""]
        )

    def errors(self) -> list[str]:
        return check(self.root, check_render=False)[0]

    def test_finds_literal_and_module_constant_env_reads_with_locations(self) -> None:
        self.write(
            "backend/service.py",
            "import os\nNAME = 'MISSING_MODE'\nos.getenv(NAME)\nos.environ.get('OTHER_ENABLED')\nos.environ['THIRD_STOP']\n",
        )
        errors = "\n".join(self.errors())
        self.assertIn("backend/service.py:3: unregistered feature flag: MISSING_MODE", errors)
        self.assertIn("backend/service.py:4: unregistered feature flag: OTHER_ENABLED", errors)
        self.assertIn("backend/service.py:5: unregistered feature flag: THIRD_STOP", errors)

    def test_swift_dart_and_build_define_patterns_require_registry_entries(self) -> None:
        self.write("desktop/macos/Desktop/Sources/Feature.swift", 'static let killSwitchFlagName = "missing_macos_kill"\nisFeatureEnabled("missing_enable")\n')
        self.write("app/lib/services/experiments/registry.dart", "ExperimentDefinition<String>(\n  key: 'missing-mobile-experiment',\n)\n")
        self.write("desktop/windows/src/renderer/flags.ts", "import.meta.env.VITE_ENABLE_MISSING_WINDOWS\n")
        self.write("web/admin/src/flags.ts", "process.env.NEXT_PUBLIC_ENABLE_MISSING_WEB\n")
        errors = "\n".join(self.errors())
        for key in ("missing_macos_kill", "missing_enable", "missing-mobile-experiment", "VITE_ENABLE_MISSING_WINDOWS", "NEXT_PUBLIC_ENABLE_MISSING_WEB"):
            self.assertIn(f"unregistered feature flag: {key}", errors)
        self.assertIn("desktop/macos/Desktop/Sources/Feature.swift:1", errors)
        self.assertIn("web/admin/src/flags.ts:1", errors)

    def test_hook_git_environment_does_not_redirect_fixture_git_reads(self) -> None:
        with mock.patch.dict(os.environ, {"GIT_DIR": "/nonexistent-outer-git-dir", "GIT_WORK_TREE": "/nonexistent-outer-worktree"}):
            self.assertEqual(self.errors(), [])

    def test_commented_client_gate_names_are_not_code_reads(self) -> None:
        self.write("web/admin/src/commented.ts", "// process.env.NEXT_PUBLIC_ENABLE_OLD_WIDGET\n")
        self.write("desktop/macos/Desktop/Sources/Commented.swift", '// static let flagName = "old-macos-flag"\n')
        self.assertEqual(self.errors(), [])

    def test_alias_without_code_read_is_stale(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(aliases=["FORMER_ENABLED"])]))
        self.assertIn("stale registry entry: delete it or restore the read: FORMER_ENABLED", self.errors())

    def test_deploy_key_missing_from_registry(self) -> None:
        self.write("backend/deploy/runtime_env/_base.yaml", "services:\n  MISSING_KILL_SWITCH:\n    value: false\n")
        self.assertTrue(any("backend/deploy/runtime_env/_base.yaml:2: undeclared registry flag: MISSING_KILL_SWITCH" in e for e in self.errors()))

    def test_rejects_bad_enums_duplicate_alias_and_posthog_schema(self) -> None:
        entries = [flag(kind="mystery", aliases=["EXAMPLE_ENABLED"], lifecycle="experiment", review_by="nonsense")]
        self.write("config/feature-flags.yaml", self.yaml(entries))
        errors = "\n".join(validate_registry(load_registry(self.root / "config/feature-flags.yaml")))
        self.assertIn("invalid kind", errors)
        self.assertIn("duplicate key or alias", errors)
        self.assertIn("review_by must be an ISO date", errors)
        self.write("config/feature-flags.yaml", self.yaml([flag(kind="posthog")]))
        self.assertIn("posthog requires row expected|absent", "\n".join(self.errors()))

    def test_duplicates_across_flag_alias_ignore_and_retired_are_rejected(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(aliases=["OLD_ENABLED"])], ignore=[{"key": "OLD_ENABLED", "reason": "Test"}], retired=[{"key": "EXAMPLE_ENABLED", "kind": "posthog", "retired": "2026-09-24", "reason": "Test", "posthog": {"row": "delete"}}]))
        errors = "\n".join(self.errors())
        self.assertIn("duplicate key or alias: OLD_ENABLED", errors)
        self.assertIn("duplicate key or alias: EXAMPLE_ENABLED", errors)

    def test_overdue_is_warning_not_failure(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(review_by="2020-01-01")]))
        errors, warnings = check(self.root, check_render=False)
        self.assertEqual(errors, [])
        self.assertIn("WARNING: overdue for a decision: EXAMPLE_ENABLED", warnings)

    def test_rendered_overdue_list_uses_explicit_as_of_date(self) -> None:
        registry = {"flags": [flag(review_by="2026-10-15")], "ignore": [], "retired": []}
        early = render(self.root, registry, date(2026, 9, 24))
        late = render(self.root, registry, date(2026, 11, 1))
        self.assertIn("None as of 2026-09-24.", early)
        self.assertIn("`EXAMPLE_ENABLED` — review_by 2026-10-15", late)
        self.assertNotIn("`EXAMPLE_ENABLED` — review_by", early)

    def test_rendered_doc_mismatch_requires_regeneration(self) -> None:
        self.write("backend/docs/feature-flag-registry.md", "<!-- feature-flag-registry as-of: 2026-09-24 -->\nstale\n")
        self.assertIn("rendered doc drift", "\n".join(check(self.root)[0]))

    def test_renderer_shows_inherited_and_chart_values_and_explicit_empty_literals(self) -> None:
        self.write("backend/deploy/runtime_env/_base.yaml", "environment_shared:\n  gke:\n    backend-listen:\n      env:\n        EXAMPLE_ENABLED:\n          value: 'true'\n        EMPTY_ENABLED:\n          value: ''\n")
        self.write("backend/deploy/runtime_env/prod.overlay.yaml", "overlay:\n  gke:\n    backend-listen:\n      env:\n        EXAMPLE_ENABLED:\n          value: 'false'\n")
        self.write("backend/charts/backend-listen/prod_omi_backend_listen_values.yaml", "env:\n  - name: EXAMPLE_ENABLED\n    value: 'true'\n")
        registry = {"flags": [flag(), flag("EMPTY_ENABLED")], "ignore": [], "retired": []}
        output = render(self.root, registry, date(2026, 9, 24))
        self.assertIn("| _base | dev | prod |", output)
        example = next(line for line in output.splitlines() if line.startswith("| `EXAMPLE_ENABLED` |"))
        cells = [part.strip() for part in example.strip("|").split("|")]
        self.assertEqual(cells[5], "true")
        self.assertEqual(cells[6], "true")
        self.assertIn("false", cells[7])
        self.assertIn("true", cells[7])
        self.assertIn("(chart)", cells[7])
        empty = next(line for line in output.splitlines() if line.startswith("| `EMPTY_ENABLED` |"))
        self.assertIn("''", empty)

    def test_retired_name_must_not_be_read_and_is_exempt_from_stale(self) -> None:
        old = {"key": "old-kill-v1", "kind": "posthog", "retired": "2026-09-24", "reason": "Superseded", "posthog": {"row": "delete"}}
        self.write("config/feature-flags.yaml", self.yaml([flag()], retired=[old]))
        self.assertEqual(self.errors(), [])
        self.write("backend/other.py", "OLD_FLAG_KEY = 'old-kill-v1'\n")
        self.assertIn("retired name reintroduced: old-kill-v1", "\n".join(self.errors()))


if __name__ == "__main__":
    unittest.main()
