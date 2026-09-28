#!/usr/bin/env python3
"""Hermetic tests for scripts/resolve-registry-conflict.

The two failures that made tonight's merge-forwards drop content are encoded
as naive strategies that must fail the postconditions the resolver satisfies.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CLI = REPOSITORY_ROOT / "scripts" / "resolve-registry-conflict"
LOADER = importlib.machinery.SourceFileLoader("resolve_registry_conflict", str(CLI))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

GIT_ISOLATION = [
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "maintenance.auto=false",
    "-c",
    "gc.auto=0",
]

MANIFEST = ".github/checks-manifest.yaml"
SPINE = "contracts/spine/files.json"
ALLOWLIST = ".github/scripts/dead_code/flutter.allowlist.json"

BASE_MANIFEST = """# header comment must survive
checks:
  - id: shared
    command: ["python3", "old.py", "--changed-files", "{changed_files}"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "base shared"

exempt:
  - path: "keep.py"
    reason: "must stay exempt"
"""

OURS_MANIFEST = """# header comment must survive
checks:
  - id: shared
    command: ["python3", "old.py", "--changed-files", "{changed_files}"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "base shared"

  - id: ours-only
    command: ["python3", "ours.py"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "only on the branch"

exempt:
  - path: "keep.py"
    reason: "must stay exempt"
"""

THEIRS_MANIFEST = """# header comment must survive
checks:
  - id: shared
    command: ["python3", "old.py", "--base", "{base}", "--head", "{head}"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "base shared"

  - id: main-only
    command: ["python3", "main.py"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "only on main"

exempt:
  - path: "keep.py"
    reason: "must stay exempt"
"""

BOTH_EDITED_OURS = """checks:
  - id: shared
    command: ["python3", "old.py", "--changed-files", "{changed_files}"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "branch edited the reason"

exempt:
  - path: "keep.py"
    reason: "must stay exempt"
"""

BOTH_EDITED_THEIRS = """checks:
  - id: shared
    command: ["python3", "old.py", "--base", "{base}"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "base shared"

exempt:
  - path: "keep.py"
    reason: "must stay exempt"
"""


def naive_append_main_only(ours: str, theirs: str) -> str:
    """Tonight's first mistake: append main-only check blocks at end-of-file."""

    ours_doc = MOD.parse_document(MANIFEST, ours)
    theirs_doc = MOD.parse_document(MANIFEST, theirs)
    ours_ids = {item.key for container in ours_doc.containers if container.name == "checks" for item in container.items}
    extras = [
        item.text.rstrip("\n")
        for container in theirs_doc.containers
        if container.name == "checks"
        for item in container.items
        if item.key not in ours_ids
    ]
    return ours.rstrip() + "\n" + "\n".join(extras) + "\n"


def naive_ours_plus_main_ids(ours: str, theirs: str) -> str:
    """Tonight's second mistake: keep ours (including stale shared ids) and add main-only ids."""

    return naive_append_main_only(ours, theirs)


def parsed_check_ids(text: str) -> list[str]:
    sections = MOD.parse_yaml_subset(text)
    return [str(row.get("id", "")) for row in sections.get("checks", []) if row.get("id")]


def parsed_exempt_ids(text: str) -> list[str]:
    sections = MOD.parse_yaml_subset(text)
    return [str(row.get("id", "")) for row in sections.get("exempt", []) if "id" in row]


def parsed_shared_command(text: str) -> list[str]:
    sections = MOD.parse_yaml_subset(text)
    for row in sections.get("checks", []):
        if row.get("id") == "shared":
            command = row.get("command", [])
            return list(command) if isinstance(command, list) else []
    raise AssertionError("shared check missing")


class RegistryConflictResolverTests(unittest.TestCase):
    def test_naive_append_lands_inside_exempt(self) -> None:
        naive = naive_append_main_only(OURS_MANIFEST, THEIRS_MANIFEST)
        self.assertIn("main-only", naive)
        self.assertNotIn("main-only", parsed_check_ids(naive))
        self.assertIn("main-only", parsed_exempt_ids(naive))
        with self.assertRaises(MOD.ResolverError) as caught:
            MOD.verify_result(
                MANIFEST,
                MOD.parse_document(MANIFEST, BASE_MANIFEST),
                MOD.parse_document(MANIFEST, OURS_MANIFEST),
                MOD.parse_document(MANIFEST, THEIRS_MANIFEST),
                naive,
            )
        self.assertIn("exempt", str(caught.exception))

        resolved = MOD.resolve_text(MANIFEST, BASE_MANIFEST, OURS_MANIFEST, THEIRS_MANIFEST)
        self.assertEqual(parsed_check_ids(resolved), ["shared", "ours-only", "main-only"])
        self.assertEqual(parsed_exempt_ids(resolved), [])
        self.assertIn('reason: "must stay exempt"', resolved)
        self.assertTrue(resolved.startswith("# header comment must survive"))

    def test_naive_union_reverts_main_edit_to_shared_id(self) -> None:
        naive = naive_ours_plus_main_ids(OURS_MANIFEST, THEIRS_MANIFEST)
        self.assertEqual(
            parsed_shared_command(naive),
            ["python3", "old.py", "--changed-files", "{changed_files}"],
        )
        self.assertIn("--base", parsed_shared_command(THEIRS_MANIFEST))

        resolved = MOD.resolve_text(MANIFEST, BASE_MANIFEST, OURS_MANIFEST, THEIRS_MANIFEST)
        self.assertEqual(
            parsed_shared_command(resolved),
            ["python3", "old.py", "--base", "{base}", "--head", "{head}"],
        )
        self.assertIn("ours-only", parsed_check_ids(resolved))
        self.assertIn("main-only", parsed_check_ids(resolved))

    def test_both_sides_edited_same_key_refuses_and_names_path(self) -> None:
        with self.assertRaises(MOD.ResolverError) as caught:
            MOD.resolve_text(MANIFEST, BASE_MANIFEST, BOTH_EDITED_OURS, BOTH_EDITED_THEIRS)
        message = str(caught.exception)
        self.assertIn(MANIFEST, message)
        self.assertIn("shared", message)
        self.assertIn("human has to read it", message)

    def test_refuses_agents_md(self) -> None:
        with self.assertRaises(MOD.ResolverError) as caught:
            MOD.resolve_text("app/AGENTS.md", "a", "b", "c")
        self.assertIn("11411", str(caught.exception))
        self.assertIn("not mechanical", str(caught.exception))

    def test_refuses_unknown_path(self) -> None:
        with self.assertRaises(MOD.ResolverError) as caught:
            MOD.resolve_text("random.yaml", "a", "b", "c")
        self.assertIn("random.yaml", str(caught.exception))

    def test_spine_files_json_union_without_reserialising_existing_pairs(self) -> None:
        base = '{\n  "app/a.dart": "C1"\n}\n'
        ours = '{\n  "app/a.dart": "C1",\n  "app/ours.dart": "C3"\n}\n'
        theirs = '{\n  "app/a.dart": "C1",\n  "app/main.dart": "C1"\n}\n'
        resolved = MOD.resolve_text(SPINE, base, ours, theirs)
        parsed = json_loads(resolved)
        self.assertEqual(parsed["app/a.dart"], "C1")
        self.assertEqual(parsed["app/ours.dart"], "C3")
        self.assertEqual(parsed["app/main.dart"], "C1")
        self.assertIn('"app/a.dart": "C1"', resolved)
        self.assertNotIn('{"app/a.dart":', resolved.replace(" ", ""))

    def test_same_content_different_key_order_is_not_both_edited(self) -> None:
        """A reorder of equal keys is not an owner disagreement.

        pick_side compares canonical(parsed) per key (json.dumps sort_keys), not
        file order. Reordering shared entries, or fields inside one entry, must
        resolve rather than refuse.
        """

        base = '{\n  "app/a.dart": "C1",\n  "app/b.dart": "C1"\n}\n'
        ours = '{\n  "app/a.dart": "C1",\n  "app/b.dart": "C1",\n  "app/ours.dart": "C3"\n}\n'
        theirs = '{\n  "app/b.dart": "C1",\n  "app/a.dart": "C1",\n  "app/main.dart": "C1"\n}\n'
        resolved = MOD.resolve_text(SPINE, base, ours, theirs)
        parsed = json_loads(resolved)
        self.assertEqual(parsed["app/a.dart"], "C1")
        self.assertEqual(parsed["app/b.dart"], "C1")
        self.assertEqual(parsed["app/ours.dart"], "C3")
        self.assertEqual(parsed["app/main.dart"], "C1")

        ours_fields = """checks:
  - id: shared
    reason: "base shared"
    command: ["python3", "old.py"]
    triggers: ["all"]
    lanes: ["local", "ci"]

exempt:
  - path: "keep.py"
    reason: "must stay exempt"
"""
        theirs_fields = """checks:
  - id: shared
    command: ["python3", "old.py"]
    triggers: ["all"]
    lanes: ["local", "ci"]
    reason: "base shared"

exempt:
  - path: "keep.py"
    reason: "must stay exempt"
"""
        resolved_fields = MOD.resolve_text(MANIFEST, ours_fields, ours_fields, theirs_fields)
        self.assertEqual(parsed_check_ids(resolved_fields), ["shared"])
        self.assertEqual(parsed_shared_command(resolved_fields), ["python3", "old.py"])

    def test_allowlist_union_by_path(self) -> None:
        base = """{
  "entries": [
    {
      "path": "app/lib/keep.dart",
      "reason": "shared"
    }
  ]
}
"""
        ours = """{
  "entries": [
    {
      "path": "app/lib/keep.dart",
      "reason": "shared"
    },
    {
      "path": "app/lib/ours.dart",
      "reason": "branch"
    }
  ]
}
"""
        theirs = """{
  "entries": [
    {
      "path": "app/lib/keep.dart",
      "reason": "shared"
    },
    {
      "path": "app/lib/main.dart",
      "reason": "main"
    }
  ]
}
"""
        resolved = MOD.resolve_text(ALLOWLIST, base, ours, theirs)
        paths = [entry["path"] for entry in json_loads(resolved)["entries"]]
        self.assertEqual(paths, ["app/lib/keep.dart", "app/lib/ours.dart", "app/lib/main.dart"])

    def test_cli_resolves_git_merge_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            git(root, "init", "-q")
            git(root, "config", "user.email", "resolver@example.test")
            git(root, "config", "user.name", "Resolver Test")
            manifest = root / MANIFEST
            manifest.parent.mkdir(parents=True)
            manifest.write_text(BASE_MANIFEST, encoding="utf-8")
            git(root, "add", MANIFEST)
            git(root, "commit", "-qm", "base")
            git(root, "branch", "-M", "main")
            git(root, "switch", "-qc", "feature")
            manifest.write_text(OURS_MANIFEST, encoding="utf-8")
            git(root, "add", MANIFEST)
            git(root, "commit", "-qm", "feature adds ours-only")
            git(root, "switch", "-q", "main")
            manifest.write_text(THEIRS_MANIFEST, encoding="utf-8")
            git(root, "add", MANIFEST)
            git(root, "commit", "-qm", "main adds a check and edits shared")
            git(root, "switch", "-q", "feature")
            result = git(root, "merge", "--no-edit", "main", check=False)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            completed = run_cli(root, MANIFEST)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            text = manifest.read_text(encoding="utf-8")
            self.assertEqual(parsed_check_ids(text), ["shared", "ours-only", "main-only"])
            self.assertEqual(
                parsed_shared_command(text),
                ["python3", "old.py", "--base", "{base}", "--head", "{head}"],
            )
            self.assertEqual(parsed_exempt_ids(text), [])


def json_loads(text: str) -> object:
    import json

    return json.loads(text)


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["git", *GIT_ISOLATION, *args]
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    result = subprocess.run(command, cwd=root, check=False, text=True, capture_output=True, env=environment)
    if check and result.returncode:
        raise AssertionError(f"{command} failed: {result.stderr}")
    return result


def run_cli(root: Path, path: str) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.run(
        [sys.executable, str(CLI), "--root", str(root), path],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
        env=environment,
    )


if __name__ == "__main__":
    unittest.main()
