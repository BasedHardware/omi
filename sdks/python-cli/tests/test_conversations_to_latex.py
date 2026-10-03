"""Tests for the conversations -> LaTeX report exporter.

Pins the standalone-document structure, envelope unwrapping, transcript and
action-item rendering, deterministic bytes, split-file naming, and the
no-overwrite / no-path-traversal / malformed-input guarantees. The escaping
suite is exhaustive: every one of the ten LaTeX special characters, their
combinations, and the rule that an escape never feeds back into another.
All cases are hermetic: JSON fixtures in, .tex bytes out; no network, no CLI,
no external services.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_here = Path(__file__).resolve().parent
script_path = _here / "conversations_to_latex.py"
if not script_path.exists():
    script_path = _here.parent / "examples" / "conversations_to_latex.py"
spec = importlib.util.spec_from_file_location("conversations_to_latex", script_path)
c2tex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2tex)


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


def read_doc(dest):
    return dest.read_text(encoding="utf-8")


class TestEscapeLatex(unittest.TestCase):
    # each of the ten specials, in isolation
    def test_backslash(self):
        self.assertEqual(c2tex.escape_latex("a\\b"), r"a\textbackslash{}b")

    def test_ampersand(self):
        self.assertEqual(c2tex.escape_latex("a&b"), r"a\&b")

    def test_percent(self):
        self.assertEqual(c2tex.escape_latex("50%"), r"50\%")

    def test_dollar(self):
        self.assertEqual(c2tex.escape_latex("$5"), r"\$5")

    def test_hash(self):
        self.assertEqual(c2tex.escape_latex("x#y"), r"x\#y")

    def test_underscore(self):
        self.assertEqual(c2tex.escape_latex("a_b"), r"a\_b")

    def test_left_brace(self):
        self.assertEqual(c2tex.escape_latex("{a}"), r"\{a\}")

    def test_tilde(self):
        self.assertEqual(c2tex.escape_latex("~"), r"\textasciitilde{}")

    def test_caret(self):
        self.assertEqual(c2tex.escape_latex("^"), r"\textasciicircum{}")

    def test_plain_text_untouched(self):
        self.assertEqual(c2tex.escape_latex("hello world"), "hello world")

    def test_empty_string(self):
        self.assertEqual(c2tex.escape_latex(""), "")

    def test_none_becomes_empty(self):
        self.assertEqual(c2tex.escape_latex(None), "")

    # combinations that would corrupt under naive sequential .replace()
    def test_backslash_escape_not_corrupted_by_later_passes(self):
        # A naive sequential replace that escapes { } after \ would turn the
        # braces in \textbackslash{} into \{\}. The single-pass table must not.
        self.assertEqual(c2tex.escape_latex("\\"), r"\textbackslash{}")

    def test_braces_not_corrupted_by_backslash_pass(self):
        # Naive order that escapes { } first, then \, would turn \{ \} into
        # \textbackslash{}{ ... }. The single-pass table must not.
        self.assertEqual(c2tex.escape_latex("{}"), r"\{\}")

    def test_tilde_and_caret_self_contained(self):
        self.assertEqual(c2tex.escape_latex("a~b^c"), r"a\textasciitilde{}b\textasciicircum{}c")

    def test_mixed_all_ten(self):
        value = "\\\\&%$#_{ }~^"
        # Build the expected with the same mapping so the test is independent of
        # implementation order while still pinning exact output.
        expected = "".join(c2tex._LATEX_SPECIALS.get(ch, ch) for ch in "\\\\&%$#_{ }~^")
        self.assertEqual(c2tex.escape_latex("\\\\&%$#_{ }~^"), expected)

    def test_repeated_specials(self):
        self.assertEqual(c2tex.escape_latex("&&&"), r"\&\&\&")

    def test_no_feedback_on_replacement_text(self):
        # The replacement string for backslash contains '{' and '}' characters.
        # If the escaper were a second pass, it would double-escape them.
        self.assertNotIn(r"\{\}", c2tex.escape_latex("\\"))

    # non-string coercion happens before escaping
    def test_int_coerced_then_escaped(self):
        self.assertEqual(c2tex.escape_latex(42), "42")

    def test_dict_json_dumped_then_escaped(self):
        # json.dumps yields literal braces, which are LaTeX-special and therefore
        # escaped too: the whole rendered string is safe to drop in body text.
        self.assertEqual(c2tex.escape_latex({"a_b": 1}), r'\{"a\_b": 1\}')

    def test_list_json_dumped(self):
        self.assertEqual(c2tex.escape_latex([1, 2]), "[1, 2]")

    def test_whitespace_collapsed(self):
        self.assertEqual(c2tex.escape_latex("  a\tb\n c "), "a b c")

    def test_unicode_passthrough(self):
        self.assertEqual(c2tex.escape_latex("héllo"), "héllo")
        self.assertEqual(c2tex.escape_latex("日本語"), "日本語")


class TestHelpers(unittest.TestCase):
    # one_line
    def test_one_line_none(self):
        self.assertEqual(c2tex.one_line(None), "")

    def test_one_line_plain(self):
        self.assertEqual(c2tex.one_line("plain"), "plain")

    def test_one_line_collapses_whitespace(self):
        self.assertEqual(c2tex.one_line("a\nb\tc  d "), "a b c d")

    def test_one_line_int(self):
        self.assertEqual(c2tex.one_line(42), "42")

    def test_one_line_float(self):
        self.assertEqual(c2tex.one_line(3.14), "3.14")

    def test_one_line_bool(self):
        self.assertEqual(c2tex.one_line(True), "True")
        self.assertEqual(c2tex.one_line(False), "False")

    def test_one_line_dict_json(self):
        self.assertEqual(c2tex.one_line({"a": 1}), '{"a": 1}')

    def test_one_line_list_json(self):
        self.assertEqual(c2tex.one_line([1, 2]), "[1, 2]")

    # slugify
    def test_slugify_basic(self):
        self.assertEqual(c2tex.slugify("Hello World"), "hello_world")

    def test_slugify_strips_symbols(self):
        self.assertEqual(c2tex.slugify("bad--chars!!"), "bad_chars")

    def test_slugify_truncates_50(self):
        self.assertEqual(c2tex.slugify("a" * 100), "a" * 50)

    def test_slugify_empty_fallback(self):
        self.assertEqual(c2tex.slugify(""), "conversation")
        self.assertEqual(c2tex.slugify("   "), "conversation")

    def test_slugify_unicode_word_chars(self):
        self.assertEqual(c2tex.slugify("Café & Co."), "caf\u00e9_co")

    # format_timestamp
    def test_format_timestamp_none(self):
        self.assertIsNone(c2tex.format_timestamp(None))

    def test_format_timestamp_zero(self):
        self.assertEqual(c2tex.format_timestamp(0), "00:00")

    def test_format_timestamp_minutes_seconds(self):
        self.assertEqual(c2tex.format_timestamp(90), "01:30")

    def test_format_timestamp_hours(self):
        self.assertEqual(c2tex.format_timestamp(3661), "01:01:01")

    def test_format_timestamp_string_number(self):
        self.assertEqual(c2tex.format_timestamp("90"), "01:30")

    def test_format_timestamp_float_truncated(self):
        self.assertEqual(c2tex.format_timestamp(90.7), "01:30")

    def test_format_timestamp_bad_strings(self):
        self.assertIsNone(c2tex.format_timestamp("abc"))
        self.assertIsNone(c2tex.format_timestamp("1.5s"))

    def test_format_timestamp_rejects_non_finite_and_negative_values(self):
        for value in (float("nan"), float("inf"), float("-inf"), -1, "NaN", "Infinity", "-1"):
            with self.subTest(value=value):
                self.assertIsNone(c2tex.format_timestamp(value))

    # is_completed
    def test_is_completed_native(self):
        self.assertTrue(c2tex.is_completed(True))
        self.assertFalse(c2tex.is_completed(False))

    def test_is_completed_numeric(self):
        self.assertTrue(c2tex.is_completed(1))
        self.assertTrue(c2tex.is_completed(2.5))
        self.assertFalse(c2tex.is_completed(0))
        self.assertFalse(c2tex.is_completed(0.0))

    def test_is_completed_strings(self):
        self.assertTrue(c2tex.is_completed("true"))
        self.assertTrue(c2tex.is_completed("YES"))
        self.assertTrue(c2tex.is_completed("1"))
        self.assertTrue(c2tex.is_completed("done"))
        self.assertTrue(c2tex.is_completed("completed"))
        self.assertFalse(c2tex.is_completed("false"))
        self.assertFalse(c2tex.is_completed("no"))
        self.assertFalse(c2tex.is_completed("0"))
        self.assertFalse(c2tex.is_completed(""))

    def test_is_completed_other_types(self):
        self.assertFalse(c2tex.is_completed(None))
        self.assertFalse(c2tex.is_completed([1]))

    # transcript_rows
    def test_rows_missing_segments_key(self):
        self.assertEqual(c2tex.transcript_rows({}), [])

    def test_rows_segments_not_a_list(self):
        self.assertEqual(c2tex.transcript_rows({"transcript_segments": "x"}), [])

    def test_rows_filters_non_dict_segments(self):
        rows = c2tex.transcript_rows(
            {"transcript_segments": [42, None, {"speaker": 1, "start": 0, "end": 1, "text": "a"}]}
        )
        self.assertEqual(rows, [{"speaker": "Speaker 1", "start": "00:00", "end": "00:01", "text": "a"}])

    def test_rows_speaker_int(self):
        self.assertEqual(
            c2tex.transcript_rows({"transcript_segments": [{"speaker": 3, "text": "x"}]})[0]["speaker"], "Speaker 3"
        )

    def test_rows_speaker_missing(self):
        self.assertEqual(c2tex.transcript_rows({"transcript_segments": [{"text": "x"}]})[0]["speaker"], "Speaker")

    def test_rows_speaker_blank(self):
        self.assertEqual(
            c2tex.transcript_rows({"transcript_segments": [{"speaker": "   ", "text": "x"}]})[0]["speaker"], "Speaker"
        )

    def test_rows_text_none_becomes_empty(self):
        self.assertEqual(c2tex.transcript_rows({"transcript_segments": [{"speaker": 1}]})[0]["text"], "")

    def test_rows_text_collapses_whitespace(self):
        self.assertEqual(
            c2tex.transcript_rows({"transcript_segments": [{"speaker": 1, "text": "  a  b "}]})[0]["text"], "a b"
        )

    def test_rows_text_escapes_specials(self):
        self.assertEqual(
            c2tex.transcript_rows({"transcript_segments": [{"speaker": 1, "text": "a&b"}]})[0]["text"], r"a\&b"
        )

    def test_rows_only_known_keys(self):
        rows = c2tex.transcript_rows(
            {"transcript_segments": [{"speaker": 1, "start": 0, "end": 1, "text": "a", "junk": 9}]}
        )
        self.assertEqual(set(rows[0].keys()), {"speaker", "start", "end", "text"})


class TestExtractConversations(unittest.TestCase):
    def test_envelope_keys(self):
        for key in ("conversations", "items", "data", "results"):
            self.assertEqual(c2tex.extract_conversations({key: [conv()]}), [conv()], key)

    def test_single_conversation_dict(self):
        self.assertEqual(c2tex.extract_conversations(conv()), [conv()])

    def test_single_via_created_at(self):
        payload = {"created_at": "2026-01-01T00:00:00Z"}
        self.assertEqual(c2tex.extract_conversations(payload), [payload])

    def test_single_via_structured_key(self):
        payload = {"structured": {"title": "T"}}
        self.assertEqual(c2tex.extract_conversations(payload), [payload])

    def test_single_via_transcript_segments_key(self):
        payload = {"transcript_segments": []}
        self.assertEqual(c2tex.extract_conversations(payload), [payload])

    def test_single_via_started_at_key(self):
        payload = {"started_at": "2026-01-01T00:00:00Z"}
        self.assertEqual(c2tex.extract_conversations(payload), [payload])

    def test_bare_list_filters_junk(self):
        self.assertEqual(c2tex.extract_conversations(["nope", None, conv(), 7]), [conv()])

    def test_error_shape_returns_empty(self):
        self.assertEqual(c2tex.extract_conversations({"detail": "Not Found"}), [])
        self.assertEqual(c2tex.extract_conversations({"conversations": []}), [])
        self.assertEqual(c2tex.extract_conversations(42), [])

    def test_non_list_envelope_values_ignored(self):
        self.assertEqual(c2tex.extract_conversations({"conversations": "not-a-list", "items": 5, "data": {"x": 1}}), [])
        self.assertEqual(c2tex.extract_conversations({"results": conv()}), [])

    def test_envelope_wins_over_single_dict_shape(self):
        payload = {
            "conversations": [conv()],
            "id": "looks-like-a-single-conversation",
            "started_at": "2026-01-01T00:00:00Z",
        }
        self.assertEqual(c2tex.extract_conversations(payload), [conv()])

    def test_unknown_envelope_returns_empty(self):
        self.assertEqual(c2tex.extract_conversations({"foo": [conv()]}), [])
        self.assertEqual(c2tex.extract_conversations("just a string"), [])


class TestDocumentStructure(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, payload, destination="out.tex", **kwargs):
        src = self.tmp / "conversations.json"
        src.write_text(json.dumps(payload), encoding="utf-8")
        dest = self.tmp / destination
        written = c2tex.convert(str(src), str(dest), **kwargs)
        return written, dest

    def test_master_document_has_full_standalone_structure(self):
        written, dest = self.export([conv(), conv(id="conv_2")])
        self.assertEqual(written, 2)
        text = read_doc(dest)
        self.assertIn(r"\documentclass[11pt]{article}", text)
        self.assertIn(r"\usepackage{iftex}", text)
        self.assertIn(r"\ifPDFTeX", text)
        self.assertIn(r"\usepackage[utf8]{inputenc}", text)
        self.assertIn(r"\usepackage{fontspec}", text)
        self.assertIn(r"\usepackage{amsmath,amssymb}", text)
        self.assertIn(r"\begin{document}", text)
        self.assertIn(r"\maketitle", text)
        self.assertTrue(text.rstrip().endswith(r"\end{document}"))
        self.assertEqual(text.count("\\section{"), 2)
        self.assertIn("2 conversation(s) exported", text)

    def test_section_numbers_sequential(self):
        _, dest = self.export([conv(id="a"), conv(id="b", structured={"title": "Second"})])
        text = read_doc(dest)
        self.assertIn("\\section{1.", text)
        self.assertIn("\\section{2.", text)

    def test_metadata_description_block(self):
        _, dest = self.export([conv()])
        text = read_doc(dest)
        self.assertIn(r"\begin{description}", text)
        self.assertIn(r"\end{description}", text)
        self.assertIn(r"\item[ID] \texttt{conv\_1}", text)
        self.assertIn(r"\item[Source] \texttt{omi}", text)
        self.assertIn(r"\item[Category] \texttt{meeting}", text)
        self.assertIn("2 segment(s)", text)
        self.assertIn("2 speaker(s)", text)

    def test_summary_subsection(self):
        _, dest = self.export([conv()])
        text = read_doc(dest)
        self.assertIn("\\subsection{Summary}", text)
        self.assertIn("We agreed on a September 15 beta.", text)

    def test_action_items_subsection_with_bullets(self):
        _, dest = self.export([conv()])
        text = read_doc(dest)
        self.assertIn("\\subsection{Action items}", text)
        self.assertIn(r"\item " + r"\checkmark{} Draft the rollout plan", text)
        self.assertIn(r"\item " + r"\square{} Set up the feature flag", text)

    def test_transcript_subsection(self):
        _, dest = self.export([conv()])
        text = read_doc(dest)
        self.assertIn("\\subsection{Transcript}", text)
        self.assertIn(r"\begin{quote}", text)
        self.assertIn(r"\end{quote}", text)
        self.assertIn(r"\textbf{Speaker 1} \texttt{[00:00]}:", text)
        self.assertIn(r"\textbf{Speaker 2} \texttt{[00:03]}:", text)

    def test_no_trailing_par_inside_quote(self):
        _, dest = self.export([conv()])
        text = read_doc(dest)
        # The final transcript line must not end with \par before \end{quote}.
        self.assertNotIn("\\par\\end{quote}", text)
        quote = text.split("\\begin{quote}", 1)[1].split("\\end{quote}", 1)[0]
        lines = [ln for ln in quote.split("\n") if ln.strip()]
        self.assertTrue(lines[-1].endswith("."))
        self.assertNotIn("\\par", lines[-1])
        # interior lines carry an explicit \par paragraph break
        self.assertTrue(any(ln.endswith("\\par") for ln in lines[:-1]))

    def test_empty_export_writes_skeleton_document(self):
        written, dest = self.export([])
        self.assertEqual(written, 0)
        text = read_doc(dest)
        self.assertIn(r"\begin{document}", text)
        self.assertIn("No conversations in this export.", text)
        self.assertEqual(text.count("\\section{"), 0)

    def test_title_is_escaped(self):
        c = conv(structured={"title": "C++ & Rust: 100% better"})
        _, dest = self.export([c])
        text = read_doc(dest)
        # '+' is not a LaTeX special, so it stays; & and % are escaped.
        self.assertIn("C++ \\& Rust: 100\\% better", text)
        self.assertNotIn("C++ & Rust", text)

    def test_overview_is_escaped(self):
        c = conv(structured={"overview": "50% of the $x#y & z_a {b}"})
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertIn("50\\% of the \\$x\\#y \\& z\\_a \\{b\\}", text)

    def test_transcript_text_is_escaped(self):
        c = conv(transcript_segments=[{"speaker": 1, "text": "a & b ~ c"}])
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertIn("a \\& b \\textasciitilde{} c", text)

    def test_speaker_is_escaped(self):
        c = conv(transcript_segments=[{"speaker": "R&D", "text": "x"}])
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertIn(r"\textbf{R\&D}", text)

    def test_unicode_roundtrip_without_ascii_escaping(self):
        c = conv(transcript_segments=[{"speaker": "Speaker 1", "start": 0, "text": "日本語のメモ🚀"}])
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertIn("日本語のメモ🚀", text)
        self.assertNotIn("\\u65e5", text)

    def test_deterministic_bytes(self):
        payload = [conv(), conv(id="conv_2", structured=None)]
        _, a = self.export(payload, "a.tex")
        _, b = self.export(payload, "b.tex")
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_all_junk_action_items_omit_cell(self):
        c = conv(structured={"title": "T", "action_items": [7, None, "  "]})
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertNotIn("\\subsection{Action items}", text)

    def test_missing_summary_omits_section(self):
        c = conv(structured={"title": "T", "overview": ""})
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertNotIn("\\subsection{Summary}", text)

    def test_missing_transcript_omits_section(self):
        c = conv(transcript_segments=[])
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertNotIn("\\subsection{Transcript}", text)

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
        text = read_doc(dest)
        self.assertIn("Untitled Conversation", text)
        self.assertIn("spaced text", text)
        # three valid dict segments survive (0, 2, 3): two start None -> [00:00],
        # one start "90" -> [01:30]
        self.assertEqual(text.count("\\texttt{[00:00]}") + text.count("\\texttt{[01:30]}"), 3)

    def test_zero_segments_header_no_speaker_note(self):
        c = conv(transcript_segments=[])
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertIn("0 segment(s)", text)
        self.assertNotIn("speaker(s)", text)

    def test_missing_started_at_omits_line(self):
        c = conv(started_at="")
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertNotIn(r"\item[Started]", text)

    def test_bad_date_string_falls_back_to_raw(self):
        c = conv(started_at="not-a-date")
        _, dest = self.export([c])
        text = read_doc(dest)
        self.assertIn("not-a-date", text)


class TestStdin(unittest.TestCase):
    def test_stdin_source(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "in.tex"
            old_stdin = sys.stdin
            sys.stdin = io.StringIO(json.dumps([conv()]))
            try:
                written = c2tex.convert("-", str(dest))
            finally:
                sys.stdin = old_stdin
            self.assertEqual(written, 1)
            self.assertIn("Planning the launch", read_doc(dest))

    def test_stdin_empty_list(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "empty.tex"
            old_stdin = sys.stdin
            sys.stdin = io.StringIO("[]")
            try:
                written = c2tex.convert("-", str(dest))
            finally:
                sys.stdin = old_stdin
            self.assertEqual(written, 0)
            self.assertIn("No conversations in this export.", read_doc(dest))

    def test_stdin_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "env.tex"
            old_stdin = sys.stdin
            sys.stdin = io.StringIO(json.dumps({"conversations": [conv()]}))
            try:
                written = c2tex.convert("-", str(dest))
            finally:
                sys.stdin = old_stdin
            self.assertEqual(written, 1)


class TestSplitOutputDir(unittest.TestCase):
    def export_split(self, payload, out_dir):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            result = c2tex.convert(str(src), "", output_dir=str(out_dir if out_dir else tmp / "reports"))
            return result, (out_dir if out_dir else tmp / "reports")

    def test_one_document_per_conversation_with_safe_names(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            payload = [
                conv(),
                conv(id="conv_2", started_at="not-a-date", structured={"title": "Café & Co."}),
                conv(id="conv_1", started_at="2026-09-01T10:00:00Z", structured={"title": "Planning the launch"}),
            ]
            src.write_text(json.dumps(payload), encoding="utf-8")
            out_dir = tmp / "reports"
            written = c2tex.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(written, 3)
            names = sorted(p.name for p in out_dir.iterdir())
            self.assertEqual(
                names,
                [
                    "2026-09-01_planning_the_launch_conv_1-2.tex",
                    "2026-09-01_planning_the_launch_conv_1.tex",
                    "undated_caf\u00e9_co_conv_2.tex",
                ],
            )
            for name in names:
                self.assertIn(r"\begin{document}", read_doc(out_dir / name))

    def test_split_refuses_clobber_existing_files(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            out_dir = tmp / "reports"
            c2tex.convert(str(src), "", output_dir=str(out_dir))
            existing = out_dir / "2026-09-01_planning_the_launch_conv_1.tex"
            first_bytes = existing.read_bytes()
            with self.assertRaises(OSError):
                c2tex.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(existing.read_bytes(), first_bytes)

    def test_split_empty_export_writes_zero_files(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([]), encoding="utf-8")
            out_dir = tmp / "a" / "b" / "reports"
            written = c2tex.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(written, 0)
            self.assertTrue(out_dir.is_dir())
            self.assertEqual(list(out_dir.iterdir()), [])

    def test_split_creates_nested_output_dir(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            out_dir = tmp / "deep" / "nested" / "dir"
            c2tex.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["2026-09-01_planning_the_launch_conv_1.tex"])

    def test_split_collision_suffixes(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv(), conv(), conv()]), encoding="utf-8")
            out_dir = tmp / "reports"
            written = c2tex.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(written, 3)
            names = {p.name for p in out_dir.iterdir()}
            self.assertEqual(
                names,
                {
                    "2026-09-01_planning_the_launch_conv_1.tex",
                    "2026-09-01_planning_the_launch_conv_1-2.tex",
                    "2026-09-01_planning_the_launch_conv_1-3.tex",
                },
            )

    def test_split_files_hold_single_conversation(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            c1, c2 = conv(id="conv_1"), conv(id="conv_2", structured={"title": "Second"})
            src.write_text(json.dumps([c1, c2]), encoding="utf-8")
            out_dir = tmp / "reports"
            c2tex.convert(str(src), "", output_dir=str(out_dir))
            for p in out_dir.iterdir():
                text = read_doc(p)
                self.assertEqual(text.count("\\section{"), 1, p.name)

    def test_split_file_bytes_match_single_payload(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            c1, c2 = conv(id="conv_1"), conv(id="conv_2", started_at="not-a-date", structured={"title": "Second"})
            src.write_text(json.dumps([c1, c2]), encoding="utf-8")
            out_dir = tmp / "reports"
            c2tex.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual(
                (out_dir / "2026-09-01_planning_the_launch_conv_1.tex").read_bytes(), c2tex.latex_payload([c1])
            )
            self.assertEqual((out_dir / "undated_second_conv_2.tex").read_bytes(), c2tex.latex_payload([c2]))

    def test_split_same_title_different_ids_unique(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv(id="alpha"), conv(id="beta")]), encoding="utf-8")
            out_dir = tmp / "reports"
            c2tex.convert(str(src), "", output_dir=str(out_dir))
            names = {p.name for p in out_dir.iterdir()}
            self.assertEqual(
                names, {"2026-09-01_planning_the_launch_alpha.tex", "2026-09-01_planning_the_launch_beta.tex"}
            )

    def test_split_undated_no_title_fallback_name(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            c = conv(id="zz", started_at="x", structured=None)
            src.write_text(json.dumps([c]), encoding="utf-8")
            out_dir = tmp / "reports"
            c2tex.convert(str(src), "", output_dir=str(out_dir))
            self.assertEqual([p.name for p in out_dir.iterdir()], ["undated_untitled_conversation_zz.tex"])


class TestGuards(unittest.TestCase):
    def test_refuses_to_overwrite_master_document(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "n.tex"
            c2tex.convert(str(src), str(dest))
            original = dest.read_bytes()
            with self.assertRaises(FileExistsError) as ctx:
                c2tex.convert(str(src), str(dest))
            self.assertIn("Refusing to overwrite", str(ctx.exception))
            self.assertEqual(dest.read_bytes(), original)
            written = c2tex.convert(str(src), str(dest), overwrite=True)
            self.assertEqual(written, 1)
            self.assertEqual(dest.read_bytes(), c2tex.latex_payload([conv()]))

    def test_path_traversal_guard(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            for bad in (f"{tmp}/../evil.tex", "../../evil.tex"):
                with self.assertRaises(ValueError):
                    c2tex.convert(str(src), bad)
            with self.assertRaises(ValueError):
                c2tex.convert(str(src), "", output_dir=f"{tmp}/../outdir")

    def test_missing_input_file_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(OSError):
                c2tex.convert(str(Path(td) / "nope.json"), str(Path(td) / "n.tex"))

    def test_malformed_json_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "bad.json"
            src.write_text("{not json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                c2tex.convert(str(src), str(tmp / "n.tex"))

    def test_master_destination_in_missing_parent_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            missing = tmp / "no" / "such" / "dir" / "x.tex"
            with self.assertRaises(OSError):
                c2tex.convert(str(src), str(missing))
            self.assertFalse(missing.exists())

    def test_master_destination_is_a_directory_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "x.tex"
            dest.mkdir()
            with self.assertRaises(OSError):
                c2tex.convert(str(src), str(dest))
            self.assertTrue(dest.is_dir())

    def test_overwrite_replaces_bytes_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "o.tex"
            dest.write_bytes(b"stale-bytes")
            c2tex.convert(str(src), str(dest), overwrite=True)
            self.assertEqual(dest.read_bytes(), c2tex.latex_payload([conv()]))

    def test_overwrite_preserves_preexisting_fixed_tmp_sibling(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "report.tex"
            dest.write_bytes(b"stale")
            sibling = tmp / "report.tex.tmp"
            sibling.write_bytes(b"user data")

            c2tex.convert(str(src), str(dest), overwrite=True)

            self.assertEqual(dest.read_bytes(), c2tex.latex_payload([conv()]))
            self.assertEqual(sibling.read_bytes(), b"user data")

    def test_traversal_triple_dot_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            with self.assertRaises(ValueError):
                c2tex.convert(str(src), "a/../../evil.tex")
            with self.assertRaises(ValueError):
                c2tex.convert(str(src), "", output_dir=f"{tmp}/x/../../y")

    def test_refusal_message_names_path(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "existing.tex"
            c2tex.convert(str(src), str(dest))
            with self.assertRaises(FileExistsError) as ctx:
                c2tex.convert(str(src), str(dest))
            self.assertIn(str(dest), str(ctx.exception))

    def test_bom_tolerant_input(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "bom.json"
            src.write_bytes(b"\xef\xbb\xbf" + json.dumps([conv()]).encode("utf-8"))
            dest = tmp / "bom.tex"
            written = c2tex.convert(str(src), str(dest))
            self.assertEqual(written, 1)
            self.assertIn("Planning the launch", read_doc(dest))


class TestCli(unittest.TestCase):
    def run_cli(self, *argv, cwd=None, stdin=None):
        return subprocess.run(
            [sys.executable, str(script_path), *argv],
            capture_output=True,
            text=True,
            input=stdin,
            cwd=str(cwd) if cwd else str(script_path.parent),
        )

    def test_cli_master_success(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "cli.tex"
            result = self.run_cli(str(src), str(dest))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 conversation(s) written", result.stdout)
            self.assertIn(r"\documentclass", read_doc(dest))

    def test_cli_rejects_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "cli.tex"
            self.run_cli(str(src), str(dest))
            result = self.run_cli(str(src), str(dest))
            self.assertEqual(result.returncode, 1)
            self.assertIn("Refusing to overwrite", result.stdout + result.stderr)

    def test_cli_malformed_input_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "bad.json"
            src.write_text("{", encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "n.tex"))
            self.assertEqual(result.returncode, 1)
            self.assertIn("LaTeX export failed", result.stdout + result.stderr)

    def test_cli_requires_exactly_one_destination(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "a.tex"), "--output-dir", str(tmp / "d"))
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
            out_dir = tmp / "reports"
            result = self.run_cli(str(src), "", "--output-dir", str(out_dir))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("2 LaTeX document(s) written to", result.stdout)
            self.assertEqual(len(list(out_dir.glob("*.tex"))), 2)

    def test_cli_overwrite_flag_replaces_file(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            dest = tmp / "o.tex"
            dest.write_bytes(b"stale")
            result = self.run_cli(str(src), str(dest), "--overwrite")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(dest.read_bytes(), c2tex.latex_payload([conv()]))

    def test_cli_malformed_has_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "bad.json"
            src.write_text("{", encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "n.tex"))
            combined = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1)
            self.assertIn("LaTeX export failed", combined)
            self.assertNotIn("Traceback", combined)

    def test_cli_success_produces_no_stderr(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "ok.tex"))
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")

    def test_cli_default_destination(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            result = self.run_cli(str(src), cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((tmp / "omi_conversations.tex").exists())

    def test_cli_missing_input_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            result = self.run_cli(str(tmp / "nope.json"), str(tmp / "n.tex"))
            self.assertEqual(result.returncode, 1)
            self.assertIn("LaTeX export failed", result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_cli_stdin_pipe(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            dest = tmp / "pipe.tex"
            result = self.run_cli("-", str(dest), stdin=json.dumps([conv()]))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 conversation(s) written", result.stdout)
            self.assertIn(r"\begin{document}", read_doc(dest))

    def test_cli_split_second_run_fails(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            out_dir = tmp / "reports"
            first = self.run_cli(str(src), "", "--output-dir", str(out_dir))
            self.assertEqual(first.returncode, 0, first.stderr)
            second = self.run_cli(str(src), "", "--output-dir", str(out_dir))
            self.assertEqual(second.returncode, 1)
            self.assertIn("LaTeX export failed", second.stdout + second.stderr)

    def test_cli_empty_export_reports_zero(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text("[]", encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "empty.tex"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("0 conversation(s) written", result.stdout)


class TestEscapeInvariants(unittest.TestCase):
    """Whole-document invariants: for any generated .tex, every occurrence of a
    LaTeX special character must be part of its own escape sequence. These hold
    over the entire document (preamble included), because the preamble the
    generator emits introduces none of the ten specials. A raw leak from user
    data would break exactly these counts.
    """

    def export_text(self, payload):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            dest = tmp / "out.tex"
            c2tex.convert(str(src), str(dest))
            return read_doc(dest)

    ALL_SPECIALS_CONV = None

    @classmethod
    def setUpClass(cls):
        cls.ALL_SPECIALS_CONV = conv(
            id="a_b",
            source="x&y",
            structured={
                "title": "a&b%c$d#e_f{g}~h^i\\j",
                "category": "c&_at",
                "overview": "50% & 100$ #1 _u~s^e r \\name {x}",
                "action_items": [
                    {"description": "done & open ~ ^", "completed": "true"},
                    "plain",
                ],
            },
            transcript_segments=[
                {"speaker": "R&D~Ops", "start": 0, "text": "a&b%c$d#e_f{g}~h^i\\j"},
            ],
        )

    def check_invariants(self, text):
        # the five "self-containing" escapes: every raw char is part of its escape
        self.assertEqual(text.count("%"), text.count(r"\%"))
        self.assertEqual(text.count("$"), text.count(r"\$"))
        self.assertEqual(text.count("#"), text.count(r"\#"))
        self.assertEqual(text.count("_"), text.count(r"\_"))
        self.assertEqual(text.count("&"), text.count(r"\&"))
        # the tilde/caret escapes (\textasciitilde{} / \textasciicircum{}) do NOT
        # contain the raw char in their name, so the raw char must be fully absent
        self.assertEqual(text.count("~"), 0)
        self.assertEqual(text.count("^"), 0)
        # braces balance once the escaped literal braces are removed
        stripped = "".join(text.replace(r"\{", "").replace(r"\}", ""))
        self.assertEqual(stripped.count("{"), stripped.count("}"))

    def test_percent_invariant(self):
        text = self.export_text([self.ALL_SPECIALS_CONV])
        self.check_invariants(text)
        self.assertIn(r"50\%", text)
        self.assertNotIn("50%", text)

    def test_dollar_invariant(self):
        text = self.export_text([self.ALL_SPECIALS_CONV])
        self.check_invariants(text)
        self.assertIn(r"\$d", text)
        self.assertNotIn("$d#", text)

    def test_hash_invariant(self):
        text = self.export_text([self.ALL_SPECIALS_CONV])
        self.check_invariants(text)
        self.assertIn(r"\#e", text)

    def test_underscore_invariant(self):
        text = self.export_text([self.ALL_SPECIALS_CONV])
        self.check_invariants(text)
        self.assertIn(r"\_f", text)
        self.assertIn(r"\texttt{a\_b}", text)

    def test_ampersand_invariant(self):
        text = self.export_text([self.ALL_SPECIALS_CONV])
        self.check_invariants(text)
        self.assertIn(r"a\&b", text)

    def test_tilde_invariant(self):
        text = self.export_text([self.ALL_SPECIALS_CONV])
        self.check_invariants(text)
        # "…~h^i…" must render as …\textasciitilde{}h\textasciicircum{}i…
        self.assertIn(r"\textasciitilde{}h", text)
        self.assertNotIn("~h", text)

    def test_caret_invariant(self):
        text = self.export_text([self.ALL_SPECIALS_CONV])
        self.check_invariants(text)
        # "…~h^i\j" must render as \textasciitilde{}h\textasciicircum{}i\textbackslash{}j
        self.assertIn(r"h\textasciicircum{}i", text)
        self.assertNotIn("h^i", text)

    def test_backslash_invariant(self):
        # every backslash must belong to a known escape/command, and the user's
        # literal backslash must appear as \textbackslash{}
        text = self.export_text([self.ALL_SPECIALS_CONV])
        self.assertIn(r"\textbackslash{}j", text)
        self.assertNotIn("\\\\j", text)

    def test_brace_balance_invariant(self):
        text = self.export_text([self.ALL_SPECIALS_CONV, conv(id="conv_2")])
        stripped = "".join(text.replace(r"\{", "").replace(r"\}", ""))
        self.assertEqual(stripped.count("{"), stripped.count("}"))

    def test_empty_document_satisfies_invariants(self):
        # the preamble alone must introduce no raw specials
        text = self.export_text([])
        self.check_invariants(text)

    def test_split_files_satisfy_invariants(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([self.ALL_SPECIALS_CONV, conv(id="conv_2")]), encoding="utf-8")
            out_dir = tmp / "reports"
            c2tex.convert(str(src), "", output_dir=str(out_dir))
            for p in out_dir.iterdir():
                self.check_invariants(read_doc(p))


class TestDocumentEdges(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, payload, destination="out.tex", **kwargs):
        src = self.tmp / "conversations.json"
        src.write_text(json.dumps(payload), encoding="utf-8")
        dest = self.tmp / destination
        c2tex.convert(str(src), str(dest), **kwargs)
        return read_doc(dest)

    def test_int_id_rendered(self):
        c = conv(id=12345)
        text = self.export([c])
        self.assertIn(r"\item[ID] \texttt{12345}", text)
        self.assertNotIn("unknown", text)

    def test_non_utc_offset_normalized(self):
        c = conv(started_at="2026-09-01T09:00:00+05:30")
        text = self.export([c])
        self.assertIn("2026-09-01 03:30:00 UTC", text)

    def test_negative_utc_offset_normalized(self):
        c = conv(started_at="2026-09-01T09:00:00-04:00")
        text = self.export([c])
        self.assertIn("2026-09-01 13:00:00 UTC", text)

    def test_float_speaker_no_crash(self):
        c = conv(transcript_segments=[{"speaker": 1.5, "text": "x"}])
        text = self.export([c])
        self.assertIn(r"\textbf{1.5}", text)

    def test_long_duration_timestamp_three_hours(self):
        c = conv(transcript_segments=[{"speaker": 1, "start": 12600, "text": "x"}])
        text = self.export([c])
        self.assertIn(r"\texttt{[03:30:00]}", text)

    def test_string_float_timestamp(self):
        c = conv(transcript_segments=[{"speaker": 1, "start": "90.5", "text": "x"}])
        text = self.export([c])
        self.assertIn(r"\texttt{[01:30]}", text)

    def test_bad_timestamp_falls_back_to_zero(self):
        c = conv(transcript_segments=[{"speaker": 1, "start": "abc", "text": "x"}])
        text = self.export([c])
        self.assertIn(r"\texttt{[00:00]}", text)

    def test_action_item_uppercase_yes_marks_done(self):
        c = conv(structured={"action_items": [{"description": "It", "completed": "YES"}]})
        text = self.export([c])
        self.assertIn(r"\item " + r"\checkmark{} It", text)

    def test_action_item_zero_numeric_open(self):
        c = conv(structured={"action_items": [{"description": "It", "completed": 0}]})
        text = self.export([c])
        self.assertIn(r"\item " + r"\square{} It", text)

    def test_structured_as_list_falls_back(self):
        c = conv(structured=["not", "a", "dict"])
        text = self.export([c])
        self.assertIn("Untitled Conversation", text)
        self.assertNotIn("\\subsection{Summary}", text)

    def test_date_metadata_line_shows_count(self):
        text = self.export([conv(), conv(id="conv_2")])
        self.assertIn(r"\date{2 conversation(s) exported from \texttt{omi --json conversation list}}", text)

    def test_source_with_specials_escaped(self):
        c = conv(source="a&b~c")
        text = self.export([c])
        self.assertIn(r"\item[Source] \texttt{a\&b\textasciitilde{}c}", text)

    def test_category_with_specials_escaped(self):
        c = conv(structured={"category": "r&d_v2"})
        text = self.export([c])
        self.assertIn(r"\item[Category] \texttt{r\&d\_v2}", text)

    def test_section_header_untitled_fallback(self):
        c = conv(structured=None)
        text = self.export([c])
        self.assertIn("\\section{1. Untitled Conversation}", text)

    def test_hundred_segment_transcript_complete(self):
        segs = [{"speaker": 1, "start": i * 60, "text": f"line {i} & {i}%"} for i in range(100)]
        c = conv(transcript_segments=segs)
        text = self.export([c])
        self.assertIn("100 segment(s)", text)
        self.assertIn(r"line 99 \& 99\%", text)
        # 99 * 60 = 5940 s = 01:39:00 (hour form, since it exceeds one hour)
        self.assertIn(r"\texttt{[01:39:00]}", text)


class TestMoreEscapeLatex(unittest.TestCase):
    def test_newlines_collapsed_before_escape(self):
        self.assertEqual(c2tex.escape_latex("a\nb&c"), "a b\\&c")

    def test_specials_inside_json_dumped_dict(self):
        self.assertEqual(c2tex.escape_latex({"a&b": 1}), r'\{"a\&b": 1\}')

    def test_specials_inside_json_dumped_list(self):
        self.assertEqual(c2tex.escape_latex(["x~y", 2]), r'["x\textasciitilde{}y", 2]')

    def test_bool_false_coerced_then_escaped(self):
        self.assertEqual(c2tex.escape_latex(False), "False")

    def test_only_specials_string(self):
        # a string made purely of specials must map exactly to the single-pass
        # table result; this pins that no escape feeds back into another
        value = "\\\\&%$#_{ }~^"
        out = c2tex.escape_latex(value)
        expected = "".join(c2tex._LATEX_SPECIALS.get(ch, ch) for ch in value)
        self.assertEqual(out, expected)
        # the brace-introducing escapes survive intact (no double-escape of the
        # braces they introduce)
        self.assertIn(r"\textbackslash{}", out)
        self.assertIn(r"\textasciitilde{}", out)
        self.assertIn(r"\textasciicircum{}", out)
        self.assertIn(r"\&", out)
        self.assertIn(r"\%", out)


class TestCliExtra(unittest.TestCase):
    def run_cli(self, *argv, cwd=None, stdin=None):
        return subprocess.run(
            [sys.executable, str(script_path), *argv],
            capture_output=True,
            text=True,
            input=stdin,
            cwd=str(cwd) if cwd else str(script_path.parent),
        )

    def test_cli_no_args_exits_two(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)

    def test_cli_unknown_flag_exits_two(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "a.tex"), "--bogus-flag")
            self.assertEqual(result.returncode, 2)

    def test_cli_split_and_destination_conflict_message(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            result = self.run_cli(str(src), str(tmp / "a.tex"), "--output-dir", str(tmp / "d"))
            self.assertEqual(result.returncode, 2)
            self.assertIn("exactly one of destination or --output-dir", result.stderr)
            self.assertNotIn("Traceback", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
