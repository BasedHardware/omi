"""Regression tests for plugins-free example sdks/python-cli/examples/conversations_to_markdown.py.

Standard library only (unittest), so the suite runs under plain python3 in the
manifest lane. The example script is not an importable package, so it is loaded
by path with importlib.

Covers #14277: the exporter built output names from the date, the title slug, and
only the first eight sanitized characters of the conversation id, then called
Path.write_text with no collision handling. Two conversations titled "Meeting"
on 2026-09-17 with ids sharing an eight-character prefix both resolved to
2026-09-17_meeting_12345678.md, so the second note silently overwrote the first
while the summary still reported both as exported. Distinct conversations must
produce distinct files; re-exporting the same conversation id must still target
the same file so repeat runs stay idempotent.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parent / "conversations_to_markdown.py"


def load_module():
    spec = importlib.util.spec_from_file_location("conversations_to_markdown_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def conversation(conv_id, title, started_at, overview):
    return {
        "id": conv_id,
        "started_at": started_at,
        "source": "omi",
        "structured": {"title": title, "category": "work", "overview": overview},
    }


def run_exporter(payload, output_dir):
    """Invoke the example script as a user would, via its CLI entrypoint."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "conversations.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(source), "--output-dir", str(output_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
    return result


class CollisionSafeNamingTests(unittest.TestCase):
    def test_ids_sharing_a_prefix_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "notes"
            result = run_exporter(
                [
                    conversation("12345678-1111-4111-8111-111111111111", "Meeting",
                                 "2026-09-17T10:00:00Z", "FIRST body"),
                    conversation("12345678-2222-4222-8222-222222222222", "Meeting",
                                 "2026-09-17T11:00:00Z", "SECOND body"),
                ],
                out,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            notes = sorted(out.glob("*.md"))
            self.assertEqual(len(notes), 2, "both conversations must survive as separate notes")
            bodies = [n.read_text(encoding="utf-8") for n in notes]
            self.assertTrue(any("FIRST body" in b for b in bodies))
            self.assertTrue(any("SECOND body" in b for b in bodies))
            # The reported count must match what was actually written.
            self.assertIn("Successfully exported 2 conversation(s)", result.stdout)

    def test_three_way_prefix_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "notes"
            result = run_exporter(
                [
                    conversation("abcdef12-0000-4000-8000-000000000001", "Sync", "2026-01-01T00:00:00Z", "one"),
                    conversation("abcdef12-0000-4000-8000-000000000002", "Sync", "2026-01-01T00:00:00Z", "two"),
                    conversation("abcdef12-0000-4000-8000-000000000003", "Sync", "2026-01-01T00:00:00Z", "three"),
                ],
                out,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            notes = sorted(out.glob("*.md"))
            self.assertEqual(len(notes), 3)
            bodies = "".join(n.read_text(encoding="utf-8") for n in notes)
            for word in ("one", "two", "three"):
                self.assertIn(word, bodies)

    def test_repeated_export_is_idempotent(self):
        payload = [
            conversation("12345678-1111-4111-8111-111111111111", "Meeting", "2026-09-17T10:00:00Z", "FIRST body"),
            conversation("12345678-2222-4222-8222-222222222222", "Meeting", "2026-09-17T11:00:00Z", "SECOND body"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "notes"
            self.assertEqual(run_exporter(payload, out).returncode, 0)
            first = sorted(p.name for p in out.glob("*.md"))
            self.assertEqual(run_exporter(payload, out).returncode, 0)
            second = sorted(p.name for p in out.glob("*.md"))
            self.assertEqual(first, second, "re-exporting the same ids must not grow the output set")

    def test_same_id_twice_yields_one_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "notes"
            result = run_exporter(
                [
                    conversation("dupdupdu-1111-4111-8111-111111111111", "Dup", "2026-03-03T00:00:00Z", "v1"),
                    conversation("dupdupdu-1111-4111-8111-111111111111", "Dup", "2026-03-03T00:00:00Z", "v2"),
                ],
                out,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(out.glob("*.md"))), 1)

    def test_non_colliding_ids_keep_plain_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "notes"
            result = run_exporter(
                [
                    conversation("aaaaaaaa-1111-4111-8111-111111111111", "Alpha", "2026-02-02T00:00:00Z", "A"),
                    conversation("bbbbbbbb-2222-4222-8222-222222222222", "Beta", "2026-02-03T00:00:00Z", "B"),
                ],
                out,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            names = sorted(p.name for p in out.glob("*.md"))
            self.assertEqual(names, ["2026-02-02_alpha_aaaaaaaa.md", "2026-02-03_beta_bbbbbbbb.md"])

    def test_stable_suffix_is_deterministic_and_distinct(self):
        module = load_module()
        first = module.stable_suffix("12345678-1111-4111-8111-111111111111")
        again = module.stable_suffix("12345678-1111-4111-8111-111111111111")
        other = module.stable_suffix("12345678-2222-4222-8222-222222222222")
        self.assertEqual(first, again, "suffix must be stable across runs")
        self.assertNotEqual(first, other, "ids sharing a prefix must get different suffixes")
        self.assertTrue(first.isalnum() and first.islower() or first.isdigit())


if __name__ == "__main__":
    unittest.main()
