"""Tests for the conversations -> Jupyter notebook exporter.

Pins nbformat-4 structure, envelope unwrapping, transcript cell literal safety,
unicode round-tripping, deterministic bytes, split-file naming, and the
no-overwrite / no-path-traversal / malformed-input guarantees. All cases are
hermetic: JSON fixtures in, notebook bytes out; no network, no CLI, no external
services.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_here = Path(__file__).resolve().parent
script_path = _here / "conversations_to_jupyter.py"
if not script_path.exists():
    script_path = _here.parent / "examples" / "conversations_to_jupyter.py"
spec = importlib.util.spec_from_file_location("conversations_to_jupyter", script_path)
c2jup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2jup)


def conv(**overrides):
    base = {
        "id": "conv_1",
        "started_at": "2026-09-01T09:00:00Z",
        "source": "omi",
        "structured": {
            "title": "Planning the launch",
            "category": "meeting",
            "overview": "We agreed on a September 15 beta.",
            "action_items": [
                {"description": "Draft the rollout plan", "completed": True},
                {"description": "Set up the feature flag"},
            ],
        },
        "transcript_segments": [
            {"speaker": 1, "start": 0.0, "end": 3.5, "text": "Hi, ready to walk through the launch plan?"},
            {"speaker": 2, "start": 3.5, "end": 9.0, "text": "Yes, the rollout starts at five percent."},
        ],
    }
    base.update(overrides)
    return base


class TestHelpers(unittest.TestCase):
    # one_line
    def test_one_line_none(self):
        self.assertEqual(c2jup.one_line(None), "")

    def test_one_line_plain(self):
        self.assertEqual(c2jup.one_line("plain"), "plain")

    def test_one_line_collapses_whitespace(self):
        self.assertEqual(c2jup.one_line("a\nb\tc  d "), "a b c d")

    def test_one_line_int(self):
        self.assertEqual(c2jup.one_line(42), "42")

    def test_one_line_float(self):
        self.assertEqual(c2jup.one_line(3.14), "3.14")

    def test_one_line_bool(self):
        self.assertEqual(c2jup.one_line(True), "True")
        self.assertEqual(c2jup.one_line(False), "False")

    def test_one_line_dict_json(self):
        self.assertEqual(c2jup.one_line({"a": 1}), '{"a": 1}')

    def test_one_line_list_json(self):
        self.assertEqual(c2jup.one_line([1, 2]), "[1, 2]")

    # slugify
    def test_slugify_basic(self):
        self.assertEqual(c2jup.slugify("Hello World"), "hello_world")

    def test_slugify_strips_symbols(self):
        self.assertEqual(c2jup.slugify("bad--chars!!"), "bad_chars")

    def test_slugify_truncates_50(self):
        self.assertEqual(c2jup.slugify("a" * 100), "a" * 50)

    def test_slugify_empty_fallback(self):
        self.assertEqual(c2jup.slugify(""), "conversation")
        self.assertEqual(c2jup.slugify("   "), "conversation")

    def test_slugify_unicode_word_chars(self):
        self.assertEqual(c2jup.slugify("Café & Co."), "caf\u00e9_co")

    # format_timestamp
    def test_format_timestamp_none(self):
        self.assertIsNone(c2jup.format_timestamp(None))

    def test_format_timestamp_zero(self):
        self.assertEqual(c2jup.format_timestamp(0), "00:00")

    def test_format_timestamp_minutes_seconds(self):
        self.assertEqual(c2jup.format_timestamp(90), "01:30")

    def test_format_timestamp_hours(self):
        self.assertEqual(c2jup.format_timestamp(3661), "01:01:01")

    def test_format_timestamp_string_number(self):
        self.assertEqual(c2jup.format_timestamp("90"), "01:30")

    def test_format_timestamp_float_truncated(self):
        self.assertEqual(c2jup.format_timestamp(90.7), "01:30")

    def test_format_timestamp_bad_strings(self):
        self.assertIsNone(c2jup.format_timestamp("abc"))
        self.assertIsNone(c2jup.format_timestamp("1.5s"))

    # transcript_rows
    def test_rows_missing_segments_key(self):
        self.assertEqual(c2jup.transcript_rows({}), [])

    def test_rows_segments_not_a_list(self):
        self.assertEqual(c2jup.transcript_rows({"transcript_segments": "x"}), [])

    def test_rows_filters_non_dict_segments(self):
        rows = c2jup.transcript_rows(
            {"transcript_segments": [42, None, {"speaker": 1, "start": 0, "end": 1, "text": "a"}]}
        )
        self.assertEqual(rows, [{"speaker": "Speaker 1", "start": "00:00", "end": "00:01", "text": "a"}])

    def test_rows_speaker_int(self):
        self.assertEqual(
            c2jup.transcript_rows({"transcript_segments": [{"speaker": 3, "text": "x"}]})[0]["speaker"], "Speaker 3"
        )

    def test_rows_speaker_missing(self):
        self.assertEqual(c2jup.transcript_rows({"transcript_segments": [{"text": "x"}]})[0]["speaker"], "Speaker")

    def test_rows_speaker_blank(self):
        self.assertEqual(
            c2jup.transcript_rows({"transcript_segments": [{"speaker": "   ", "text": "x"}]})[0]["speaker"], "Speaker"
        )

    def test_rows_text_none_becomes_empty(self):
        self.assertEqual(c2jup.transcript_rows({"transcript_segments": [{"speaker": 1}]})[0]["text"], "")

    def test_rows_text_collapses_whitespace(self):
        self.assertEqual(
            c2jup.transcript_rows({"transcript_segments": [{"speaker": 1, "text": "  a  b "}]})[0]["text"], "a b"
        )

    def test_rows_only_known_keys(self):
        rows = c2jup.transcript_rows(
            {"transcript_segments": [{"speaker": 1, "start": 0, "end": 1, "text": "a", "junk": 9}]}
        )
        self.assertEqual(set(rows[0].keys()), {"speaker", "start", "end", "text"})

    # py_literal
    def test_py_literal_scalars(self):
        self.assertEqual(c2jup.py_literal(None), "None")
        self.assertEqual(c2jup.py_literal(True), "True")
        self.assertEqual(c2jup.py_literal(False), "False")
        self.assertEqual(c2jup.py_literal("x"), '"x"')
        self.assertEqual(c2jup.py_literal(42), "42")
        self.assertEqual(c2jup.py_literal(3.5), "3.5")

    def test_py_literal_empty_containers(self):
        self.assertEqual(c2jup.py_literal([]), "[]")
        self.assertEqual(c2jup.py_literal({}), "{}")

    def test_py_literal_nested_roundtrip(self):
        value = [{"speaker": "S", "start": None, "end": None, "text": "h\u00e9llo"}]
        self.assertEqual(ast.literal_eval(c2jup.py_literal(value)), value)

    def test_py_literal_unicode_readable(self):
        rendered = c2jup.py_literal({"text": "h\u00e9llo"})
        self.assertIn("h\u00e9llo", rendered)
        self.assertNotIn("\\u00e9", rendered)


class TestNotebookStructure(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_input(self, payload):
        src = self.tmp / "conversations.json"
        src.write_text(json.dumps(payload), encoding="utf-8")
        return src

    def export(self, payload, destination="out.ipynb", **kwargs):
        src = self.write_input(payload)
        dest = self.tmp / destination
        written = c2jup.convert(str(src), str(dest), **kwargs)
        return written, dest

    def test_master_notebook_structure(self):
        written, dest = self.export([conv(), conv(id="conv_2")])
        self.assertEqual(written, 2)
        doc = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(doc["nbformat"], 4)
        self.assertEqual(doc["nbformat_minor"], 4)
        self.assertEqual(doc["metadata"]["omi"]["conversation_count"], 2)
        self.assertEqual(doc["metadata"]["kernelspec"]["language"], "python")
        types = [cell["cell_type"] for cell in doc["cells"]]
        # header + (header, summary, action items, code) per conversation
        self.assertEqual(types, ["markdown"] * 1 + ["markdown", "markdown", "markdown", "code"] * 2)
        for cell in doc["cells"]:
            self.assertIsInstance(cell["source"], list)
            self.assertEqual(cell["metadata"], {})
        code_cells = [cell for cell in doc["cells"] if cell["cell_type"] == "code"]
        self.assertIsNone(code_cells[0]["execution_count"])
        self.assertEqual(code_cells[0]["outputs"], [])

    def test_transcript_cell_is_a_literal_python_assignment(self):
        _, dest = self.export([conv()])
        doc = json.loads(dest.read_text(encoding="utf-8"))
        code = "".join(doc["cells"][4]["source"])
        tree = ast.parse(code)
        assign = [
            node
            for node in tree.body
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "transcript"
        ]
        self.assertEqual(len(assign), 1)
        value = ast.literal_eval(assign[0].value)
        self.assertEqual(value[0]["text"], "Hi, ready to walk through the launch plan?")
        self.assertEqual(value[0]["start"], "00:00")
        self.assertEqual(value[1]["speaker"], "Speaker 2")
        self.assertEqual(code.rstrip().splitlines()[-1], "len(transcript)")

    def test_unicode_roundtrip_without_ascii_escaping(self):
        c = conv()
        c["transcript_segments"] = [{"speaker": "Speaker 1", "start": 0, "text": "日本語のメモ🚀"}]
        _, dest = self.export([c])
        text = dest.read_text(encoding="utf-8")
        self.assertIn("日本語のメモ🚀", text)
        self.assertNotIn("\\u65e5", text)

    def test_deterministic_bytes(self):
        payload = [conv(), conv(id="conv_2", structured=None)]
        _, a = self.export(payload, "a.ipynb")
        _, b = self.export(payload, "b.ipynb")
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_empty_export_writes_header_only_notebook(self):
        written, dest = self.export([])
        self.assertEqual(written, 0)
        doc = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(len(doc["cells"]), 2)
        self.assertIn("No conversations in this export", "".join(doc["cells"][1]["source"]))

    def test_degenerate_fields_do_not_crash(self):
        c = conv(
            structured="not-a-dict",
            transcript_segments=[
                {"text": None},
                42,
                {"speaker": "", "start": "90", "text": "  spaced  text "},
                {"speaker": 0, "end": "abc"},
                "garbage",
            ],
        )
        _, dest = self.export([c])
        doc = json.loads(dest.read_text(encoding="utf-8"))
        code = [cell for cell in doc["cells"] if cell["cell_type"] == "code"][0]
        tree = ast.parse("".join(code["source"]))
        assign = [n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "transcript"]
        value = ast.literal_eval(assign[0].value)
        self.assertEqual(len(value), 3)
        self.assertEqual(value[0], {"speaker": "Speaker", "start": None, "end": None, "text": ""})
        self.assertEqual(value[1]["speaker"], "Speaker")
        self.assertEqual(value[1]["start"], "01:30")
        self.assertEqual(value[1]["text"], "spaced text")
        self.assertEqual(value[2]["speaker"], "Speaker 0")
        self.assertEqual(value[2]["end"], None)
        # degenerate structured degrades to the untitled fallback
        self.assertIn("Untitled Conversation", "".join(doc["cells"][1]["source"]))

    def test_empty_transcript_code_cell(self):
        c = conv(transcript_segments=[])
        _, dest = self.export([c])
        doc = json.loads(dest.read_text(encoding="utf-8"))
        code = [cell for cell in doc["cells"] if cell["cell_type"] == "code"][0]
        text = "".join(code["source"])
        self.assertIn("transcript = []", text)
        self.assertEqual(text.rstrip().splitlines()[-1], "len(transcript)")

    def test_action_item_variants_render(self):
        c = conv(
            structured={
                "title": "T",
                "action_items": [
                    {"title": "Named item", "completed": "true"},
                    {"description": "Done item", "completed": "1"},
                    "Plain string item",
                    {"note": "no desc/title"},
                    7,
                ],
            }
        )
        _, dest = self.export([c])
        doc = json.loads(dest.read_text(encoding="utf-8"))
        cells = ["".join(c2["source"]) for c2 in doc["cells"] if c2["cell_type"] == "markdown"]
        action = [c for c in cells if c.startswith("### Action items")]
        self.assertEqual(len(action), 1)
        self.assertIn("- [x] Named item", action[0])
        self.assertIn("- [x] Done item", action[0])
        self.assertIn("- [ ] Plain string item", action[0])
        self.assertIn("- [ ] Untitled action item", action[0])

    def test_all_junk_action_items_omit_cell(self):
        c = conv(structured={"title": "T", "action_items": [7, None, "  "]})
        _, dest = self.export([c])
        doc = json.loads(dest.read_text(encoding="utf-8"))
        cells = ["".join(c2["source"]) for c2 in doc["cells"]]
        self.assertFalse(any(c.startswith("### Action items") for c in cells))

    def test_notebook_metadata_full_shape(self):
        _, dest = self.export([conv(), conv(id="conv_2")])
        doc = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(
            doc["metadata"]["kernelspec"], {"display_name": "Python 3", "language": "python", "name": "python3"}
        )
        self.assertEqual(doc["metadata"]["language_info"], {"name": "python", "version": "3"})
        self.assertEqual(doc["metadata"]["omi"], {"source": "omi --json conversation list", "conversation_count": 2})

    def test_header_cell_content(self):
        _, dest = self.export([conv(), conv(id="conv_2")])
        doc = json.loads(dest.read_text(encoding="utf-8"))
        header = "".join(doc["cells"][0]["source"])
        self.assertIn("2 conversation(s) exported from `omi --json conversation list`", header)
        self.assertIn("Open this notebook in [Jupyter]", header)

    def test_bom_tolerant_input(self):
        src = self.tmp / "bom.json"
        src.write_bytes(b"\xef\xbb\xbf" + json.dumps([conv()]).encode("utf-8"))
        dest = self.tmp / "bom.ipynb"
        written = c2jup.convert(str(src), str(dest))
        self.assertEqual(written, 1)
        self.assertIn("Planning the launch", dest.read_text(encoding="utf-8"))

    def test_format_timestamp_variants(self):
        self.assertIsNone(c2jup.format_timestamp(None))
        self.assertEqual(c2jup.format_timestamp(0), "00:00")
        self.assertEqual(c2jup.format_timestamp(90), "01:30")
        self.assertEqual(c2jup.format_timestamp("90"), "01:30")
        self.assertEqual(c2jup.format_timestamp(3661), "01:01:01")
        self.assertEqual(c2jup.format_timestamp(5.0), "00:05")
        self.assertIsNone(c2jup.format_timestamp("abc"))
        self.assertIsNone(c2jup.format_timestamp("90.5 seconds"))


class TestNotebookStructure2(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, payload, destination="out.ipynb"):
        src = self.tmp / "in.json"
        src.write_text(json.dumps(payload), encoding="utf-8")
        dest = self.tmp / destination
        c2jup.convert(str(src), str(dest))
        return json.loads(dest.read_text(encoding="utf-8"))

    def test_bare_conv_layout_three_cells(self):
        c = conv()
        c.pop("structured")
        c["transcript_segments"] = []
        doc = self.export([c])
        self.assertEqual([cell["cell_type"] for cell in doc["cells"]], ["markdown", "markdown", "code"])

    def test_full_conv_cell_count_five(self):
        doc = self.export([conv()])
        self.assertEqual(len(doc["cells"]), 5)

    def test_section_numbers_sequential(self):
        doc = self.export([conv(id="a"), conv(id="b", structured={"title": "Second"})])
        sections = [
            "".join(c["source"])
            for c in doc["cells"]
            if c["cell_type"] == "markdown" and c["source"][0].startswith("## ")
        ]
        self.assertTrue(any(s.startswith("## 1.") for s in sections))
        self.assertTrue(any(s.startswith("## 2.") for s in sections))

    def test_id_shown_in_header(self):
        doc = self.export([conv()])
        section = [c for c in doc["cells"] if c["cell_type"] == "markdown" and c["source"][0].startswith("## ")][0]
        self.assertIn("- **ID:** `conv_1`", "".join(section["source"]))

    def test_category_in_header(self):
        doc = self.export([conv()])
        section = [c for c in doc["cells"] if c["cell_type"] == "markdown" and c["source"][0].startswith("## ")][0]
        self.assertIn("- **Category:** `meeting`", "".join(section["source"]))

    def test_speaker_count_in_header(self):
        doc = self.export([conv()])
        section = [c for c in doc["cells"] if c["cell_type"] == "markdown" and c["source"][0].startswith("## ")][0]
        self.assertIn("2 speaker(s)", "".join(section["source"]))

    def test_zero_segments_header(self):
        c = conv(transcript_segments=[])
        doc = self.export([c])
        section = [x for x in doc["cells"] if x["cell_type"] == "markdown" and x["source"][0].startswith("## ")][0]
        text = "".join(section["source"])
        self.assertIn("0 segment(s)", text)
        self.assertNotIn("speaker(s)", text)

    def test_missing_started_at_omits_line(self):
        c = conv(started_at="")
        doc = self.export([c])
        section = [x for x in doc["cells"] if x["cell_type"] == "markdown" and x["source"][0].startswith("## ")][0]
        self.assertNotIn("**Started:**", "".join(section["source"]))

    def test_cells_carry_no_id_key(self):
        doc = self.export([conv()])
        for cell in doc["cells"]:
            self.assertNotIn("id", cell)

    def test_file_bytes_are_json_roundtrip_stable(self):
        c = conv()
        src = self.tmp / "in.json"
        src.write_text(json.dumps([c]), encoding="utf-8")
        dest = self.tmp / "rt.ipynb"
        c2jup.convert(str(src), str(dest))
        raw = dest.read_text(encoding="utf-8")
        self.assertEqual(raw, json.dumps(json.loads(raw), indent=1, ensure_ascii=False) + "\n")


class TestEnvelopeUnwrapping(unittest.TestCase):
    def test_envelope_keys(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            for key in ("conversations", "items", "data", "results"):
                src = tmp / f"{key}.json"
                src.write_text(json.dumps({key: [conv()]}), encoding="utf-8")
                dest = tmp / f"{key}.ipynb"
                written = c2jup.convert(str(src), str(dest))
                self.assertEqual(written, 1, key)
                doc = json.loads(dest.read_text(encoding="utf-8"))
                self.assertEqual(doc["metadata"]["omi"]["conversation_count"], 1)

    def test_single_conversation_dict(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "one.json"
            src.write_text(json.dumps(conv()), encoding="utf-8")
            written = c2jup.convert(str(src), str(tmp / "one.ipynb"))
            self.assertEqual(written, 1)

    def test_error_shape_returns_empty(self):
        self.assertEqual(c2jup.extract_conversations({"detail": "Not Found"}), [])
        self.assertEqual(c2jup.extract_conversations({"conversations": []}), [])
        self.assertEqual(c2jup.extract_conversations(42), [])
        filtered = c2jup.extract_conversations([{"id": "a"}, "junk", None, {"id": "b"}])
        self.assertEqual(filtered, [{"id": "a"}, {"id": "b"}])

    def test_non_list_envelope_values_ignored(self):
        self.assertEqual(c2jup.extract_conversations({"conversations": "not-a-list", "items": 5, "data": {"x": 1}}), [])
        self.assertEqual(c2jup.extract_conversations({"results": conv()}), [])

    def test_envelope_wins_over_single_dict_shape(self):
        payload = {
            "conversations": [conv()],
            "id": "looks-like-a-single-conversation",
            "started_at": "2026-01-01T00:00:00Z",
        }
        self.assertEqual(c2jup.extract_conversations(payload), [conv()])

    def test_unknown_envelope_returns_empty(self):
        self.assertEqual(c2jup.extract_conversations({"foo": [conv()]}), [])
        self.assertEqual(c2jup.extract_conversations("just a string"), [])

    def test_single_via_created_at(self):
        payload = {"created_at": "2026-01-01T00:00:00Z"}
        self.assertEqual(c2jup.extract_conversations(payload), [payload])

    def test_single_via_structured_key(self):
        payload = {"structured": {"title": "T"}}
        self.assertEqual(c2jup.extract_conversations(payload), [payload])

    def test_single_via_transcript_segments_key(self):
        payload = {"transcript_segments": []}
        self.assertEqual(c2jup.extract_conversations(payload), [payload])

    def test_single_via_started_at_key(self):
        payload = {"started_at": "2026-01-01T00:00:00Z"}
        self.assertEqual(c2jup.extract_conversations(payload), [payload])

    def test_bare_list_filters_junk(self):
        payload = ["nope", None, conv(), 7]
        self.assertEqual(c2jup.extract_conversations(payload), [conv()])


class TestStdin(unittest.TestCase):
    def test_stdin_source(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "in.ipynb"
            old_stdin = sys.stdin
            sys.stdin = io.StringIO(json.dumps([conv()]))
            try:
                written = c2jup.convert("-", str(dest))
            finally:
                sys.stdin = old_stdin
            self.assertEqual(written, 1)
            self.assertIn("Planning the launch", dest.read_text(encoding="utf-8"))

    def test_stdin_empty_list_header_only(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "empty.ipynb"
            old_stdin = sys.stdin
            sys.stdin = io.StringIO("[]")
            try:
                written = c2jup.convert("-", str(dest))
            finally:
                sys.stdin = old_stdin
            self.assertEqual(written, 0)
            doc = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(len(doc["cells"]), 2)

    def test_stdin_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "env.ipynb"
            old_stdin = sys.stdin
            sys.stdin = io.StringIO(json.dumps({"conversations": [conv()]}))
            try:
                written = c2jup.convert("-", str(dest))
            finally:
                sys.stdin = old_stdin
            self.assertEqual(written, 1)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8"))["metadata"]["omi"]["conversation_count"], 1)


class TestSplitOutputDir(unittest.TestCase):
    def test_one_notebook_per_conversation_with_safe_names(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            payload = [
                conv(),
                conv(id="conv_2", started_at="not-a-date", structured={"title": "Café & Co."}),
                conv(id="conv_1", started_at="2026-09-01T10:00:00Z", structured={"title": "Planning the launch"}),
            ]
            src.write_text(json.dumps(payload), encoding="utf-8")
            out_dir = tmp / "notebooks"
            written = c2jup.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(written, 3)
            names = sorted(p.name for p in out_dir.iterdir())
            self.assertEqual(
                names,
                [
                    "2026-09-01_planning_the_launch_conv_1-2.ipynb",
                    "2026-09-01_planning_the_launch_conv_1.ipynb",
                    "undated_caf\u00e9_co_conv_2.ipynb",
                ],
            )
            for name in names:
                doc = json.loads((out_dir / name).read_text(encoding="utf-8"))
                self.assertEqual(doc["nbformat"], 4)

    def test_split_refuses_clobber_existing_files(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            out_dir = tmp / "notebooks"
            c2jup.convert(str(src), "", output_dir=str(out_dir))
            existing = out_dir / "2026-09-01_planning_the_launch_conv_1.ipynb"
            first_bytes = existing.read_bytes()
            with self.assertRaises(OSError):
                c2jup.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(existing.read_bytes(), first_bytes)

    def test_split_empty_export_writes_zero_files(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([]), encoding="utf-8")
            out_dir = tmp / "a" / "b" / "notebooks"
            written = c2jup.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(written, 0)
            self.assertTrue(out_dir.is_dir())
            self.assertEqual(list(out_dir.iterdir()), [])

    def test_split_creates_nested_output_dir(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            out_dir = tmp / "deep" / "nested" / "dir"
            c2jup.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["2026-09-01_planning_the_launch_conv_1.ipynb"])

    def test_split_collision_suffixes(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv(), conv(), conv()]), encoding="utf-8")
            out_dir = tmp / "nbs"
            written = c2jup.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(written, 3)
            names = {p.name for p in out_dir.iterdir()}
            self.assertEqual(
                names,
                {
                    "2026-09-01_planning_the_launch_conv_1.ipynb",
                    "2026-09-01_planning_the_launch_conv_1-2.ipynb",
                    "2026-09-01_planning_the_launch_conv_1-3.ipynb",
                },
            )

    def test_split_files_hold_single_conversation(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            c1, c2 = conv(id="conv_1"), conv(id="conv_2", structured={"title": "Second"})
            src.write_text(json.dumps([c1, c2]), encoding="utf-8")
            out_dir = tmp / "nbs"
            c2jup.convert(str(src), "", output_dir=str(out_dir))
            for p in out_dir.iterdir():
                doc = json.loads(p.read_text(encoding="utf-8"))
                self.assertEqual(doc["metadata"]["omi"]["conversation_count"], 1, p.name)
                sections = [
                    x for x in doc["cells"] if x["cell_type"] == "markdown" and x["source"][0].startswith("## ")
                ]
                self.assertEqual(len(sections), 1, p.name)

    def test_split_file_bytes_match_single_payload(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            c1, c2 = conv(id="conv_1"), conv(id="conv_2", started_at="not-a-date", structured={"title": "Second"})
            src.write_text(json.dumps([c1, c2]), encoding="utf-8")
            out_dir = tmp / "nbs"
            c2jup.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(
                (out_dir / "2026-09-01_planning_the_launch_conv_1.ipynb").read_bytes(), c2jup.notebook_payload([c1])
            )
            self.assertEqual((out_dir / "undated_second_conv_2.ipynb").read_bytes(), c2jup.notebook_payload([c2]))

    def test_split_same_title_different_ids_unique(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv(id="alpha"), conv(id="beta")]), encoding="utf-8")
            out_dir = tmp / "nbs"
            c2jup.convert(str(src), "", output_dir=str(out_dir))
            names = {p.name for p in out_dir.iterdir()}
            self.assertEqual(
                names, {"2026-09-01_planning_the_launch_alpha.ipynb", "2026-09-01_planning_the_launch_beta.ipynb"}
            )

    def test_split_undated_no_title_fallback_name(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            c = conv(id="zz", started_at="x", structured=None)
            src.write_text(json.dumps([c]), encoding="utf-8")
            out_dir = tmp / "nbs"
            c2jup.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual([p.name for p in out_dir.iterdir()], ["undated_untitled_conversation_zz.ipynb"])


class TestGuards(unittest.TestCase):
    def test_refuses_to_overwrite_master_notebook(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "n.ipynb"
            c2jup.convert(str(src), str(dest))
            original = dest.read_bytes()
            with self.assertRaises(FileExistsError) as ctx:
                c2jup.convert(str(src), str(dest))
            self.assertIn("Refusing to overwrite", str(ctx.exception))
            self.assertEqual(dest.read_bytes(), original)
            written = c2jup.convert(str(src), str(dest), overwrite=True)
            self.assertEqual(written, 1)
            self.assertEqual(dest.read_bytes(), c2jup.notebook_payload([conv()]))

    def test_path_traversal_guard(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            for bad in (f"{tmp}/../evil.ipynb", "../../evil.ipynb"):
                with self.assertRaises(ValueError):
                    c2jup.convert(str(src), bad)
            with self.assertRaises(ValueError):
                c2jup.convert(str(src), "", output_dir=f"{tmp}/../outdir")

    def test_missing_input_file_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(OSError):
                c2jup.convert(str(Path(td) / "nope.json"), str(Path(td) / "n.ipynb"))

    def test_malformed_json_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "bad.json"
            src.write_text("{not json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                c2jup.convert(str(src), str(tmp / "n.ipynb"))

    def test_master_destination_in_missing_parent_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            missing = tmp / "no" / "such" / "dir" / "x.ipynb"
            with self.assertRaises(OSError):
                c2jup.convert(str(src), str(missing))
            self.assertFalse(missing.exists())

    def test_master_destination_is_a_directory_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "x.ipynb"
            dest.mkdir()
            with self.assertRaises(OSError):
                c2jup.convert(str(src), str(dest))
            self.assertTrue(dest.is_dir())

    def test_overwrite_replaces_bytes_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "o.ipynb"
            dest.write_bytes(b"stale-bytes")
            c2jup.convert(str(src), str(dest), overwrite=True)
            self.assertEqual(dest.read_bytes(), c2jup.notebook_payload([conv()]))

    def test_traversal_triple_dot_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            with self.assertRaises(ValueError):
                c2jup.convert(str(src), "a/../../evil.ipynb")
            with self.assertRaises(ValueError):
                c2jup.convert(str(src), "", output_dir=f"{tmp}/x/../../y")

    def test_refusal_message_names_path(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "existing.ipynb"
            c2jup.convert(str(src), str(dest))
            with self.assertRaises(FileExistsError) as ctx:
                c2jup.convert(str(src), str(dest))
            self.assertIn(str(dest), str(ctx.exception))


class TestCli(unittest.TestCase):
    def run_cli(self, *argv, cwd=None, stdin=None):
        return subprocess.run(
            [sys.executable, str(script_path), *argv],
            capture_output=True,
            text=True,
            input=stdin,
            cwd=str(cwd) if cwd else str(script_path.parent),
        )

    def test_cli_master_and_stderr_free_success(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "cli.ipynb"
            result = self.run_cli(str(src), str(dest))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 conversation(s) written", result.stdout)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8"))["nbformat"], 4)

    def test_cli_rejects_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "cli.ipynb"
            self.run_cli(str(src), str(dest))
            result = self.run_cli(str(src), str(dest))
            self.assertEqual(result.returncode, 1)
            self.assertIn("Refusing to overwrite", result.stdout + result.stderr)

    def test_cli_malformed_input_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "bad.json"
            src.write_text("{", encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "n.ipynb"))
            self.assertEqual(result.returncode, 1)
            self.assertIn("Jupyter export failed", result.stdout + result.stderr)

    def test_cli_requires_exactly_one_destination(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "a.ipynb"), "--output-dir", str(tmp / "d"))
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("exactly one of destination or --output-dir", result.stderr)

    def test_cli_split_mode_success(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(
                json.dumps([conv(), conv(id="conv_2", started_at="not-a-date", structured={"title": "Other"})]),
                encoding="utf-8",
            )
            out_dir = tmp / "nbs"
            result = self.run_cli(str(src), "", "--output-dir", str(out_dir))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("2 notebook(s) written to", result.stdout)
            self.assertEqual(len(list(out_dir.glob("*.ipynb"))), 2)

    def test_cli_overwrite_flag_replaces_file(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "o.ipynb"
            dest.write_bytes(b"stale")
            result = self.run_cli(str(src), str(dest), "--overwrite")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(dest.read_bytes(), c2jup.notebook_payload([conv()]))

    def test_cli_malformed_has_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "bad.json"
            src.write_text("{", encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "n.ipynb"))
            combined = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1)
            self.assertIn("Jupyter export failed", combined)
            self.assertNotIn("Traceback", combined)

    def test_cli_success_produces_no_stderr(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "ok.ipynb"))
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")

    def test_cli_default_destination(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            result = self.run_cli(str(src), cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((tmp / "omi_conversations.ipynb").exists())

    def test_cli_missing_input_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_cli(str(tmp / "nope.json"), str(tmp / "n.ipynb"))
            self.assertEqual(result.returncode, 1)
            self.assertIn("Jupyter export failed", result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_cli_stdin_pipe(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "pipe.ipynb"
            result = self.run_cli("-", str(dest), stdin=json.dumps([conv()]))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 conversation(s) written", result.stdout)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8"))["nbformat"], 4)

    def test_cli_split_second_run_fails(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            out_dir = tmp / "nbs"
            first = self.run_cli(str(src), "", "--output-dir", str(out_dir))
            self.assertEqual(first.returncode, 0, first.stderr)
            second = self.run_cli(str(src), "", "--output-dir", str(out_dir))
            self.assertEqual(second.returncode, 1)
            self.assertIn("Jupyter export failed", second.stdout + second.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
