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
        "fail": "closed",
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


class RegistryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="omi-flag-registry-")
        self.root = Path(self.temp.name)
        subprocess.run(
            ["git", "init", "-q"],
            cwd=self.root,
            check=True,
            env={key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
        )
        self.write("backend/service.py", "import os\nENABLED_NAME = 'EXAMPLE_ENABLED'\nos.getenv(ENABLED_NAME)\n")
        self.write("config/feature-flags.yaml", self.yaml([flag()]))

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
        return check(self.root, check_render=False, as_of=date(2026, 10, 1))[0]

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

    def test_deploy_key_missing_from_registry(self) -> None:
        self.write("backend/deploy/runtime_env/_base.yaml", "services:\n  MISSING_KILL_SWITCH:\n    value: false\n")
        self.assertTrue(
            any(
                "backend/deploy/runtime_env/_base.yaml:2: undeclared registry flag: MISSING_KILL_SWITCH" in e
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
        self.assertTrue(any("within the 7-day grace: EXAMPLE_ENABLED (review_by 2026-10-13)" in w for w in warnings))
        errors, _ = check(self.root, check_render=False, as_of=date(2026, 10, 21))
        self.assertIn("review overdue beyond the 7-day grace: EXAMPLE_ENABLED", "\n".join(errors))

    def test_review_overdue_exception_is_dated_and_prints_loudly(self) -> None:
        self.write("config/feature-flags.yaml", self.yaml([flag(review_by="2026-10-13")]))
        exception = {"EXAMPLE_ENABLED": {"expires": "2026-11-20", "reason": "David must decide"}}
        with mock.patch("check_feature_flag_registry.REVIEW_OVERDUE", exception):
            errors, warnings = check(self.root, check_render=False, as_of=date(2026, 10, 21))
            self.assertEqual(errors, [])
            self.assertTrue(any("BLOCKER for David: review_overdue exception EXAMPLE_ENABLED" in w for w in warnings))
            errors, _ = check(self.root, check_render=False, as_of=date(2026, 11, 21))
            self.assertIn("review_overdue exception expired 2026-11-20", "\n".join(errors))

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
        self.assertIn("duplicate ramp/allowlist declaration: EXAMPLE_PERCENT", "\n".join(errors))
        self.assertIn("duplicate ramp/allowlist declaration: EXAMPLE_UID_ALLOWLIST", "\n".join(errors))

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
