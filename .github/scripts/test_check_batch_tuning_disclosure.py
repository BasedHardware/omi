#!/usr/bin/env python3
"""Hermetic P6 fixtures; no cloud credentials, GitHub, or production access."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import check_batch_tuning_disclosure as check

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from git_test_env import clean_git_env

CONFIG = "backend/config/batch_pipeline.py"
CHART = "backend/charts/batch-pipeline-worker/values.yaml"
PUSHER = "backend/utils/pusher_worker.py"


def patch(*lines: str, path: str = CONFIG) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,10 +1,10 @@\n" + "\n".join(lines) + "\n"


class DisclosureTests(unittest.TestCase):
    def detect(self, *lines: str, path: str = CONFIG, existing: tuple[str, ...] = ()) -> tuple[set[str], set[str]]:
        return check.detect(patch(*lines, path=path), lambda value: value in existing)[:2]

    def test_numeric_config_and_hpa_require_numbers(self) -> None:
        for path, line, knob in (
            (CONFIG, "MAX_OWNER_DRAINS = 8", "MAX_OWNER_DRAINS"),
            (CHART, "maxReplicas: 12", "maxReplicas"),
            ("backend/charts/pusher/values.yaml", "minReplicas: 2", "minReplicas"),
            (PUSHER, "worker_pool = 16", "worker_pool"),
            (CONFIG, "page_size = 10", "page_size"),
        ):
            with self.subTest(line=line):
                knobs, states = self.detect("+" + line, path=path)
                self.assertEqual(knobs, {knob})
                self.assertTrue(check.validate(knobs, states, "")[0])
                self.assertFalse(check.validate(knobs, states, f"{knob}: before 4; after 8.")[0])

    def test_getenv_defaults_and_removed_lines(self) -> None:
        for line in (
            '+WORKERS = int(os.getenv("BATCH_IO_CONCURRENCY", "8"))',
            "-value = os.getenv('BATCH_IO_CONCURRENCY', '4')",
            "+value = os.getenv('BATCH_IO_CONCURRENCY', 8)",
        ):
            knobs, _ = self.detect(line)
            self.assertIn("BATCH_IO_CONCURRENCY", knobs)
            self.assertTrue(check.validate(knobs, set(), "")[0])

    def test_unchanged_values_are_not_tuning_but_full_numeric_changes_are(self) -> None:
        for old, new in (
            ("call(max_count=4096)", "call(max_count=4096, client=client)"),
            ("MAX_DRAINS = 8  # old comment", "MAX_DRAINS = 8  # new comment"),
            ("MAX_DRAINS = 1_000", "MAX_DRAINS = 1000"),
            ("os.getenv('IO_CONCURRENCY', '8')", "int(os.getenv('IO_CONCURRENCY', '8'))"),
        ):
            self.assertEqual(self.detect("-" + old, "+" + new), (set(), set()))
        for old, new in (("1_000", "1_500"), (".5", ".6"), ("1e3", "2e3"), ("-1", "-2")):
            self.assertEqual(self.detect("-MAX_DRAINS = " + old, "+MAX_DRAINS = " + new)[0], {"MAX_DRAINS"})

    def test_flags_comments_context_and_unrelated_paths_do_not_trigger(self) -> None:
        for line in (
            "+MAX_ENABLED = 1", "+MAX_PERCENT = 25", "+MAX_UIDS = 8",
            "+MAX_ALLOWLIST = 1", "+MAX_URL = 1", "+ENABLED = True",
            "+# MAX_OWNER_DRAINS = 8", "+  // maxReplicas: 8",
            " MAX_OWNER_DRAINS = 8", '+# status = "brand_new"',
        ):
            with self.subTest(line=line):
                self.assertEqual(self.detect(line), (set(), set()))
        self.assertEqual(self.detect("+maxReplicas: 8", path="backend/charts/unrelated/values.yaml"), (set(), set()))

    def test_quoted_documentation_and_log_examples_are_not_assignments(self) -> None:
        for line in ("+`MAX_RELEASE_ATTEMPTS=3` or above", '+log("MAX_DRAINS=8")', "+`os.getenv('IO_CONCURRENCY', '8')`"):
            with self.subTest(line=line):
                self.assertEqual(self.detect(line), (set(), set()))

    def test_numeric_tokens_inside_strings_and_inline_comments_are_not_assignments(self) -> None:
        for line in (
            '+log("effective_page_rows=%d max_rows_per_second=20", rows)',
            "+log('capacity max_count=8')",
            '+log("env os.getenv(\'IO_CONCURRENCY\', \'8\')")',
            "+other = 1  # MAX_DRAINS = 8",
            "+prose with `MAX_DRAINS=8` in the middle",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.detect(line), (set(), set()))

    def test_before_after_same_section_name_and_boundaries(self) -> None:
        for body in (
            "before 4 after 8", "MAX_DRAINS before 4", "MAX_DRAINS after 8",
            "## Before\nMAX_DRAINS before 4\n## After\nafter 8",
            "OTHER_MAX_DRAINS before 4 after 8",
            "<!-- MAX_DRAINS before 4 after 8 -->",
            "MAX_DRAINS before " + "x" * 121 + "4 after 8",
        ):
            with self.subTest(body=body):
                self.assertTrue(check.validate({"MAX_DRAINS"}, set(), body)[0])
        for body in (
            "## Tuning\nMAX_DRAINS before 4\nafter 8",
            "MAX_DRAINS after 8, before 4",
            "## MAX_DRAINS\nbefore 4 after 8",
            "MAX_DRAINS before 4 after 8",  # one matched knob is sufficient
        ):
            self.assertFalse(check.validate({"MAX_DRAINS", "MAX_OTHER"}, set(), body)[0])

    def test_new_state_needs_literal_and_exit(self) -> None:
        knobs, states = self.detect('+status = "awaiting_repair"')
        self.assertEqual(states, {"awaiting_repair"})
        for body in ("", "awaiting_repair", "exit through recovery", "not_awaiting_repair exits"):
            self.assertTrue(check.validate(knobs, states, body)[0])
        for exit_word in ("exit", "terminal", "dead-letter", "re-entry", "reentry", "clear", "recover"):
            self.assertFalse(check.validate(knobs, states, f"awaiting_repair: {exit_word} via retry")[0])
        self.assertFalse(check.validate(knobs, states, "## State\nawaiting_repair\n## Recovery\nrecover via retry")[0])

    def test_code_examples_cannot_disclose_or_waive(self) -> None:
        for example in (
            "Numbers-waived: example only\nState-exit-waived: example only",
            "MAX_DRAINS before 4 after 8\nawaiting_repair exits on retry",
            "MAX_DRAINS from 4 to 8\nawaiting_repair recovers",
            "MAX_DRAINS new: 8\nawaiting_repair exits",
        ):
            indented = "\n".join("    " + line for line in example.splitlines())
            tabbed = "\n".join("\t" + line for line in example.splitlines())
            for wrapped in (
                f"```text\n{example}\n```", f"~~~\n{example}\n~~~", f"`{example}`", f"``{example}``", f"```\n{example}",
                indented, f"Example:\n\n{indented}", f"Example:\n\n{tabbed}", f"<!--\n{example}", f"<!-- note -->\n<!--\n{example}",
                f"## Example\n{indented}", f"Example:\n\n" + "\n".join("   \t" + line for line in example.splitlines()),
                f"> Example:\n>\n" + "\n".join(">     " + line for line in example.splitlines()),
                "> ```\n" + "\n".join("> " + line for line in example.splitlines()) + "\n> ```",
            ):
                with self.subTest(wrapped=wrapped):
                    errors, notices = check.validate({"MAX_DRAINS"}, {"awaiting_repair"}, wrapped, {"MAX_DRAINS"})
                    self.assertEqual(len(errors), 2)
                    self.assertEqual(notices, [])
        self.assertTrue(check.validate({"MAX_DRAINS"}, set(), "MAX_DRAINS `before 4 after 8`")[0])
        self.assertFalse(check.validate({"MAX_DRAINS"}, set(), "```\nexample\n```\nMAX_DRAINS from 4 to 8")[0])
        # Indentation only counts as code after a blank line; list continuations stay prose.
        self.assertFalse(check.validate({"MAX_DRAINS"}, set(), "- MAX_DRAINS\n    from 4 to 8")[0])
        self.assertFalse(check.validate({"MAX_DRAINS"}, set(), "    example\n\nMAX_DRAINS from 4 to 8")[0])
        self.assertFalse(check.validate({"MAX_DRAINS"}, set(), "> MAX_DRAINS from 4 to 8")[0])
        for title in ('"MAX_DRAINS from 4 to 8"', "'MAX_DRAINS from 4 to 8'", "(MAX_DRAINS from 4 to 8)"):
            self.assertTrue(check.validate({"MAX_DRAINS"}, set(), f"[notes](/guide {title})")[0])
            self.assertTrue(check.validate({"MAX_DRAINS"}, set(), f"[notes](/wiki/Foo_(bar) {title})")[0])
            self.assertTrue(check.validate({"MAX_DRAINS"}, set(), f"[notes](</a b> {title})")[0])
        self.assertFalse(check.validate({"MAX_DRAINS"}, set(), "[MAX_DRAINS from 4 to 8](/guide)")[0])
        self.assertTrue(check.validate({"MAX_DRAINS"}, set(), "> ## Tuning\n> MAX_DRAINS before 4\n> ## Separate\n> after 8")[0])

    def test_from_to_and_arrow_disclosures(self) -> None:
        for body in (
            "MAX_DRAINS from 6 to 4", "MAX_DRAINS: 6 -> 4", "MAX_DRAINS: 6 → 4",
            "MAX_DRAINS from min 6 / max 12 to min 4 / max 8",
            "MAX_DRAINS: 1e3 → 1_500", "MAX_DRAINS: -.5 -> .6", "6 → 4 for MAX_DRAINS",
        ):
            with self.subTest(body=body):
                self.assertFalse(check.validate({"MAX_DRAINS"}, set(), body)[0])
        for body in ("OTHER_MAX_DRAINS 6 -> 4", "MAX_DRAINS from 6", "MAX_DRAINS -> 4", "MAX_DRAINS\n## Other\n6 -> 4"):
            self.assertTrue(check.validate({"MAX_DRAINS"}, set(), body)[0])
        for wording in ("from 6 to 4", "6 -> 4", "6 → 4", "new: 4", "initial 4"):
            self.assertTrue(check.validate({"MAX_DRAINS"}, set(), "MAX_DRAINS " + "x" * 121 + wording, {"MAX_DRAINS"})[0])

    def test_initial_disclosure_only_for_a_knob_without_removed_numeric_value(self) -> None:
        for lines, new in (
            (("+MAX_DRAINS = 8",), {"MAX_DRAINS"}),
            (("-MAX_DRAINS = None", "+MAX_DRAINS = 8"), {"MAX_DRAINS"}),
            (("-MAX_DRAINS = 4", "+MAX_DRAINS = 8"), set()),
            (("-MAX_DRAINS = 4",), set()),
            (("-os.getenv('IO_CONCURRENCY', '4')", "+os.getenv('IO_CONCURRENCY', '8')"), set()),
            (("+os.getenv('IO_CONCURRENCY', '8')",), {"IO_CONCURRENCY"}),
        ):
            knobs, states, new_knobs = check.detect(patch(*lines), lambda _: False)
            self.assertEqual(new_knobs, new)
            for knob in knobs:
                for wording in ("new: 8", "initial 8"):
                    self.assertEqual(bool(check.validate(knobs, states, f"{knob}: {wording}", new_knobs)[0]), not bool(new))
            self.assertFalse(check.validate(knobs, states, "Numbers-waived: no prior value", new_knobs)[0])
        self.assertTrue(check.validate({"MAX_DRAINS", "MAX_OTHER"}, set(), "MAX_DRAINS new: 8", {"MAX_OTHER"})[0])

    def test_state_literals_require_direct_assignment_or_comparison(self) -> None:
        for line in (
            "state = 'retry_pending'", "state == 'retry_pending'", "'retry_pending' == state",
            "status='retry_pending'", "update(status='retry_pending')", "{'state': 'retry_pending'}",
            "job['state'] = 'retry_pending'", "job.state != 'retry_pending'",
            "job_state = 'retry_pending'", "phase='retry_pending'", "disposition='retry_pending'",
            "outcome='retry_pending'", "reason='retry_pending'",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.detect('+' + line)[1], {"retry_pending"})
        for line in (
            "logger.info('request state=%s', 'retry_pending')",
            "logger.info('state = ', 'retry_pending')",
            "logger.info('state', 'retry_pending')", "description = 'retry_pending'",
            "'retry_pending'", """log('state == "retry_pending"')""",
            "'state' == 'retry_pending'",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.detect(' state = current', '+' + line)[1], set())

    def test_state_distance_hunk_and_file_boundaries(self) -> None:
        self.assertEqual(self.detect(' status = (', '+"awaiting_repair"')[1], {"awaiting_repair"})
        self.assertEqual(self.detect(' status = (', ' ', ' ', '+"awaiting_repair"')[1], {"awaiting_repair"})
        self.assertEqual(self.detect(' status = (', ' x', ' x', '+"awaiting_repair"')[1], set())
        self.assertEqual(self.detect(' status = (', ' x', ' x', ' x', '+"awaiting_repair"')[1], set())
        self.assertEqual(self.detect('-status = "removed_state"', '+value = "unrelated_word"')[1], set())
        self.assertEqual(self.detect(' status = "old_state"', '+value = 2')[1], set())
        self.assertEqual(check.detect(patch('+status = "known_state"') + patch('+name = "unrelated_word"'), lambda _: True), (set(), set(), set()))

    def test_existing_states_never_trigger(self) -> None:
        self.assertEqual(self.detect('+status = "awaiting_repair"', existing=("awaiting_repair",)), (set(), set()))

    def test_metadata_next_to_state_is_not_a_new_state(self) -> None:
        for line in (
            "+**({'registration_origin': 'restore'} if restoring else {})",
            "+job['new_metadata_key'] = value", "+job.get('new_metadata_key')",
            "+description = 'new_description'",
            "+getattr(error, 'store_tables', 'n/a')",
            "+Counter('omi_new_metric_total', 'Description')",
            "+Counter('omi_new_metric_total', 'Description', ['outcome'])",
        ):
            with self.subTest(line=line):
                # outcome is a pre-existing label name, not a new metric value.
                self.assertEqual(self.detect(' status = current', line, existing=("outcome",)), (set(), set()))
        self.assertEqual(self.detect(' status = current', '+Counter(', "+    'omi_new_metric_total',", '+)')[1], set())
        self.assertEqual(self.detect("+job['state'] = 'awaiting_repair'")[1], {"awaiting_repair"})
        self.assertEqual(self.detect("+{'state': 'awaiting_repair'}")[1], {"awaiting_repair"})

    def test_unrelated_state_context_does_not_cross_hunks_or_files(self) -> None:
        diff = patch(' status = "known_state"') + '@@ -90 +90 @@\n+label = "unrelated_word"\n'
        diff += patch('+name = "another_word"', path=PUSHER)
        self.assertEqual(check.detect(diff, lambda _: False), (set(), set(), set()))

    def test_manifest_selects_both_lanes_and_requires_body(self) -> None:
        from run_checks import load_manifest, resolve_checks

        manifest = load_manifest(ROOT / ".github/checks-manifest.yaml")
        for lane in ("local", "ci"):
            for path in (CONFIG, CHART, PUSHER, ".github/scripts/test_check_batch_tuning_disclosure.py"):
                with self.subTest(lane=lane, path=path):
                    selected = resolve_checks(manifest, [path], lane, platform="linux")
                    matches = [item for item in selected if item.id == "batch-pipeline-tuning-disclosure"]
                    self.assertEqual(len(matches), 1)
                    self.assertTrue(matches[0].requires_pr_body)

    def test_deleted_file_keeps_removed_knob(self) -> None:
        diff = f"diff --git a/{CONFIG} b/{CONFIG}\n--- a/{CONFIG}\n+++ /dev/null\n@@ -1 +0,0 @@\n-MAX_DRAINS = 4\n"
        self.assertEqual(check.detect(diff, lambda _: False), ({"MAX_DRAINS"}, set(), set()))

    def test_both_waivers_require_reasons_and_echo_them(self) -> None:
        for body in ("Numbers-waived:\nState-exit-waived:", "<!-- Numbers-waived: example\nState-exit-waived: example -->"):
            self.assertEqual(len(check.validate({"MAX_DRAINS"}, {"awaiting_repair"}, body)[0]), 2)
        body = "Numbers-waived: offline comparison pending\nState-exit-waived: diagnostic label only"
        errors, notices = check.validate({"MAX_DRAINS"}, {"awaiting_repair"}, body)
        self.assertEqual(errors, [])
        self.assertEqual(notices, body.splitlines())
        self.assertEqual(len(check.validate({"MAX_DRAINS"}, {"awaiting_repair"}, body.splitlines()[0])[0]), 1)


class GitFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="p6-fixture-")
        self.root = Path(self.temp.name)
        self.env = clean_git_env()
        self.git("init", "-q")
        self.write(CONFIG, 'MAX_DRAINS = 4\nstatus = "known_state"\n')
        self.write("elsewhere.txt", "cross_file_state\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/main", self.base)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "-c", "init.defaultBranch=main",
             "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args],
            cwd=self.root, env=self.env, text=True,
        )

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def run_check(self, body: str = "", base: str = "origin/main") -> subprocess.CompletedProcess[str]:
        self.git("add", ".")
        self.git("commit", "-qm", "fixture change", "--allow-empty")
        # Isolate body from Git and propagate a contaminated parent environment:
        # scripts/pr-preflight scrubs this before invoking manifest commands.
        with tempfile.TemporaryDirectory() as inputs:
            body_file = Path(inputs) / "body.md"
            body_file.write_text(body, encoding="utf-8")
            env = self.env.copy()
            env["OMI_PR_BODY_FILE"] = str(body_file)
            return subprocess.run(
                [sys.executable, str(Path(check.__file__)), "--root", str(self.root), "--base", base],
                env=env, capture_output=True, text=True,
            )

    def test_cli_failure_disclosure_and_waivers_echo(self) -> None:
        self.write(CONFIG, 'MAX_DRAINS = 8\nstatus = "awaiting_repair"\n')
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("before and after", result.stderr)
        self.assertIn("awaiting_repair", result.stderr)
        result = self.run_check("MAX_DRAINS before 4 after 8. awaiting_repair exits on retry.")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_check("Numbers-waived: no load fixture\nState-exit-waived: diagnostic only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Numbers-waived: no load fixture", result.stdout)
        self.assertIn("State-exit-waived: diagnostic only", result.stdout)

    def test_whole_base_tree_and_existing_literals(self) -> None:
        self.write(CONFIG, 'status = "known_state"\nphase = "cross_file_state"\n')
        # Avoid the removed MAX_DRAINS tuning requirement in this state fixture.
        result = self.run_check("MAX_DRAINS before 4 after 0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0 new states", result.stdout)

    def test_cli_initial_value_requires_no_removed_numeric_assignment(self) -> None:
        self.write(CONFIG, 'MAX_DRAINS = 4\nMAX_NEW = 8\nstatus = "known_state"\n')
        result = self.run_check("MAX_NEW initial 8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write(CONFIG, 'MAX_DRAINS = 8\nstatus = "known_state"\n')
        result = self.run_check("MAX_DRAINS new: 8")
        self.assertEqual(result.returncode, 1, result.stderr)
        result = self.run_check("MAX_DRAINS 4 → 8")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_batched_lookup_handles_overlap_absence_and_binary_content(self) -> None:
        self.write("fixture.bin", b"\x00unique_binary_state\x00".decode())
        self.git("add", ".")
        self.git("commit", "-qm", "binary fixture")
        self.assertEqual(
            check.existing_literals(self.root, "HEAD", {"known_state", "known", "cross_file_state", "unique_binary_state", "absent_state"}),
            {"known_state", "known", "cross_file_state", "unique_binary_state"},
        )

    def test_merge_base_not_current_base_tip(self) -> None:
        self.git("checkout", "-qb", "base-advance")
        self.write("elsewhere.txt", "future_state\n")
        self.git("add", ".")
        self.git("commit", "-qm", "advance base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("checkout", "-q", "--detach", self.base)
        self.write(CONFIG, 'MAX_DRAINS = 4\nstatus = "future_state"\n')
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("future_state", result.stderr)

    def test_missing_base_fails_closed(self) -> None:
        result = self.run_check(base="missing-ref")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("merge-base", result.stderr)
        with self.assertRaisesRegex(RuntimeError, "git grep"):
            check.existing_literals(self.root, "missing-ref", {"missing_state"})

    def test_fixture_init_scrubs_inherited_git_environment(self) -> None:
        config = self.root / ".git/config"
        before = config.read_bytes()
        inherited = {"GIT_DIR": str(self.root / ".git"), "GIT_WORK_TREE": str(self.root), "GIT_NAMESPACE": "caller"}
        with tempfile.TemporaryDirectory(prefix="p6-isolation-") as other, mock.patch.dict(os.environ, inherited):
            subprocess.run(["git", "init", "-q", other], env=clean_git_env(), check=True, capture_output=True)
            self.assertTrue((Path(other) / ".git/config").is_file())
        self.assertEqual(config.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
