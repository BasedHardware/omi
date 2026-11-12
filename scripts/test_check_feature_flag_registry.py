#!/usr/bin/env python3
from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from io import StringIO
from unittest import mock
from pathlib import Path

from git_test_env import clean_git_env

from check_feature_flag_registry import MAX_UNRAMPED_PER_OWNER, check, normalize_owner, owner_backlog, owner_tokens
from feature_flag_registry import effective_due, ramp_due, load_registry, validate_registry
from render_feature_flag_registry import render, _deploy_index, _parse_mapping


def flag(key: str = "EXAMPLE_ENABLED", **overrides: object) -> dict[str, object]:
    lifecycle = overrides.get("lifecycle", "rollout")
    decision = overrides.get("decision", "pending")
    terminal = overrides.get(
        "terminal",
        (
            "keep"
            if lifecycle in {"ops_kill", "config_switch"}
            else {"graduate": "on", "ship": "on", "kill": "off", "keep": "keep"}.get(decision, "on")
        ),
    )
    entry: dict[str, object] = {
        "key": key,
        "aliases": [],
        "kind": "env",
        "lifecycle": "rollout",
        "surfaces": ["backend"],
        "summary": "Fixture gate",
        "fail": "open" if lifecycle == "ops_kill" else "closed",
        "owner": "tester",
        "created": "2026-08-01",
        "review_by": "2026-11-15",
        "decision": "pending",
        "terminal": terminal,
    }
    entry.update(overrides)
    return entry


def ramp_plan(**overrides: object) -> dict[str, object]:
    ramp: dict[str, object] = {
        "cohorts": ["release-probe", "1%", "5% 3h", "25%", "100%"],
        "clean_metric": "checkout_error_rate",
        "expander": "release-owner session",
        "done_by": "2026-11-20",
    }
    ramp.update(overrides)
    return ramp


def extension(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "until": "2026-11-15",
        "reason": "Complete the staged cohort readout",
        "by": "release-owner lane",
        "granted": "2026-11-01",
    }
    fields.update(overrides)
    return fields


