#!/usr/bin/env python3
"""Hermetic self-tests for the dead-code ratchet.

Every test builds a disposable fake checkout (one reachable file, one dead
file, one allowlisted-with-reason file per area) and runs the real checker
against it via --root, so check/baseline/allowlist behavior executes end to
end. No network, no git history: pure filesystem analysis, like production.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPOSITORY_ROOT / ".github" / "scripts" / "check_dead_code.py"

from check_dead_code import scan_agent, scan_backend, scan_flutter, scan_windows  # noqa: E402


def run_checker(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), *extra],
        check=False,
        text=True,
        capture_output=True,
    )


def git_init(root: Path) -> None:
    """Make `root` a real repo so `git ls-files --ignored` can answer."""
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)


def git_stage_all(root: Path) -> None:
    """Track everything git does not ignore, so 'tracked' assertions mean it."""
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)


def write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_fake_checkout(root: Path) -> None:
    """One reachable, one dead, and one allowlisted-dead file per area."""
    # flutter: reachable via package:omi/, dead, allowlisted codegen input,
    # plus gen/ and *.g.dart files that the codegen exclusion must ignore.
    write(root, "app/lib/main.dart", "import 'package:omi/widgets/live.dart';\nvoid main() {}\n")
    write(root, "app/lib/widgets/live.dart", "class Live {}\n")
    write(root, "app/lib/widgets/dead_widget.dart", "class DeadWidget {}\n")
    write(root, "app/lib/widgets/contract_interface.dart", "abstract class Contract {}\n")
    write(root, "app/lib/widgets/gen/generated.dart", "// generated\n")
    write(root, "app/lib/widgets/model.g.dart", "// generated\n")
    # backend: live via `from utils import x` (package-submodule edge), dead,
    # allowlisted, entrypoint-class, and mention-only (demoted, never dead).
    write(root, "backend/routers/api.py", "from utils import live_helper\nfrom utils.other import helper\n\ndef route():\n    return live_helper.helper()\n")
    write(root, "backend/utils/__init__.py", "")
    write(root, "backend/utils/live_helper.py", "helper = lambda: 1\n")
    write(root, "backend/utils/other/__init__.py", "")
    write(root, "backend/utils/other/helper.py", "value = 2\n")
    write(root, "backend/utils/dead_module.py", "unused = True\n")
    write(root, "backend/utils/legacy_contract.py", "contract = True\n")
    write(root, "backend/utils/scratch_cli.py", "print('scratch')\nif __name__ == '__main__':\n    raise SystemExit(1)\n")
    write(root, "backend/utils/mentioned_only.py", "flag = False\n")
    write(root, "backend/routers/telemetry.py", "LABEL = 'utils.mentioned_only'\n")
    # agent: live via relative import, live via dynamic import(), dead, allowlisted.
    write(root, "desktop/macos/agent/src/index.ts", (
        "import { live } from './runtime/live';\n"
        "async function boot() {\n"
        "  const mod = await import('./runtime/dynamicLive');\n"
        "  return mod.value;\n"
        "}\n"
    ))
    write(root, "desktop/macos/agent/src/runtime/live.ts", "export const live = 1;\n")
    write(root, "desktop/macos/agent/src/runtime/dynamicLive.ts", "export const value = 2;\n")
    write(root, "desktop/macos/agent/src/runtime/dead.ts", "export const dead = 3;\n")
    write(root, "desktop/macos/agent/src/runtime/fixture_contract.ts", "export const schema = {};\n")
    # windows: entries main + preload + renderer/main; live via alias, live via
    # a string-spawned .js sibling; dead; allowlisted.
    write(root, "desktop/windows/src/main/index.ts", (
        "import { join } from 'node:path';\n"
        "import { live } from './live';\n"
        "new Worker(join(__dirname, 'spawned.js'));\n"
    ))
    write(root, "desktop/windows/src/main/live.ts", "export const live = 1;\n")
    write(root, "desktop/windows/src/main/spawned.ts", "export const worker = 2;\n")
    write(root, "desktop/windows/src/preload/index.ts", "export const bridge = {};\n")
    write(root, "desktop/windows/src/preload/index.d.ts", "export {};\n")
    write(root, "desktop/windows/src/renderer/src/main.tsx", "import { aliased } from '@renderer/aliasLive';\nconsole.log(aliased);\n")
    write(root, "desktop/windows/src/renderer/src/aliasLive.ts", "export const aliased = 3;\n")
    write(root, "desktop/windows/src/renderer/src/dead.tsx", "export const dead = 4;\n")
    write(root, "desktop/windows/src/renderer/src/fixture.testkit.ts", "export const kit = 5;\n")
    write(root, "desktop/windows/src/renderer/src/component.test.ts", "import '../main/live';\n")


def seed_allowlist(root: Path) -> None:
    allowlist = {
        "entries": [
            {"path": "app/lib/widgets/contract_interface.dart", "reason": "codegen contract inputs, unimported by design"},
            {"path": "backend/utils/legacy_contract.py", "reason": "lifecycle-permanent ops tooling"},
            {"path": "desktop/macos/agent/src/runtime/fixture_contract.ts", "reason": "contract test fixtures module"},
            {"path": "desktop/windows/src/renderer/src/fixture.testkit.ts", "reason": "intentional test infrastructure"},
        ]
    }
    path = root / ".github/scripts/dead_code"
    path.mkdir(parents=True, exist_ok=True)
    (path / "flutter.allowlist.json").write_text(json.dumps(allowlist), encoding="utf-8")
    (path / "backend.allowlist.json").write_text(json.dumps(allowlist), encoding="utf-8")
    (path / "agent.allowlist.json").write_text(json.dumps(allowlist), encoding="utf-8")
    (path / "windows.allowlist.json").write_text(json.dumps(allowlist), encoding="utf-8")


DEAD_BY_AREA = {
    "flutter": "app/lib/widgets/dead_widget.dart",
    "backend": "backend/utils/dead_module.py",
    "agent": "desktop/macos/agent/src/runtime/dead.ts",
    "windows": "desktop/windows/src/renderer/src/dead.tsx",
}


class DeadCodeRatchetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        build_fake_checkout(self.root)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_check_fails_on_each_area_dead_file_with_fix_hint(self) -> None:
        seed_allowlist(self.root)
        for area, dead in DEAD_BY_AREA.items():
            with self.subTest(area=area):
                result = run_checker(self.root, "--area", area)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(dead, result.stdout)
                self.assertIn("delete it, or add it to", result.stdout)
                self.assertIn(f"{area}.allowlist.json", result.stdout)

    def test_check_passes_once_dead_files_are_allowlisted_with_reason(self) -> None:
        seed_allowlist(self.root)
        for area, dead in DEAD_BY_AREA.items():
            allowlist_path = self.root / ".github/scripts/dead_code" / f"{area}.allowlist.json"
            data = json.loads(allowlist_path.read_text(encoding="utf-8"))
            data["entries"].append({"path": dead, "reason": "seeded dead file kept on purpose"})
            allowlist_path.write_text(json.dumps(data), encoding="utf-8")
        result = run_checker(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("dead_widget.dart", result.stdout)

    def test_generated_dart_files_are_never_dead(self) -> None:
        seed_allowlist(self.root)
        scan = scan_flutter(self.root)
        self.assertNotIn("app/lib/widgets/gen/generated.dart", scan.dead)
        self.assertNotIn("app/lib/widgets/model.g.dart", scan.dead)

    def test_backend_trap_edges_keep_live_files_alive_and_demote_the_rest(self) -> None:
        seed_allowlist(self.root)
        scan = scan_backend(self.root)
        # `from utils import live_helper` must edge to utils/live_helper.py.
        self.assertNotIn("backend/utils/live_helper.py", scan.dead)
        # `from utils.other import helper` must edge into the nested package.
        self.assertNotIn("backend/utils/other/helper.py", scan.dead)
        # __main__-guard files are entrypoint-class, not dead.
        self.assertNotIn("backend/utils/scratch_cli.py", scan.dead)
        # A dotted mention demotes to manual review instead of auto-dead.
        self.assertNotIn("backend/utils/mentioned_only.py", scan.dead)

    def test_ts_dynamic_import_alias_and_spawned_sibling_edges(self) -> None:
        seed_allowlist(self.root)
        self.assertNotIn("desktop/macos/agent/src/runtime/dynamicLive.ts", scan_agent(self.root).dead)
        windows_scan = scan_windows(self.root)
        self.assertNotIn("desktop/windows/src/main/spawned.ts", windows_scan.dead)
        self.assertNotIn("desktop/windows/src/renderer/src/aliasLive.ts", windows_scan.dead)
        # .d.ts and *.test.* files are excluded from the windows file set.
        self.assertNotIn("desktop/windows/src/preload/index.d.ts", windows_scan.dead)
        self.assertNotIn("desktop/windows/src/renderer/src/component.test.ts", windows_scan.dead)

    def test_allowlist_entry_without_reason_is_rejected(self) -> None:
        seed_allowlist(self.root)
        allowlist_path = self.root / ".github/scripts/dead_code/flutter.allowlist.json"
        allowlist_path.write_text(json.dumps({"entries": [{"path": "app/lib/widgets/dead_widget.dart"}]}), encoding="utf-8")
        result = run_checker(self.root, "--area", "flutter")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing a non-empty 'reason'", result.stdout)

    def test_update_baseline_round_trips_and_shrinks(self) -> None:
        seed_allowlist(self.root)
        seeded = run_checker(self.root, "--update-baseline")
        self.assertEqual(seeded.returncode, 0, seeded.stdout + seeded.stderr)
        for area, dead in DEAD_BY_AREA.items():
            baseline = self.root / ".github/scripts/dead_code" / f"{area}.baseline.json"
            data = json.loads(baseline.read_text(encoding="utf-8"))
            self.assertIn(dead, data["unreachable"], area)
        # The allowlisted files are the allowlist's job, not the floor's.
        flutter_floor = json.loads(
            (self.root / ".github/scripts/dead_code/flutter.baseline.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("app/lib/widgets/contract_interface.dart", flutter_floor["unreachable"])
        # With the floor seeded, check passes without any dead file allowlisted.
        result = run_checker(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # A newly dead file fails the ratchet.
        write(self.root, "app/lib/widgets/freshly_dead.dart", "class FreshlyDead {}\n")
        result = run_checker(self.root, "--area", "flutter")
        self.assertEqual(result.returncode, 1)
        self.assertIn("freshly_dead.dart", result.stdout)
        # Deleting a baselined file lets --update-baseline prune the entry.
        (self.root / DEAD_BY_AREA["backend"]).unlink()
        result = run_checker(self.root, "--update-baseline", "--area", "backend")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 pruned", result.stdout)
        floor = json.loads(
            (self.root / ".github/scripts/dead_code/backend.baseline.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("backend/utils/dead_module.py", floor["unreachable"])

    def test_stale_allowlist_entry_warns_without_failing(self) -> None:
        seed_allowlist(self.root)
        for area, dead in DEAD_BY_AREA.items():
            baseline = {
                "area": area,
                "unreachable": [dead],
            }
            (self.root / ".github/scripts/dead_code" / f"{area}.baseline.json").write_text(
                json.dumps(baseline), encoding="utf-8"
            )
        # contract_interface.dart is allowlisted but not dead -> note only.
        (self.root / "app/lib/widgets/contract_interface.dart").unlink()
        result = run_checker(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no longer dead", result.stdout)

    def test_gitignored_files_are_not_reported_dead(self) -> None:
        """A file git ignores is not in the tree CI checks out (#12476 shape)."""
        git_init(self.root)
        write(self.root, ".gitignore", "/app/lib/widgets/ignored_widget.dart\nbuild_output/\n")
        write(self.root, "app/lib/widgets/ignored_widget.dart", "class IgnoredWidget {}\n")
        # A file under an ignored *directory*: `ls-files --directory` collapses the
        # directory to one entry, so this matches through an ancestor.
        write(self.root, "app/lib/build_output/generated_widget.dart", "class GeneratedWidget {}\n")
        git_stage_all(self.root)

        scan = scan_flutter(self.root)

        self.assertNotIn("app/lib/widgets/ignored_widget.dart", scan.dead)
        self.assertNotIn("app/lib/build_output/generated_widget.dart", scan.dead)
        # The tracked dead file is still caught: this filters the checkout, not the verdict.
        self.assertIn(DEAD_BY_AREA["flutter"], scan.dead)

    def test_gitignored_backend_module_is_not_reported_dead(self) -> None:
        git_init(self.root)
        write(self.root, ".gitignore", "/backend/utils/local_secrets.py\n")
        write(self.root, "backend/utils/local_secrets.py", "TOKEN = 'x'\n")
        git_stage_all(self.root)

        scan = scan_backend(self.root)

        self.assertNotIn("backend/utils/local_secrets.py", scan.dead)
        self.assertIn(DEAD_BY_AREA["backend"], scan.dead)

    def test_gitignored_typescript_file_is_not_reported_dead(self) -> None:
        """scan_ts is shared by the agent and windows areas, so it needs its own case."""
        git_init(self.root)
        write(self.root, ".gitignore", "/desktop/macos/agent/src/runtime/localOnly.ts\n")
        write(self.root, "desktop/macos/agent/src/runtime/localOnly.ts", "export const localOnly = 1;\n")
        git_stage_all(self.root)

        scan = scan_agent(self.root)

        self.assertNotIn("desktop/macos/agent/src/runtime/localOnly.ts", scan.dead)
        self.assertIn(DEAD_BY_AREA["agent"], scan.dead)

    def test_gitignored_flutter_entry_fails_closed(self) -> None:
        """Reachability is seeded from the entry, so an ignored entry must error."""
        git_init(self.root)
        write(self.root, ".gitignore", "/app/lib/main.dart\n")
        git_stage_all(self.root)

        scan = scan_flutter(self.root)

        self.assertIn("gitignored", scan.error or "")
        self.assertEqual((), scan.dead)

    def test_scan_outside_a_git_repo_is_unchanged(self) -> None:
        """git cannot answer here, so the pure-filesystem behaviour must stand."""
        write(self.root, "app/lib/widgets/untracked_widget.dart", "class UntrackedWidget {}\n")

        scan = scan_flutter(self.root)

        self.assertIn("app/lib/widgets/untracked_widget.dart", scan.dead)
        self.assertIn(DEAD_BY_AREA["flutter"], scan.dead)

    def test_scan_is_deterministic_across_runs(self) -> None:
        seed_allowlist(self.root)
        for scanner in (scan_flutter, scan_backend, scan_agent, scan_windows):
            self.assertEqual(scanner(self.root), scanner(self.root))

    def test_missing_entry_files_fail_closed_with_guidance(self) -> None:
        (self.root / "desktop/macos/agent/src/index.ts").unlink()
        scan = scan_agent(self.root)
        self.assertIsNotNone(scan.error)
        assert scan.error
        self.assertIn("index.ts", scan.error)


if __name__ == "__main__":
    unittest.main()