class RegistryFixture(unittest.TestCase):
    def setUp(self) -> None:
        git_env = mock.patch.dict(os.environ, clean_git_env(), clear=True)
        git_env.start()
        self.addCleanup(git_env.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="omi-flag-registry-")
        self.root = Path(self.temp.name)
        subprocess.run(
            ["git", "init", "-q"],
            cwd=self.root,
            check=True,
            env=clean_git_env(),
        )
        self.write("backend/service.py", "import os\nENABLED_NAME = 'EXAMPLE_ENABLED'\nos.getenv(ENABLED_NAME)\n")
        self.write("config/feature-flags.yaml", self.yaml([flag()]))

    def test_default_as_of_uses_utc_even_when_local_date_is_ahead(self) -> None:
        self.write_flags([flag(review_by="2026-11-01")])
        # At UTC midnight minus one hour, a UTC+7 host already says Nov 9.
        instant = datetime(2026, 11, 8, 23, tzinfo=timezone.utc)
        with mock.patch("check_feature_flag_registry.datetime") as clock:
            clock.now.return_value = instant
            errors, warnings = check(self.root, check_render=False)
        clock.now.assert_called_once_with(timezone.utc)
        self.assertEqual([], errors)
        self.assertIn("within the 7-day grace", "\n".join(warnings))
        self.assertTrue(check(self.root, check_render=False, as_of=date(2026, 11, 9))[0])

    def test_live_policy_guard_preserves_default_on_kills_and_accepts_opt_in_lifecycles(self) -> None:
        path = Path(__file__).resolve().parents[1] / "backend/config/policy/guard.py"
        spec = importlib.util.spec_from_file_location("flag_registry_policy_guard", path)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        cohort = flag("BATCH_LIVE_STT_RETIRE_PERCENT", notes="Nested batch cohort")
        for default_on in (True, False):
            self.write("backend/config/policy/kill_switches.py", f"KILL_SWITCHES = {{'EXAMPLE_ENABLED': {default_on!r}}}\n")
            for lifecycle in ("ops_kill", "config_switch", "rollout", "experiment"):
                with self.subTest(default_on=default_on, lifecycle=lifecycle):
                    self.write("config/feature-flags.yaml", self.yaml([flag(lifecycle=lifecycle), cohort]))
                    expected = lifecycle == "ops_kill" or (not default_on and lifecycle in {"config_switch", "rollout"})
                    self.assertEqual(expected, not guard.registry_violations(self.root))
            self.write("config/feature-flags.yaml", self.yaml([cohort]))
            self.assertIn("EXAMPLE_ENABLED", "\n".join(guard.registry_violations(self.root)))

    def test_shared_boolean_parser_fail_field_is_enforced(self) -> None:
        with mock.patch("check_feature_flag_registry.parser_defaults", return_value={"EXAMPLE_ENABLED": "open"}):
            errors, _ = check(self.root, check_render=False, as_of=date(2026, 10, 1))
        self.assertTrue(any("EXAMPLE_ENABLED: fail must be open" in error for error in errors))

    def test_renderer_checks_and_generates_parser_fail_field(self) -> None:
        self.write(
            "backend/config/refactor_modes.py",
            "def default_on(name, *, environ=None): return True\n"
            "def default_off(name, *, environ=None): return False\n",
        )
        self.write(
            "backend/config/example.py",
            "from config.refactor_switches import default_on\ndef enabled(): return default_on('EXAMPLE_ENABLED', False)\n",
        )
        renderer = Path(__file__).with_name("render_feature_flag_registry.py")
        import sys

        command = [sys.executable, str(renderer), "--root", str(self.root), "--as-of", "2026-10-01"]
        checked = subprocess.run(command + ["--check-parsers"], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
        self.assertIn("EXAMPLE_ENABLED", checked.stderr)
        rendered = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
        checked = subprocess.run(command + ["--check-parsers"], capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(load_registry(self.root / "config/feature-flags.yaml")["flags"][0]["fail"], "open")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def yaml(
        flags: list[dict[str, object]],
        ignore: list[dict[str, str]] | None = None,
        retired: list[dict[str, object]] | None = None,
    ) -> str:
        return "\n".join(
            [
                "flags:",
                *(f"  - {json.dumps(entry)}" for entry in flags),
                "ignore:",
                *(f"  - {json.dumps(entry)}" for entry in (ignore or [])),
                "retired:",
                *(f"  - {json.dumps(entry)}" for entry in (retired or [])),
                "",
            ]
        )

    def errors(self) -> list[str]:
        return check(self.root, check_render=False, as_of=date(2026, 11, 8))[0]

    def write_flags(self, rows: list[dict[str, object]]) -> None:
        self.write("config/feature-flags.yaml", self.yaml(rows))
        self.write("backend/service.py", "import os\n" + "".join(f"os.getenv({row['key']!r})\n" for row in rows))

    def commit_fixture(self) -> str:
        identity = [
            "-c",
            "user.email=flags@example.test",
            "-c",
            "user.name=Flag Tests",
            "-c",
            "core.hooksPath=/dev/null",
        ]
        for args in (["add", "-A"], ["commit", "-qm", "fixture"]):
            subprocess.run(["git", *identity, *args], cwd=self.root, check=True, env=clean_git_env())
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()

    def backlog_base(self, count: int = MAX_UNRAMPED_PER_OWNER, **overrides: object) -> list[dict[str, object]]:
        rows = [flag(f"EXAMPLE_{index}_ENABLED", **overrides) for index in range(count)]
        self.write_flags(rows)
        base = self.commit_fixture()
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", base], cwd=self.root, check=True)
        return rows

    def test_owner_at_cap_cannot_add_rollout_but_under_cap_can(self) -> None:
        rows = self.backlog_base()
        self.write_flags(rows + [flag("NEW_ENABLED", decision="ship")])
        self.commit_fixture()
        self.assertIn("NEW_ENABLED: owner=tester had 5 unramped flags", "\n".join(self.errors()))
        self.assertIn("ramp or retire before adding", "\n".join(self.errors()))
        # Existing merge-base debt still gates new rollout rows; additions in
        # this diff must also fit within the remaining debt allowance.
        rows[-1]["decision"] = "ship"
        self.write_flags(rows)
        base = self.commit_fixture()
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", base], cwd=self.root, check=True)
        self.write_flags(rows + [flag("UNDER_CAP_ENABLED")])
        self.assertEqual([], self.errors())
        self.write_flags(rows + [flag("UNDER_CAP_ENABLED"), flag("ANOTHER_ENABLED")])
        self.assertIn("would have 6 unramped flags after this diff", "\n".join(self.errors()))

    def test_multiple_additions_cannot_bypass_owner_cap(self) -> None:
        self.backlog_base(count=0)
        rows = [flag(f"NEW_{index}_ENABLED") for index in range(6)]
        self.write_flags(rows[:5])
        self.assertEqual([], self.errors())
        self.write_flags(rows)
        self.assertIn("would have 6 unramped flags after this diff", "\n".join(self.errors()))

    def test_multiple_live_ramps_do_not_consume_owner_debt_cap(self) -> None:
        self.backlog_base(count=0)
        self.write_flags([flag(f"NEW_{index}_ENABLED", ramp=ramp_plan(done_by="2026-11-15")) for index in range(6)])
        self.assertEqual([], self.errors())

    def test_pre_existing_rows_count_without_blocking_retroactively(self) -> None:
        rows = self.backlog_base(MAX_UNRAMPED_PER_OWNER + 1)
        rows[0]["summary"] = "Edited pre-existing rollout"
        self.write_flags(rows)
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual([], self.errors())
        self.assertIn("FLAG_OWNER_BACKLOG owner=tester unramped=6", output.getvalue())

    def test_only_new_rollouts_for_the_capped_owner_are_blocked(self) -> None:
        rows = self.backlog_base()
        ops = flag("OPS_ENABLED", lifecycle="ops_kill", decision="keep")
        ops.pop("review_by")
        self.write_flags(rows + [ops, flag("OTHER_ENABLED", owner="other")])
        self.assertEqual([], self.errors())

    def test_backlog_exception_warns_through_expiry_then_errors(self) -> None:
        rows = self.backlog_base(review_by="2026-12-01")
        self.write_flags(rows + [flag("NEW_ENABLED", review_by="2026-12-01")])
        exceptions = {"tester": {"expires": "2026-11-20", "reason": "Approved migration overlap"}}
        with mock.patch("check_feature_flag_registry.OWNER_BACKLOG_EXCEPTIONS", exceptions):
            errors, warnings = check(self.root, check_render=False, as_of=date(2026, 11, 20))
            self.assertEqual([], errors)
            self.assertIn("owner backlog exception expires 2026-11-20", "\n".join(warnings))
            self.assertIn("Approved migration overlap", "\n".join(warnings))
            errors, _ = check(self.root, check_render=False, as_of=date(2026, 11, 21))
            self.assertIn("owner backlog exception expired 2026-11-20", "\n".join(errors))
            self.assertIn("ramp or retire before adding", "\n".join(errors))

    def test_backlog_exception_requires_expiry_and_reason(self) -> None:
        rows = self.backlog_base()
        self.write_flags(rows + [flag("NEW_ENABLED")])
        for exception in (
            {"reason": "missing expiry"},
            {"expires": "bad", "reason": "bad date"},
            {"expires": "2026-11-20", "reason": " "},
        ):
            with self.subTest(exception=exception), mock.patch(
                "check_feature_flag_registry.OWNER_BACKLOG_EXCEPTIONS", {"tester": exception}
            ):
                self.assertIn("requires an ISO expires date and nonempty reason", "\n".join(self.errors()))

    def test_missing_merge_base_warns_and_skips_gate(self) -> None:
        errors, warnings = check(self.root, check_render=False, as_of=date(2026, 10, 1))
        self.assertEqual([], errors)
        self.assertIn("WARNING: registry diff rules and owner backlog gate skipped", "\n".join(warnings))
        self.assertIn("merge-base with origin/main", "\n".join(warnings))

    def test_missing_registry_at_base_warns_and_skips_gate(self) -> None:
        (self.root / "config/feature-flags.yaml").unlink()
        base = self.commit_fixture()
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", base], cwd=self.root, check=True)
        self.write_flags([flag()])
        errors, warnings = check(self.root, check_render=False, as_of=date(2026, 10, 1))
        self.assertEqual([], errors)
        self.assertIn("WARNING: registry diff rules and owner backlog gate skipped", "\n".join(warnings))

    def test_backlog_normalizes_owners_in_output_and_gate(self) -> None:
        rows = self.backlog_base(owner="  Tester (omi-lifecycle)  ")
        self.write_flags(rows + [flag("NEW_ENABLED", owner="TESTER")])
        output = StringIO()
        with redirect_stdout(output):
            errors = self.errors()
        self.assertIn("FLAG_OWNER_BACKLOG owner=tester unramped=6\n", output.getvalue())
        self.assertIn("NEW_ENABLED: owner=tester had 5 unramped flags", "\n".join(errors))

    def test_normalize_owner_collapses_whitespace_left_by_annotations(self) -> None:
        self.assertEqual("alice bob", normalize_owner("Alice (team) Bob"))
        self.assertEqual("alice bob", normalize_owner("  alice\tBOB "))

    def test_backlog_counts_only_pending_or_undecided_rollouts(self) -> None:
        # undecided is a legacy decision spelling, even if current schema rejects new uses.
        rows = [
            flag(),
            flag("LEGACY_ENABLED", owner="TESTER (lead)", decision="undecided"),
            flag("SHIPPED_ENABLED", decision="ship"),
            flag("EXPERIMENT_ENABLED", lifecycle="experiment"),
            flag("KILL_ENABLED", lifecycle="ops_kill", decision="keep"),
        ]
        self.assertEqual({"tester": 2}, owner_backlog({"flags": rows}))

    def test_gate_uses_merge_base_not_origin_main_tip(self) -> None:
        rows = self.backlog_base()
        base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        self.write_flags([dict(row, decision="ship") for row in rows])
        tip = self.commit_fixture()
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", tip], cwd=self.root, check=True)
        subprocess.run(["git", "checkout", "-q", "--detach", base], cwd=self.root, check=True)
        self.write_flags(rows + [flag("NEW_ENABLED")])
        self.commit_fixture()
        self.assertIn("ramp or retire before adding", "\n".join(self.errors()))

    def test_kill_after_readout_is_a_reviewed_nonterminal_experiment(self) -> None:
        self.write("backend/docs/experiment.md", "Pre-registered readout")
        row = flag(
            lifecycle="experiment",
            decision="kill_after_readout",
            terminal="undecided",
            review_by="2026-10-30",
            prereg="backend/docs/experiment.md",
        )
        self.assertEqual(validate_registry({"flags": [row], "ignore": [], "retired": []}, root=self.root), [])
        for changes in ({"terminal": "off"}, {"lifecycle": "rollout"}):
            errors = validate_registry({"flags": [{**row, **changes}], "ignore": [], "retired": []}, root=self.root)
            self.assertTrue(any("kill_after_readout requires" in error for error in errors))

    def test_finds_literal_and_module_constant_env_reads_with_locations(self) -> None:
        self.write(
            "backend/service.py",
            "import os\nNAME = 'MISSING_MODE'\nos.getenv(NAME)\nos.environ.get('OTHER_ENABLED')\nos.environ['THIRD_STOP']\n",
        )
        errors = "\n".join(self.errors())
        self.assertIn("backend/service.py:3: unregistered feature flag: MISSING_MODE", errors)
        self.assertIn("backend/service.py:4: unregistered feature flag: OTHER_ENABLED", errors)
        self.assertIn("backend/service.py:5: unregistered feature flag: THIRD_STOP", errors)

    def test_central_kill_switch_reads_are_not_stale_and_still_require_registration(self) -> None:
        self.write("backend/service.py", "from config.policy import kill_switch\nkill_switch('EXAMPLE_ENABLED')\n")
        self.assertEqual([], self.errors())
        self.write(
            "backend/service.py",
            "from config.policy import kill_switch\nkill_switch('EXAMPLE_ENABLED')\nkill_switch('MISSING_ENABLED')\n",
        )
        self.assertIn("backend/service.py:3: unregistered feature flag: MISSING_ENABLED", self.errors())

    def test_swift_dart_and_build_define_patterns_require_registry_entries(self) -> None:
        self.write(
            "desktop/macos/Desktop/Sources/Feature.swift",
            'static let killSwitchFlagName = "missing_macos_kill"\nisFeatureEnabled("missing_enable")\n',
        )
        self.write(
            "app/lib/services/experiments/registry.dart",
            "ExperimentDefinition<String>(\n  key: 'missing-mobile-experiment',\n)\n",
        )
        self.write("desktop/windows/src/renderer/flags.ts", "import.meta.env.VITE_ENABLE_MISSING_WINDOWS\n")
        self.write("web/admin/src/flags.ts", "process.env.NEXT_PUBLIC_ENABLE_MISSING_WEB\n")
        self.write(
            "web/app/src/lib/gate.ts", "class Gate {\n  static readonly enabledFlag = 'missing-web-posthog';\n}\n"
        )
        errors = "\n".join(self.errors())
        for key in (
            "missing_macos_kill",
            "missing_enable",
            "missing-mobile-experiment",
            "VITE_ENABLE_MISSING_WINDOWS",
            "NEXT_PUBLIC_ENABLE_MISSING_WEB",
            "missing-web-posthog",
        ):
            self.assertIn(f"unregistered feature flag: {key}", errors)
        self.assertIn("desktop/macos/Desktop/Sources/Feature.swift:1", errors)
        self.assertIn("web/admin/src/flags.ts:1", errors)

    def test_dart_kill_switch_constant_is_cataloged(self) -> None:
        self.write(
            "app/lib/services/experiments/watch_copy_dedupe.dart",
            "class Policy { static const killSwitchFlag = 'watch_copy_dedupe_off'; }\n",
        )
        self.assertIn("unregistered feature flag: watch_copy_dedupe_off", "\n".join(self.errors()))
        kill = flag(
            "watch_copy_dedupe_off",
            kind="posthog",
            surfaces=["mobile"],
            lifecycle="ops_kill",
            decision="keep",
            terminal="keep",
            posthog={"row": "expected", "role": "kill"},
        )
        kill.pop("review_by")
        self.write("config/feature-flags.yaml", self.yaml([flag(), kill]))
        self.assertEqual([], self.errors())

    def test_swift_sdk_constant_read_is_a_real_surface_not_an_unconditional_declaration(self) -> None:
        key = "fixture-remote-stop"
        self.write(
            "config/feature-flags.yaml",
            self.yaml(
                [flag(), flag(key, kind="posthog", surfaces=["macos"], posthog={"row": "expected", "role": "kill"})]
            ),
        )
        source = 'enum Stop {\n static let key = "fixture-remote-stop"\n static var killed: Bool {\n PostHogSDK.shared.getFeatureFlag(key, sendFeatureFlagEvent: false) as? Bool == true\n }\n}\n'
        self.write("desktop/macos/Desktop/Sources/Stop.swift", source)
        self.assertEqual(self.errors(), [])
        self.write(
            "desktop/macos/Desktop/Sources/Stop.swift",
            source.replace(' PostHogSDK.shared.getFeatureFlag', ' // PostHogSDK.shared.getFeatureFlag'),
        )
        self.assertIn("stale registry entry: delete it or restore the read: " + key, self.errors())

    def test_cataloged_node_runtime_gate_is_not_stale(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(), flag("ADMIN_GATE_ENABLED", surfaces=["web-admin"])]))
        self.write("web/admin/lib/flags.ts", "process.env.ADMIN_GATE_ENABLED !== '1'\n")
        self.assertEqual(self.errors(), [])

    def test_commented_node_runtime_gate_stays_stale(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(), flag("ADMIN_GATE_ENABLED", surfaces=["web-admin"])]))
        self.write("web/admin/lib/flags.ts", "// process.env.ADMIN_GATE_ENABLED !== '1'\n")
        self.assertIn("stale registry entry: delete it or restore the read: ADMIN_GATE_ENABLED", self.errors())

    def test_hook_git_environment_does_not_redirect_fixture_git_reads(self) -> None:
        with mock.patch.dict(
            os.environ, {"GIT_DIR": "/nonexistent-outer-git-dir", "GIT_WORK_TREE": "/nonexistent-outer-worktree"}
        ):
            self.assertEqual(self.errors(), [])

    def test_commented_client_gate_names_are_not_code_reads(self) -> None:
        self.write("web/admin/src/commented.ts", "// process.env.NEXT_PUBLIC_ENABLE_OLD_WIDGET\n")
        self.write("desktop/macos/Desktop/Sources/Commented.swift", '// static let flagName = "old-macos-flag"\n')
        self.assertEqual(self.errors(), [])

    def test_alias_without_code_read_is_stale(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(aliases=["FORMER_ENABLED"])]))
        self.assertIn("stale registry entry: delete it or restore the read: FORMER_ENABLED", self.errors())

    def test_reads_tracked_at_head_are_scanned_in_sparse_checkout(self) -> None:
        # Cone-mode sparse checkouts do not materialise out-of-cone sources:
        # the read scanner must fall back to the HEAD blob or every app/web
        # flag is misreported as stale in a backend-scoped lane.
        self.write(
            "app/lib/services/experiments/gate.dart",
            "final a = ExperimentDefinition<String>(key: 'SPARSE_MOBILE_GATE');\n",
        )
        self.write(
            "config/feature-flags.yaml",
            self.yaml([flag(), flag(key="SPARSE_MOBILE_GATE", surfaces=["mobile"])]),
        )
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        identity = ["-c", "user.email=flags@example.test", "-c", "user.name=Flag Tests"]
        subprocess.run(["git", "-C", str(self.root), *identity, "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(self.root), *identity, "commit", "-qm", "fixture"], check=True, env=env)
        (self.root / "app/lib/services/experiments/gate.dart").unlink()
        self.assertEqual(self.errors(), [])
        # An alias with no read on disk or at HEAD is still stale: the HEAD
        # fallback widens sparse visibility, it does not weaken the check.
        (self.root / "config/feature-flags.yaml").write_text(
            self.yaml([flag(), flag(key="SPARSE_MOBILE_GATE", surfaces=["mobile"], aliases=["SPARSE_GONE"])]),
            encoding="utf-8",
        )
        errors = self.errors()
        self.assertIn("stale registry entry: delete it or restore the read: SPARSE_GONE", errors)
        self.assertNotIn("stale registry entry: delete it or restore the read: SPARSE_MOBILE_GATE", errors)

    def test_deploy_key_missing_from_registry(self) -> None:
        self.write(
            "backend/deploy/runtime_env/_base.yaml",
            "environment_shared:\n  cloud_run:\n    services:\n      backend:\n        env:\n          MISSING_KILL_SWITCH:\n            value: false\n",
        )
        self.assertTrue(
            any(
                "backend/deploy/runtime_env/_base.yaml:6: undeclared registry flag: MISSING_KILL_SWITCH" in e
                for e in self.errors()
            )
        )

    def test_rejects_bad_enums_duplicate_alias_and_posthog_schema(self) -> None:
        entries = [flag(kind="mystery", aliases=["EXAMPLE_ENABLED"], lifecycle="experiment", review_by="nonsense")]
        self.write("config/feature-flags.yaml", self.yaml(entries))
        errors = "\n".join(validate_registry(load_registry(self.root / "config/feature-flags.yaml")))
        self.assertIn("invalid kind", errors)
        self.assertIn("duplicate key or alias", errors)
        self.assertIn("review_by must be an ISO date", errors)
        self.write("config/feature-flags.yaml", self.yaml([flag(kind="posthog")]))
        self.assertIn("posthog requires row expected|absent", "\n".join(self.errors()))

    def test_ship_decision_is_accepted_and_rendered(self) -> None:
        self.write("backend/docs/experiments/EXP-fixture.md", "# Closure\n")
        self.write(
            "config/feature-flags.yaml",
            self.yaml(
                [
                    flag(
                        lifecycle="experiment",
                        decision="ship",
                        review_by="2026-11-01",
                        prereg="backend/docs/experiments/EXP-fixture.md",
                    )
                ]
            ),
        )
        self.assertEqual(self.errors(), [])
        registry = load_registry(self.root / "config/feature-flags.yaml")
        output = render(self.root, registry, date(2026, 10, 8))
        self.assertTrue(any("ship" in line for line in output.splitlines() if line.startswith("| `EXAMPLE_ENABLED` |")))

    def test_with_legacy_keeps_a_dated_rollout_until_deletion(self) -> None:
        entry = flag(decision="with_legacy", terminal="off", review_by="2026-12-15")
        self.assertEqual(validate_registry({"flags": [entry], "ignore": [], "retired": []}, root=self.root), [])
        entry["terminal"] = "on"
        errors = "\n".join(validate_registry({"flags": [entry], "ignore": [], "retired": []}, root=self.root))
        self.assertIn("decision with_legacy requires terminal off", errors)
        entry["terminal"] = "off"
        del entry["review_by"]
        errors = "\n".join(validate_registry({"flags": [entry], "ignore": [], "retired": []}, root=self.root))
        self.assertIn("review_by", errors)

    def test_unknown_decision_is_rejected(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(decision="unknown")]))
        self.assertIn("invalid decision", "\n".join(self.errors()))

    def test_terminal_is_required_and_decisions_must_match_terminal(self) -> None:
        missing = flag()
        del missing["terminal"]
        errors = "\n".join(validate_registry({"flags": [missing], "ignore": [], "retired": []}, root=self.root))
        self.assertIn("terminal is required", errors)
        wrong = flag(decision="graduate", terminal="off")
        errors = "\n".join(validate_registry({"flags": [wrong], "ignore": [], "retired": []}, root=self.root))
        self.assertIn("decision graduate requires terminal on", errors)
        wrong_switch = flag(lifecycle="ops_kill", terminal="undecided")
        errors = "\n".join(validate_registry({"flags": [wrong_switch], "ignore": [], "retired": []}, root=self.root))
        self.assertIn("ops_kill terminal must be keep", errors)

    def test_post_cutoff_pending_rollout_accepts_complete_ramp_and_render_shows_it(self) -> None:
        entry = flag(
            created="2026-10-21",
            review_by="2026-11-30",
            terminal="undecided",
            ramp=ramp_plan(),
        )
        self.write("config/feature-flags.yaml", self.yaml([entry]))
        errors, _ = check(self.root, check_render=False, as_of=date(2026, 10, 21))
        self.assertEqual(errors, [])
        output = render(self.root, {"flags": [entry], "ignore": [], "retired": []}, date(2026, 10, 21))
        self.assertIn(
            "| `EXAMPLE_ENABLED` | release-probe → 1% → 5% 3h → 25% → 100% | "
            "checkout_error_rate | release-owner session | 2026-11-20 |",
            output,
        )

    def test_post_cutoff_pending_rollout_requires_ramp(self) -> None:
        entry = flag(created="2026-10-21", terminal="undecided")
        errors = "\n".join(validate_registry({"flags": [entry], "ignore": [], "retired": []}, root=self.root))
        self.assertIn("ramp is required", errors)

    def test_ramp_requires_all_fields(self) -> None:
        entry = flag(
            created="2026-10-21",
            review_by="2026-11-30",
            terminal="undecided",
            ramp=ramp_plan(expander=""),
        )
        errors = "\n".join(validate_registry({"flags": [entry], "ignore": [], "retired": []}, root=self.root))
        self.assertIn("ramp.expander is required", errors)

    def test_ramp_done_by_cannot_exceed_review_by(self) -> None:
        entry = flag(
            created="2026-10-21",
            review_by="2026-11-19",
            terminal="undecided",
            ramp=ramp_plan(done_by="2026-11-20"),
        )
        errors = "\n".join(validate_registry({"flags": [entry], "ignore": [], "retired": []}, root=self.root))
        self.assertIn("ramp.done_by must be on or before review_by", errors)

    def test_single_user_ramp_terminal_step_is_rejected(self) -> None:
        for final_step in ("David-only", "single user"):
            with self.subTest(final_step=final_step):
                entry = flag(
                    created="2026-10-21",
                    review_by="2026-11-30",
                    terminal="undecided",
                    ramp=ramp_plan(cohorts=["release-probe", final_step]),
                )
                errors = "\n".join(validate_registry({"flags": [entry], "ignore": [], "retired": []}, root=self.root))
                self.assertIn("terminal step must not be single-user", errors)

    def test_pre_cutoff_pending_rollout_is_grandfathered_with_warning_count(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag()]))
        errors, warnings = check(self.root, check_render=False, as_of=date(2026, 10, 20))
        self.assertEqual(errors, [])
        self.assertTrue(any("WARNING: 1 grandfathered pending/undecided rollout rows lack ramp" in w for w in warnings))

    def test_rollout_and_experiment_owners_cannot_be_unowned(self) -> None:
        entry = flag(owner="unowned")
        errors = "\n".join(validate_registry({"flags": [entry], "ignore": [], "retired": []}, root=self.root))
        self.assertIn("rollout owner must not be unowned", errors)

    def test_duplicates_across_flag_alias_ignore_and_retired_are_rejected(self) -> None:
        self.write(
            "config/feature-flags.yaml",
            self.yaml(
                [flag(aliases=["OLD_ENABLED"])],
                ignore=[{"key": "OLD_ENABLED", "reason": "Test"}],
                retired=[
                    {
                        "key": "EXAMPLE_ENABLED",
                        "kind": "posthog",
                        "retired": "2026-09-24",
                        "reason": "Test",
                        "posthog": {"row": "delete"},
                    }
                ],
            ),
        )
        errors = "\n".join(self.errors())
        self.assertIn("duplicate key or alias: OLD_ENABLED", errors)
        self.assertIn("duplicate key or alias: EXAMPLE_ENABLED", errors)

    def test_review_by_has_seven_day_grace_then_fails(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(review_by="2026-10-13")]))
        errors, warnings = check(self.root, check_render=False, as_of=date(2026, 10, 20))
        self.assertEqual(errors, [])
        self.assertTrue(any("within the 7-day grace: EXAMPLE_ENABLED (due 2026-10-13, owner tester)" in w for w in warnings))
        errors, _ = check(self.root, check_render=False, as_of=date(2026, 10, 21))
        self.assertIn("review overdue beyond the 7-day grace: EXAMPLE_ENABLED", "\n".join(errors))

    def test_effective_due_uses_later_review_or_extension_date(self) -> None:
        self.assertEqual(date(2026, 11, 15), effective_due(flag()))
        self.assertEqual(date(2026, 11, 15), effective_due(flag(extension=extension(until="2026-11-05"))))
        self.assertEqual(date(2026, 11, 20), effective_due(flag(extension=extension(until="2026-11-20"))))
        self.assertEqual(
            date(2026, 11, 15), ramp_due(flag(ramp=ramp_plan(done_by="2026-11-01"), extension=extension()))
        )
        self.assertEqual(date(2026, 11, 20), ramp_due(flag(ramp=ramp_plan(), extension=extension())))

    def test_extension_defers_review_and_preserves_grace_boundary(self) -> None:
        self.write_flags([flag(review_by="2026-11-01", extension=extension())])
        errors, warnings = check(self.root, check_render=False, as_of=date(2026, 11, 22))
        self.assertEqual([], errors)
        self.assertIn("(due 2026-11-15, owner tester)", "\n".join(warnings))
        errors, _ = check(self.root, check_render=False, as_of=date(2026, 11, 23))
        self.assertIn(
            "review overdue beyond the 7-day grace: EXAMPLE_ENABLED (due 2026-11-15, owner tester): "
            "ramp, retire, or add one extension", errors
        )

    def test_ramp_deadline_uses_same_extension_and_grace(self) -> None:
        row = flag(review_by="2026-12-01", ramp=ramp_plan(done_by="2026-11-01"))
        self.write_flags([row])
        self.assertEqual([], check(self.root, check_render=False, as_of=date(2026, 11, 8))[0])
        errors, _ = check(self.root, check_render=False, as_of=date(2026, 11, 9))
        self.assertEqual([
            "ramp overdue beyond the 7-day grace: EXAMPLE_ENABLED (done_by 2026-11-01, owner tester): "
            "ramp, retire, or add one extension"
        ], errors)
        self.write_flags([dict(row, extension=extension())])
        self.assertEqual([], check(self.root, check_render=False, as_of=date(2026, 11, 22))[0])
        errors, _ = check(self.root, check_render=False, as_of=date(2026, 11, 23))
        self.assertIn("(done_by 2026-11-15, owner tester)", "\n".join(errors))

    def test_decided_rows_require_code_retirement_after_grace(self) -> None:
        self.write("docs/prereg.md", "# readout\n")
        for decision in ("graduate", "ship", "kill", "kill_after_readout"):
            with self.subTest(decision=decision):
                row = flag(decision=decision, review_by="2026-11-01")
                if decision == "kill_after_readout":
                    row.update(lifecycle="experiment", terminal="undecided", prereg="docs/prereg.md")
                self.write_flags([row])
                self.assertEqual([], check(self.root, check_render=False, as_of=date(2026, 11, 8))[0])
                errors, _ = check(self.root, check_render=False, as_of=date(2026, 11, 9))
                self.assertEqual([
                    f"EXAMPLE_ENABLED decided {decision} but code still reads it (due 2026-11-01): retire the code path"
                ], errors)

    def test_extension_schema_rejects_invalid_dates_reason_and_lane(self) -> None:
        cases = [
            (extension(until="2026-11-16"), "0 to 14 days"),
            (extension(until="2026-10-31"), "0 to 14 days"),
            (extension(until="bad"), "extension.until must be an ISO date"),
            (extension(granted=None), "extension.granted must be an ISO date"),
            (extension(reason=""), "extension.reason"),
            (extension(reason="ReNeW"), "extension.reason"),
            (extension(reason=" extend "), "extension.reason"),
            (extension(reason="TBD"), "extension.reason"),
            (extension(reason="Later"), "extension.reason"),
            (extension(reason="Needs more"), "extension.reason"),
            (extension(by=" "), "extension.by"),
            ({"until": "2026-11-15"}, "extension.granted"),
            (None, "extension must be an object"),
        ]
        for value, message in cases:
            with self.subTest(value=value):
                errors = validate_registry({"flags": [flag(extension=value)], "ignore": [], "retired": []}, root=self.root)
                self.assertIn(message, "\n".join(errors))
        self.assertEqual([], validate_registry({"flags": [flag(extension=extension())], "ignore": [], "retired": []}, root=self.root))

    def test_second_extension_or_removal_is_refused_against_base(self) -> None:
        rows = self.backlog_base(count=1, extension=extension())
        for changes in ({"extension": extension(until="2026-11-16", granted="2026-11-02")}, {}):
            row = dict(rows[0])
            row.pop("extension")
            row.update(changes)
            self.write_flags([row])
            self.assertIn(f"{row['key']}: second extension refused: ramp or retire", self.errors())
        self.write_flags(rows)
        self.assertEqual([], self.errors())

    def test_original_dates_cannot_be_moved_later_even_with_extension(self) -> None:
        rows = self.backlog_base(count=1, ramp=ramp_plan(done_by="2026-11-01"))
        key = rows[0]["key"]
        for changes in (
            {"review_by": "2026-11-16"},
            {"ramp": ramp_plan(done_by="2026-11-02")},
            {"review_by": "2026-11-16", "extension": extension()},
        ):
            with self.subTest(changes=changes):
                self.write_flags([dict(rows[0], **changes)])
                self.assertIn(f"{key}: due date moved later without an extension; add extension: instead", self.errors())
        self.write_flags([dict(rows[0], extension=extension())])
        self.assertEqual([], self.errors())

    def test_new_rows_are_exempt_from_date_movement_rule(self) -> None:
        rows = self.backlog_base(count=1)
        self.write_flags(rows + [flag("NEW_ENABLED", review_by="2026-12-01", ramp=ramp_plan())])
        self.assertEqual([], self.errors())

    def test_decision_change_cannot_hide_later_original_dates(self) -> None:
        rows = self.backlog_base(count=1, ramp=ramp_plan(done_by="2026-11-01"))
        for decision, terminal in (("ship", "on"), ("kill", "off")):
            for changes in ({"review_by": "2026-12-01"}, {"ramp": ramp_plan(done_by="2026-11-02")}):
                with self.subTest(decision=decision, changes=changes):
                    self.write_flags([dict(rows[0], decision=decision, terminal=terminal, **changes)])
                    self.assertIn("due date moved later without an extension", "\n".join(self.errors()))

    def test_extension_grant_cannot_be_future_dated(self) -> None:
        registry = {
            "flags": [flag(extension=extension(granted="2099-01-01", until="2099-01-15"))],
            "ignore": [],
            "retired": [],
        }
        errors = validate_registry(registry, root=self.root, as_of=date(2026, 11, 8))
        self.assertIn("EXAMPLE_ENABLED: extension.granted must not be in the future", errors)
        self.assertEqual([], validate_registry(registry, root=self.root, as_of=date(2099, 1, 1)))

    def test_already_decided_rows_cannot_postpone_original_dates(self) -> None:
        for decision in ("ship", "graduate", "kill"):
            rows = self.backlog_base(count=1, decision=decision, ramp=ramp_plan(done_by="2026-11-01"))
            for changes in ({"review_by": "2026-12-01"}, {"ramp": ramp_plan(done_by="2026-11-02")}):
                with self.subTest(decision=decision, changes=changes):
                    self.write_flags([dict(rows[0], **changes)])
                    self.assertIn("due date moved later without an extension", "\n".join(self.errors()))

    def test_existing_ramp_cannot_be_removed_while_its_deadline_applies(self) -> None:
        rows = self.backlog_base(count=1, review_by="2026-12-01", ramp=ramp_plan(done_by="2026-11-01"))
        row = dict(rows[0])
        row.pop("ramp")
        self.write_flags([row])
        errors, _ = check(self.root, check_render=False, as_of=date(2026, 11, 9))
        self.assertIn(f"{row['key']}: ramp deadline removed; keep the plan, ramp, or retire", errors)
        # The approved permanent-lifecycle relabel removes an inapplicable plan.
        row.update(lifecycle="config_switch", decision="keep", terminal="keep")
        row.pop("review_by")
        self.write_flags([row])
        self.assertEqual([], self.errors())

    def test_missing_base_warns_and_skips_all_diff_rules(self) -> None:
        self.write_flags([flag(extension=extension())])
        with mock.patch("check_feature_flag_registry.load_base_registry", side_effect=ValueError("base unavailable")):
            errors, warnings = check(self.root, check_render=False, as_of=date(2026, 11, 1))
        self.assertEqual([], errors)
        self.assertIn("registry diff rules and owner backlog gate skipped", "\n".join(warnings))
        self.assertIn("base unavailable", "\n".join(warnings))

    def test_missing_base_warns_and_skips_new_owner_classification(self) -> None:
        self.write_flags([flag(owner="dazheng / auditfix")])
        with mock.patch("check_feature_flag_registry.load_base_registry", side_effect=ValueError("base unavailable")):
            errors, warnings = check(self.root, check_render=False, as_of=date(2026, 11, 1))
        self.assertEqual([], errors)
        self.assertIn("registry diff rules and owner backlog gate skipped", "\n".join(warnings))
        self.assertIn("base unavailable", "\n".join(warnings))

    def test_permanent_rows_may_record_a_valid_bounded_extension(self) -> None:
        row = flag(lifecycle="ops_kill", decision="keep", extension=extension())
        row.pop("review_by")
        self.assertEqual([], validate_registry({"flags": [row], "ignore": [], "retired": []}, root=self.root))

    def test_unreadable_base_shape_warns_and_skips_all_diff_rules(self) -> None:
        with mock.patch("check_feature_flag_registry.load_base_registry", return_value={}):
            errors, warnings = check(self.root, check_render=False, as_of=date(2026, 11, 1))
        self.assertEqual([], errors)
        self.assertIn("registry diff rules and owner backlog gate skipped", "\n".join(warnings))

    def test_live_ramps_do_not_count_as_owner_debt_until_grace_passes(self) -> None:
        rows = [
            flag(),
            flag("LIVE_ENABLED", ramp=ramp_plan(done_by="2026-11-08")),
            flag("GRACE_ENABLED", ramp=ramp_plan(done_by="2026-11-01")),
            flag("EXTENDED_ENABLED", ramp=ramp_plan(done_by="2026-11-01"), extension=extension()),
        ]
        self.assertEqual({"tester": 1}, owner_backlog({"flags": rows}, date(2026, 11, 8)))
        self.assertEqual({"tester": 2}, owner_backlog({"flags": rows}, date(2026, 11, 9)))
        self.assertEqual({"tester": 4}, owner_backlog({"flags": rows}, date(2026, 11, 23)))

    def test_owner_gate_uses_live_ramps_at_the_requested_date(self) -> None:
        rows = self.backlog_base(ramp=ramp_plan(done_by="2026-11-01"))
        self.write_flags(rows + [flag("NEW_ENABLED")])
        self.assertEqual([], check(self.root, check_render=False, as_of=date(2026, 11, 8))[0])
        errors, _ = check(self.root, check_render=False, as_of=date(2026, 11, 9))
        self.assertIn("NEW_ENABLED: owner=tester had 5 unramped flags", "\n".join(errors))

    def test_new_rows_with_account_owner_tokens_are_refused(self) -> None:
        rows = self.backlog_base(count=1, owner="auditfix")
        for owner in (
            "  DAZHENG (backend) ", "dazheng / auditfix", "auditfix,dazheng",
            "auditfix and dazheng", "auditfix & dazheng", "auditfix+dazheng", "auditfix|dazheng",
        ):
            for lifecycle in ("rollout", "ops_kill", "config_switch"):
                with self.subTest(owner=owner, lifecycle=lifecycle):
                    row = flag("NEW_ENABLED", owner=owner, lifecycle=lifecycle)
                    if lifecycle != "rollout":
                        row.pop("review_by")
                    self.write_flags(rows + [row])
                    self.assertIn("NEW_ENABLED: owner names an account; name the owning lane or area", self.errors())

    def test_new_row_with_lane_owner_passes(self) -> None:
        rows = self.backlog_base(count=1, owner="auditfix")
        self.write_flags(rows + [flag("NEW_ENABLED", owner="auditfix")])
        self.assertEqual([], self.errors())

    def test_existing_rows_with_account_tokens_are_not_newly_refused(self) -> None:
        rows = self.backlog_base(count=1, owner="dazheng")
        for owner in ("dazheng", "dazheng / auditfix", "auditfix,dazheng", "auditfix and dazheng"):
            with self.subTest(owner=owner):
                self.write_flags([dict(rows[0], owner=owner)])
                self.assertEqual([], self.errors())

    def test_owner_tokens_preserve_multiword_lanes_and_deduplicate(self) -> None:
        self.assertEqual(
            ("auditfix", "two-lane lead", "backlog-refactor", "omi-pipeline"),
            owner_tokens(" AUDITFIX (sweep) / two-lane lead, backlog-refactor & omi-pipeline + AUDITFIX | auditfix AND auditfix "),
        )
        self.assertEqual(("candy lane", "research-and-development"), owner_tokens("candy lane/research-and-development"))

    def test_shared_debt_counts_once_for_each_distinct_lane(self) -> None:
        rows = [flag(owner="auditfix / backlog-refactor / AUDITFIX"), flag("OTHER_ENABLED", owner="backlog-refactor")]
        self.assertEqual({"auditfix": 1, "backlog-refactor": 2}, owner_backlog({"flags": rows}))

    def test_shared_owner_cap_checks_base_and_new_rows_by_lane_token(self) -> None:
        rows = self.backlog_base(owner="other / auditfix")
        self.write_flags(rows + [flag("NEW_ENABLED", owner="fresh and auditfix")])
        self.assertIn("NEW_ENABLED: owner=auditfix had 5 unramped flags", "\n".join(self.errors()))
        rows = self.backlog_base(count=4, owner="other / auditfix")
        self.write_flags(rows + [flag("NEW_ENABLED", owner="fresh / auditfix"), flag("ANOTHER_ENABLED", owner="auditfix, fresh")])
        self.assertIn("owner=auditfix would have 6 unramped flags", "\n".join(self.errors()))

    def test_ops_kill_must_default_on_unless_temporarily_allowlisted(self) -> None:
        row = flag(lifecycle="ops_kill", decision="keep", fail="closed")
        row.pop("review_by")
        registry = {"flags": [row], "ignore": [], "retired": []}
        self.assertIn(
            "EXAMPLE_ENABLED: ops_kill must default on (off is the kill); use rollout or config_switch",
            validate_registry(registry, root=self.root),
        )
        with mock.patch("feature_flag_registry.OPS_KILL_DEFAULT_OFF_ALLOWLIST", {"EXAMPLE_ENABLED"}):
            self.assertEqual([], validate_registry(registry, root=self.root, as_of=date(2026, 11, 29)))
            errors = validate_registry(registry, root=self.root, as_of=date(2026, 11, 30))
            self.assertIn("ops_kill default-off exception expired 2026-11-29: EXAMPLE_ENABLED", errors)
        for fail in ("open", "inverted"):
            registry["flags"][0]["fail"] = fail
            self.assertEqual([], validate_registry(registry, root=self.root))

    def test_ops_kill_allowlist_stale_entries_fail_only_at_real_root(self) -> None:
        registry = {"flags": [flag()], "ignore": [], "retired": []}
        with mock.patch("feature_flag_registry.OPS_KILL_DEFAULT_OFF_ALLOWLIST", {"GONE_ENABLED"}):
            self.assertEqual([], validate_registry(registry, root=self.root))
            with mock.patch("feature_flag_registry.ROOT", self.root):
                self.assertIn("remove stale ops_kill default-off allowlist entries: GONE_ENABLED", validate_registry(registry, root=self.root))

    def test_keep_and_with_legacy_rollouts_warn_about_lifecycle(self) -> None:
        self.write_flags([flag(decision="keep"), flag("LEGACY_ENABLED", decision="with_legacy", terminal="off")])
        errors, warnings = check(self.root, check_render=False, as_of=date(2026, 11, 1))
        self.assertEqual([], errors)
        self.assertIn("EXAMPLE_ENABLED: rollout row decided keep; relabel config_switch or ops_kill", warnings)
        self.assertIn("LEGACY_ENABLED: rollout row decided keep; relabel config_switch or ops_kill", warnings)

    def test_machine_reports_dates_counts_and_dark_age_boundaries(self) -> None:
        self.write_flags([
            flag("SOON_ENABLED", review_by="2026-11-02", ramp=ramp_plan(done_by="2026-11-01")),
            flag("LATER_ENABLED", review_by="2026-11-03"),
            flag("BOUNDARY_ENABLED", created="2026-10-18", fail="closed"),
            flag("OPEN_ENABLED", fail="open"),
            flag("DECIDED_ENABLED", decision="ship"),
        ])
        output = StringIO()
        with redirect_stdout(output):
            errors, _ = check(self.root, check_render=False, as_of=date(2026, 11, 7))
        self.assertEqual([], errors)
        lines = output.getvalue().splitlines()
        self.assertIn("FLAG_DUE_SOON key=SOON_ENABLED owner=tester kind=review due=2026-11-02 breaks=2026-11-10", lines)
        self.assertIn("FLAG_DUE_SOON key=SOON_ENABLED owner=tester kind=ramp due=2026-11-01 breaks=2026-11-09", lines)
        self.assertFalse(any("FLAG_DUE_SOON key=LATER_ENABLED" in line for line in lines))
        self.assertIn("FLAG_OVERDUE_COUNT n=2", lines)  # Each row counted once, even with two deadlines.
        self.assertIn("FLAG_DARK_OVER_14D n=3", lines)
        output = StringIO()
        with redirect_stdout(output):
            check(self.root, check_render=False, as_of=date(2026, 11, 1))
        self.assertIn("FLAG_DARK_OVER_14D n=2", output.getvalue())  # Exactly 14 days is excluded.
        output = StringIO()
        with redirect_stdout(output):
            check(self.root, check_render=False, as_of=date(2026, 11, 9))
        self.assertIn("FLAG_OVERDUE_COUNT n=1", output.getvalue())  # SOON's ramp already fails.

    def test_machine_due_soon_uses_extension_date(self) -> None:
        self.write_flags([flag(review_by="2026-11-01", ramp=ramp_plan(done_by="2026-11-01"), extension=extension())])
        output = StringIO()
        with redirect_stdout(output):
            check(self.root, check_render=False, as_of=date(2026, 11, 20))
        self.assertIn("kind=review due=2026-11-15 breaks=2026-11-23", output.getvalue())
        self.assertIn("kind=ramp due=2026-11-15 breaks=2026-11-23", output.getvalue())

    def test_cli_as_of_prints_machine_report_before_deadline_errors(self) -> None:
        self.write_flags([flag(review_by="2026-11-01")])
        checker = Path(__file__).with_name("check_feature_flag_registry.py")
        import sys
        result = subprocess.run(
            [sys.executable, str(checker), "--root", str(self.root), "--skip-render", "--as-of", "2026-11-09"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertLess(result.stdout.index("FLAG_OVERDUE_COUNT"), result.stdout.index("review overdue beyond"))

    def test_rendered_rules_and_overdue_respect_row_extension(self) -> None:
        registry = {"flags": [flag(review_by="2026-11-01", extension=extension())], "ignore": [], "retired": []}
        early = render(self.root, registry, date(2026, 11, 10))
        late = render(self.root, registry, date(2026, 11, 16))
        self.assertIn("None as of 2026-11-10.", early)
        self.assertIn("review_by 2026-11-01; effective due 2026-11-15", late)
        self.assertIn("One `extension: {until, reason, by, granted}` per row", early)
        self.assertIn("pure code changes with a clean revert", early)
        self.assertNotIn("review_overdue", early)

    def test_duplicate_ramp_declarations_fail_across_sources(self) -> None:
        self.write(
            "backend/service.py",
            "import os\nNAME = 'EXAMPLE_ENABLED'\nos.getenv(NAME)\nos.getenv('EXAMPLE_PERCENT')\nos.getenv('EXAMPLE_UID_ALLOWLIST')\n",
        )
        self.write(
            "config/feature-flags.yaml",
            self.yaml([flag(), flag("EXAMPLE_PERCENT"), flag("EXAMPLE_UID_ALLOWLIST")]),
        )
        self.write(
            "backend/deploy/runtime_env/_base.yaml",
            "environment_shared:\n  gke:\n    backend-listen:\n      env:\n        EXAMPLE_PERCENT:\n          value: '10'\n        EXAMPLE_UID_ALLOWLIST:\n          value: 'uid'\n",
        )
        self.write(
            "backend/charts/backend-listen/prod_omi_backend_listen_values.yaml",
            "env:\n  - name: EXAMPLE_PERCENT\n    value: '10'\n  - name: EXAMPLE_UID_ALLOWLIST\n    value: 'uid'\n",
        )
        self.write(
            ".github/actions/deploy/action.yml",
            'run: gcloud run services update backend-listen --update-env-vars "EXAMPLE_PERCENT=10,EXAMPLE_UID_ALLOWLIST=uid"\n',
        )
        errors, _ = check(self.root, check_render=False, as_of=date(2026, 10, 1))
        self.assertIn("duplicate declaration: EXAMPLE_PERCENT for backend-listen/prod", "\n".join(errors))
        self.assertIn("duplicate declaration: EXAMPLE_UID_ALLOWLIST for backend-listen/prod", "\n".join(errors))

    def duplicate_fixture(self, key="EXAMPLE_PERCENT") -> None:
        self.write_flags([flag(key)])

    def manifest_flag(
        self,
        filename="_base.yaml",
        *,
        workload="backend-listen",
        value="10",
        runtime="gke",
        key="EXAMPLE_PERCENT",
        values_file=None,
    ) -> None:
        header = "environment_shared" if filename == "_base.yaml" else "overlay"
        if runtime == "gke":
            link = f"      values_file: {values_file}\n" if values_file else ""
            body = f"  gke:\n    {workload}:\n{link}      env:\n        {key}: {{value: '{value}'}}\n"
        else:
            body = (
                f"  cloud_run:\n    services:\n      {workload}:\n        env:\n          {key}: {{value: '{value}'}}\n"
            )
        self.write(f"backend/deploy/runtime_env/{filename}", f"{header}:\n{body}")

    def chart_flag(
        self, env="prod", *, filename=None, workload="backend-listen", key="EXAMPLE_PERCENT", value="10"
    ) -> str:
        path = f"backend/charts/{workload}/{filename or env + '_omi_' + workload.replace('-', '_') + '_values.yaml'}"
        self.write(path, f"env:\n  - name: {key}\n    value: '{value}'\n")
        return path

    def test_base_and_overlay_compose_one_logical_source(self) -> None:
        self.duplicate_fixture()
        self.manifest_flag()
        self.manifest_flag("dev.overlay.yaml", value="0")
        self.manifest_flag("prod.overlay.yaml", value="100")
        self.assertEqual([], self.errors())

    def test_unlinked_gke_and_chart_fail_without_allowlist(self) -> None:
        # A formerly excepted key fails too: there is no key-specific escape hatch.
        key = "AUDIO_ARCHIVE_PERCENT"
        self.duplicate_fixture(key)
        self.manifest_flag("prod.overlay.yaml", key=key)
        chart = self.chart_flag(key=key)
        self.assertEqual(
            [
                f"duplicate declaration: {key} for backend-listen/prod appears in "
                f"{chart}, backend/deploy/runtime_env#backend-listen: keep one source, "
                "or declare it in the manifest gke section that validates this chart"
            ],
            self.errors(),
        )
        import check_feature_flag_registry as checker

        self.assertFalse(any(name.startswith("DUPLICATE_DECLARATION_ALLOWLIST") for name in vars(checker)))
        self.assertNotIn("DUPLICATE_DECLARATION_ALLOWLIST", Path(checker.__file__).read_text())

    def test_gke_and_its_values_file_chart_are_one_validated_source(self) -> None:
        self.duplicate_fixture()
        self.manifest_flag(values_file="backend/charts/backend-listen/{env}_omi_backend_listen_values.yaml")
        self.manifest_flag("prod.overlay.yaml", value="100")
        self.chart_flag("dev")
        self.chart_flag("prod", value="100")
        self.assertEqual([], self.errors())

    def test_gke_pointing_to_different_chart_does_not_exempt_unlinked_chart(self) -> None:
        self.duplicate_fixture()
        self.manifest_flag("prod.overlay.yaml", values_file="backend/charts/backend-listen/prod_other_values.yaml")
        self.chart_flag()
        self.chart_flag(filename="prod_other_values.yaml")
        errors = self.errors()
        self.assertEqual(1, len(errors))
        self.assertIn("duplicate declaration: EXAMPLE_PERCENT for backend-listen/prod", errors[0])
        self.assertIn("prod_omi_backend_listen_values.yaml", errors[0])

    def test_values_file_override_is_environment_scoped(self) -> None:
        self.duplicate_fixture()
        self.manifest_flag(values_file="backend/charts/backend-listen/{env}_omi_backend_listen_values.yaml")
        self.manifest_flag("prod.overlay.yaml", values_file="backend/charts/backend-listen/prod_override_values.yaml")
        self.chart_flag("dev")
        self.chart_flag("prod")
        self.chart_flag(filename="prod_override_values.yaml")
        errors = self.errors()
        self.assertEqual(1, len(errors))
        self.assertIn("for backend-listen/prod", errors[0])

    def test_values_file_pairing_does_not_depend_on_chart_directory_or_service_list(self) -> None:
        self.duplicate_fixture()
        chart = "backend/charts/shared/prod_custom_values.yaml"
        self.manifest_flag("prod.overlay.yaml", workload="custom-worker", values_file=chart)
        self.write(chart, "env:\n  - name: EXAMPLE_PERCENT\n    value: '10'\n")
        self.assertEqual([], self.errors())
        self.write(
            ".github/actions/deploy/action.yml",
            "run: gcloud run services update custom-worker --project based-hardware --update-env-vars EXAMPLE_PERCENT=10\n",
        )
        self.assertEqual([], self.errors())

    def test_values_file_without_env_prefix_is_paired_in_each_referenced_environment(self) -> None:
        self.duplicate_fixture()
        chart = "backend/charts/shared/values.yaml"
        self.manifest_flag(workload="custom-worker", values_file=chart)
        self.write(chart, "env:\n  - name: EXAMPLE_PERCENT\n    value: '10'\n")
        self.assertEqual([], self.errors())
        from feature_flag_registry import extract_deploy_declarations

        declared = [item for item in extract_deploy_declarations(self.root) if item.path == chart]
        self.assertEqual(
            {("custom-worker", "dev"), ("custom-worker", "prod")},
            {(item.workload, item.environment) for item in declared},
        )

    def test_duplicate_identity_includes_platform_even_when_workload_name_matches(self) -> None:
        from feature_flag_registry import Declaration, duplicate_declaration_sources

        declarations = [
            Declaration("EXAMPLE_PERCENT", platform + ".yaml", 1, platform, "backend-listen", "dev", platform)
            for platform in ("gke", "cloud_run_service", "cloud_run_job", "desktop", "action")
        ]
        self.assertEqual({}, duplicate_declaration_sources(declarations))
        declarations.append(Declaration("EXAMPLE_PERCENT", "second.yaml", 1, "gke", "backend-listen", "dev", "second"))
        self.assertEqual(
            {("EXAMPLE_PERCENT", "gke", "backend-listen", "dev"): ["gke", "second"]},
            duplicate_declaration_sources(declarations),
        )

    def test_cloud_run_and_chart_are_different_workloads(self) -> None:
        self.duplicate_fixture()
        self.manifest_flag(workload="backend-listen", runtime="cloud_run")
        self.chart_flag()
        self.assertEqual([], self.errors())

    def test_chart_dev_and_prod_are_different_environments(self) -> None:
        self.duplicate_fixture()
        self.chart_flag("dev")
        self.chart_flag("prod")
        self.assertEqual([], self.errors())

    def test_two_charts_for_same_workload_and_environment_fail(self) -> None:
        self.duplicate_fixture()
        self.chart_flag()
        self.chart_flag(filename="prod_second_values.yaml")
        self.assertIn("duplicate declaration: EXAMPLE_PERCENT for backend-listen/prod", "\n".join(self.errors()))

    def test_two_gke_charts_still_fail_alongside_same_named_cloud_run_action(self) -> None:
        self.duplicate_fixture()
        first = self.chart_flag("dev")
        second = self.chart_flag("dev", filename="dev_second_values.yaml")
        self.write(
            ".github/actions/deploy/action.yml",
            "run: gcloud run services update backend-listen --project based-hardware-dev --update-env-vars EXAMPLE_PERCENT=10\n",
        )
        errors = self.errors()
        self.assertEqual(1, len(errors))
        self.assertIn("for backend-listen/dev", errors[0])
        self.assertIn(first, errors[0])
        self.assertIn(second, errors[0])
        self.assertNotIn(".github/actions/", errors[0])

    def test_cloud_run_action_and_same_named_gke_chart_are_different_platforms(self) -> None:
        self.duplicate_fixture()
        self.chart_flag()
        self.write(
            ".github/actions/deploy/action.yml",
            "run: gcloud run services update backend-listen --project based-hardware-dev --update-env-vars EXAMPLE_PERCENT=10\n",
        )
        self.assertEqual([], self.errors())
        self.chart_flag("dev")
        self.assertEqual([], self.errors())
        from feature_flag_registry import extract_action_declarations, extract_deploy_declarations

        self.assertEqual({"cloud_run_service"}, {item.platform for item in extract_action_declarations(self.root)})
        self.assertEqual({"gke"}, {item.platform for item in extract_deploy_declarations(self.root)})

    def test_action_uses_its_command_not_another_target_in_the_step(self) -> None:
        self.duplicate_fixture()
        self.manifest_flag("dev.overlay.yaml", runtime="cloud_run")
        self.write(
            ".github/actions/deploy/action.yml",
            "run: |\n  gcloud run services update other --update-env-vars OTHER=0\n"
            "  gcloud run services update backend-listen --update-env-vars EXAMPLE_PERCENT=10 --project based-hardware-dev\n",
        )
        self.assertIn(
            "duplicate declaration: EXAMPLE_PERCENT for cloud_run/services/backend-listen/dev", "\n".join(self.errors())
        )

    def test_inline_chart_entry_is_a_declaration(self) -> None:
        self.duplicate_fixture()
        self.manifest_flag("prod.overlay.yaml")
        self.write(
            "backend/charts/backend-listen/prod_omi_backend_listen_values.yaml",
            "env:\n  - {name: EXAMPLE_PERCENT, value: '10'}\n",
        )
        self.assertIn("duplicate declaration: EXAMPLE_PERCENT for backend-listen/prod", "\n".join(self.errors()))

    def test_quoted_compact_and_merged_unlinked_manifest_entries_are_declarations(self) -> None:
        self.duplicate_fixture()
        self.chart_flag()
        for body in (
            "overlay: {gke: {backend-listen: {env: {'EXAMPLE_PERCENT': {value: '10'}}}}}\n",
            "shared: &flags {EXAMPLE_PERCENT: {value: '10'}}\noverlay:\n  gke:\n    backend-listen:\n      env:\n        <<: *flags\n",
        ):
            with self.subTest(body=body):
                self.write("backend/deploy/runtime_env/prod.overlay.yaml", body)
                self.assertIn(
                    "duplicate declaration: EXAMPLE_PERCENT for backend-listen/prod", "\n".join(self.errors())
                )

    def test_action_files_remain_distinct_sources(self) -> None:
        self.duplicate_fixture()
        for name in ("first", "second"):
            self.write(
                f".github/actions/{name}/action.yml",
                "run: gcloud run services update backend --project based-hardware --update-env-vars EXAMPLE_PERCENT=10\n",
            )
        errors = self.errors()
        self.assertEqual(1, len(errors))
        self.assertIn("for cloud_run/services/backend/prod", errors[0])

    def test_cli_as_of_controls_expired_review_date(self) -> None:
        import sys

        self.write_flags([flag(review_by="2026-10-13")])
        command = [
            sys.executable,
            str(Path(__file__).with_name("check_feature_flag_registry.py")),
            "--root",
            str(self.root),
            "--skip-render",
            "--as-of",
        ]
        early = subprocess.run(command + ["2026-10-20"], capture_output=True, text=True)
        self.assertEqual(0, early.returncode, early.stdout + early.stderr)
        late = subprocess.run(command + ["2026-11-21"], capture_output=True, text=True)
        self.assertEqual(1, late.returncode)
        self.assertIn("review overdue beyond the 7-day grace: EXAMPLE_ENABLED", late.stderr)

    def test_rendered_overdue_list_uses_explicit_as_of_date(self) -> None:
        registry = {"flags": [flag(review_by="2026-10-15")], "ignore": [], "retired": []}
        early = render(self.root, registry, date(2026, 9, 24))
        late = render(self.root, registry, date(2026, 11, 1))
        self.assertIn("None as of 2026-09-24.", early)
        self.assertIn("`EXAMPLE_ENABLED` — review_by 2026-10-15", late)
        self.assertNotIn("`EXAMPLE_ENABLED` — review_by", early)

    def test_rendered_doc_mismatch_requires_regeneration(self) -> None:
        self.write("backend/docs/feature-flag-registry.md", "<!-- feature-flag-registry as-of: 2026-09-24 -->\nstale\n")
        self.assertIn("rendered doc drift", "\n".join(check(self.root, as_of=date(2026, 10, 1))[0]))

    def test_renderer_resolves_shared_cohort_mapping(self) -> None:
        tree = _parse_mapping(
            'first:\n  <<: &cohort {"FLAG": {"value": "true", "category": "rollout"}}\nsecond:\n  <<: *cohort\n  OTHER: literal\n'
        )
        self.assertEqual(tree['first']['FLAG'], {'value': 'true', 'category': 'rollout'})
        self.assertEqual(tree['second']['FLAG'], tree['first']['FLAG'])
        self.assertEqual(tree['second']['OTHER'], 'literal')

    def test_renderer_shows_inherited_and_chart_values_and_explicit_empty_literals(self) -> None:
        self.write(
            "backend/deploy/runtime_env/_base.yaml",
            "environment_shared:\n  gke:\n    backend-listen:\n      env:\n        EXAMPLE_ENABLED:\n          value: 'true'\n        EMPTY_ENABLED:\n          value: ''\n",
        )
        self.write(
            "backend/deploy/runtime_env/prod.overlay.yaml",
            "overlay:\n  gke:\n    backend-listen:\n      env:\n        EXAMPLE_ENABLED:\n          value: 'false'\n",
        )
        self.write(
            "backend/charts/backend-listen/prod_omi_backend_listen_values.yaml",
            "env:\n  - name: EXAMPLE_ENABLED\n    value: 'true'\n",
        )
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

    def test_renderer_indexes_deploy_action_env_overlays(self) -> None:
        self.write(
            ".github/actions/sync-backfill-lifecycle/action.yml",
            'run: |\n  echo "sync_backfill_env_vars<<EOF"\n'
            '  echo "SYNC_BACKFILL_ROUTING_ENABLED=true"\n  echo "EOF"\n'
            '  gcloud run services update backend-sync --update-env-vars "SYNC_BACKFILL_EXTRA_ENABLED=on"\n',
        )
        self.write(
            ".github/workflows/deploy-backend-prod.yml",
            'run: gcloud run services update backend-sync --update-env-vars "PROD_ACTION_KILL=false"\n',
        )
        index = _deploy_index(self.root)
        self.assertEqual(index["dev"]["sync-backfill-lifecycle (action)"]["SYNC_BACKFILL_ROUTING_ENABLED"], "true")
        self.assertEqual(index["prod"]["sync-backfill-lifecycle (action)"]["SYNC_BACKFILL_EXTRA_ENABLED"], "on")
        self.assertEqual(index["prod"]["deploy-backend-prod (action)"]["PROD_ACTION_KILL"], "false")
        self.assertNotIn("PROD_ACTION_KILL", index["dev"].get("deploy-backend-prod (action)", {}))

    def test_experiment_requires_prereg(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(lifecycle="experiment")]))
        self.assertIn("prereg is required for experiments", "\n".join(self.errors()))

    def test_kill_decision_experiment_is_exempt_from_prereg(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(lifecycle="experiment", decision="kill")]))
        self.assertEqual(self.errors(), [])

    def test_experiment_still_requires_review_by(self) -> None:
        self.write("docs/prereg/example.md", "# prereg\n")
        entry = flag(lifecycle="experiment", prereg="docs/prereg/example.md")
        del entry["review_by"]
        self.write("config/feature-flags.yaml", self.yaml([entry]))
        self.assertIn("review_by is required for experiment/rollout", "\n".join(self.errors()))

    def test_null_or_empty_prereg_fails_validation(self) -> None:
        for value in (None, ""):
            with self.subTest(prereg=value):
                self.write("config/feature-flags.yaml", self.yaml([flag(lifecycle="experiment", prereg=value)]))
                self.assertIn("prereg must be a nonempty repo-relative path", "\n".join(self.errors()))
        self.write("config/feature-flags.yaml", self.yaml([flag(prereg=None)]))
        self.assertIn("prereg must be a nonempty repo-relative path", "\n".join(self.errors()))

    def test_prereg_must_be_relative_inside_root_and_exist(self) -> None:
        self.write("docs/prereg/example.md", "# prereg\n")
        self.write(
            "config/feature-flags.yaml", self.yaml([flag(lifecycle="experiment", prereg="docs/prereg/missing.md")])
        )
        self.assertIn("prereg file does not exist", "\n".join(self.errors()))
        self.write("config/feature-flags.yaml", self.yaml([flag(lifecycle="experiment", prereg="/etc/passwd")]))
        self.assertIn("prereg must be a repo-relative path", "\n".join(self.errors()))
        self.write("config/feature-flags.yaml", self.yaml([flag(lifecycle="experiment", prereg="../outside.md")]))
        self.assertIn("prereg escapes the repository root", "\n".join(self.errors()))
        self.write(
            "config/feature-flags.yaml", self.yaml([flag(lifecycle="experiment", prereg="docs/prereg/example.md")])
        )
        self.assertEqual(self.errors(), [])

    def test_prereg_tracked_at_head_counts_in_sparse_checkout(self) -> None:
        # Cone-mode sparse checkouts do not materialise out-of-cone paths: a
        # prereg doc committed at HEAD but absent from the working tree is
        # still valid evidence and must not fail the registry check.
        self.write("docs/prereg/example.md", "# prereg\n")
        self.write(
            "config/feature-flags.yaml", self.yaml([flag(lifecycle="experiment", prereg="docs/prereg/example.md")])
        )
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        commit_env_identity = [
            "-c",
            "user.email=flags@example.test",
            "-c",
            "user.name=Flag Tests",
        ]
        subprocess.run(["git", "-C", str(self.root), *commit_env_identity, "add", "-A"], check=True, env=env)
        subprocess.run(
            ["git", "-C", str(self.root), *commit_env_identity, "commit", "-qm", "fixture"], check=True, env=env
        )
        (self.root / "docs/prereg/example.md").unlink()
        self.assertEqual(self.errors(), [])
        # A path in neither the working tree nor HEAD still fails closed.
        self.write(
            "config/feature-flags.yaml",
            self.yaml([flag(lifecycle="experiment", prereg="docs/prereg/never-committed.md")]),
        )
        self.assertIn("prereg file does not exist", "\n".join(self.errors()))

    def test_running_experiments_table_links_prereg_and_marks_overdue(self) -> None:
        running = flag(lifecycle="experiment", prereg="docs/prereg/example.md", review_by="2026-10-15")
        killed = flag(
            "KILLED_EXPERIMENT_ENABLED", lifecycle="experiment", decision="kill", prereg="docs/prereg/killed.md"
        )
        registry = {"flags": [running, killed], "ignore": [], "retired": []}
        early = render(self.root, registry, date(2026, 9, 24))
        late = render(self.root, registry, date(2026, 11, 1))
        self.assertLess(early.index("## Running experiments"), early.index("## Overdue for a decision"))
        section = early.split("## Running experiments", 1)[1].split("## Overdue for a decision", 1)[0]
        self.assertIn(
            "| `EXAMPLE_ENABLED` | on | tester | [docs/prereg/example.md](../../docs/prereg/example.md) | 2026-10-15 |",
            section,
        )
        self.assertNotIn("KILLED_EXPERIMENT_ENABLED", section)
        late_section = late.split("## Running experiments", 1)[1].split("## Overdue for a decision", 1)[0]
        self.assertIn("2026-10-15 OVERDUE", late_section)

    def test_fresh_render_with_running_experiments_has_no_drift(self) -> None:
        self.write("docs/prereg/example.md", "# prereg\n")
        self.write(
            "config/feature-flags.yaml", self.yaml([flag(lifecycle="experiment", prereg="docs/prereg/example.md")])
        )
        registry = load_registry(self.root / "config/feature-flags.yaml")
        self.write("backend/docs/feature-flag-registry.md", render(self.root, registry, date(2026, 9, 24)))
        self.assertEqual(check(self.root, as_of=date(2026, 10, 1))[0], [])

    def test_retired_name_must_not_be_read_and_is_exempt_from_stale(self) -> None:
        old = {
            "key": "old-kill-v1",
            "kind": "posthog",
            "retired": "2026-09-24",
            "reason": "Superseded",
            "posthog": {"row": "delete"},
        }
        self.write("config/feature-flags.yaml", self.yaml([flag()], retired=[old]))
        self.assertEqual(self.errors(), [])
        self.write("backend/other.py", "OLD_FLAG_KEY = 'old-kill-v1'\n")
        self.assertIn("retired name reintroduced: old-kill-v1", "\n".join(self.errors()))

    def test_retired_env_and_hardcoded_omit_posthog_and_duplicates_fail(self) -> None:
        hardcoded = {"key": "oldPrefKey", "kind": "hardcoded", "retired": "2026-09-26", "reason": "Removed"}
        self.write("config/feature-flags.yaml", self.yaml([flag()], retired=[hardcoded]))
        self.assertEqual(self.errors(), [])
        with_posthog = dict(hardcoded, posthog={"row": "delete"})
        self.write("config/feature-flags.yaml", self.yaml([flag()], retired=[with_posthog]))
        self.assertIn("retired hardcoded/env entries must omit posthog", "\n".join(self.errors()))
        bad_kind = {"key": "old-env-v1", "kind": "env", "retired": "2026-09-26", "reason": "Removed"}
        self.write("config/feature-flags.yaml", self.yaml([flag()], retired=[bad_kind]))
        self.assertEqual(self.errors(), [])
        self.write("backend/other.py", "import os\nos.getenv('old-env-v1')\n")
        self.assertIn("retired name reintroduced: old-env-v1", "\n".join(self.errors()))
        self.write("backend/other.py", "")
        duplicate = dict(hardcoded, key="EXAMPLE_ENABLED")
        self.write("config/feature-flags.yaml", self.yaml([flag()], retired=[duplicate]))
        self.assertIn("duplicate key or alias: EXAMPLE_ENABLED", "\n".join(self.errors()))


if __name__ == "__main__":
    unittest.main()
