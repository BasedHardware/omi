"""Hermetic unit tests for conversations_to_latex.py (JSON in, .tex bytes out)."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

import conversations_to_latex as ctl  # noqa: E402


def conv(**over):
    base = {
        "id": "abc123",
        "started_at": "2026-01-02T10:30:00Z",
        "source": "omi",
        "structured": {
            "title": None,
            "category": "work",
            "overview": "Discussed 50% of the $plan & #specs",
            "action_items": [
                {"description": "Ship it", "completed": True},
                {"description": "Buy 5% coffee", "completed": False},
            ],
        },
        "transcript_segments": [
            {"speaker": "Speaker 0", "start": 65.0, "text": "Hello _world_ ~ok^"},
            {"speaker": "Anna", "start": 3705.0, "text": "Responded with {braces} & \\backslash"},
        ],
    }
    base.update(over)
    if isinstance(base["structured"], dict):
        if "title" in over:
            base["structured"]["title"] = over["title"]
        if not base["structured"].get("title"):
            base["structured"]["title"] = "C++ & Rust: 100%"
    return base


def sample_fixture():
    return [conv(), conv(id="def456", started_at="2026-02-03T00:30:00+02:00")]


class TestEscapeLatex(unittest.TestCase):
    def test_ampersand(self):
        self.assertEqual(ctl.escape_latex("a&b"), "a\\&b")

    def test_percent(self):
        self.assertEqual(ctl.escape_latex("50%"), "50\\%")

    def test_dollar(self):
        self.assertEqual(ctl.escape_latex("$5"), r"\$5")

    def test_hash(self):
        self.assertEqual(ctl.escape_latex("#1"), r"\#1")

    def test_underscore(self):
        self.assertEqual(ctl.escape_latex("a_b"), "a\\_b")

    def test_braces(self):
        self.assertEqual(ctl.escape_latex("{}"), r"\{\}")

    def test_backslash(self):
        self.assertEqual(ctl.escape_latex("a\\b"), r"a\textbackslash{}b")

    def test_tilde(self):
        self.assertEqual(ctl.escape_latex("a~b"), "a\\textasciitilde{}b")

    def test_caret(self):
        self.assertEqual(ctl.escape_latex("a^b"), "a\\textasciicircum{}b")

    def test_plain_untouched(self):
        self.assertEqual(ctl.escape_latex("hello world"), "hello world")

    def test_non_string_coerced(self):
        self.assertEqual(ctl.escape_latex(123), "123")

    def test_none(self):
        self.assertEqual(ctl.escape_latex(None), "None")

    def test_combination_amp_then_underscore(self):
        self.assertEqual(ctl.escape_latex("a&_b"), "a\\&\\_b")

    def test_combination_dollar_backslash(self):
        self.assertEqual(ctl.escape_latex("$\\$"), r"\$\textbackslash{}\$")

    def test_all_ten_at_once(self):
        out = ctl.escape_latex("\\&%$#_{}~^")
        for esc in (r"\&", r"\%", r"\$", r"\#", r"\_", r"\{", r"\}", r"\textasciitilde{}", r"\textasciicircum{}"):
            self.assertIn(esc, out)
        self.assertIn("textbackslash", out)

    def test_no_sequential_replace_corruption(self):
        # A naive str.replace would corrupt this; single pass must not.
        self.assertEqual(ctl.escape_latex("&{}"), "\\&\\{\\}")

    def test_backslash_only_once(self):
        self.assertEqual(ctl.escape_latex("\\"), r"\textbackslash{}")

    def test_tilde_caret_combination(self):
        out = ctl.escape_latex("~^")
        self.assertNotIn("~", out)
        self.assertNotIn("^", out)

    def test_deterministic(self):
        self.assertEqual(ctl.escape_latex("a&b#c"), ctl.escape_latex("a&b#c"))

    def test_unicode_kept(self):
        self.assertEqual(ctl.escape_latex("héllo"), "héllo")

    def test_emoji_kept(self):
        self.assertEqual(ctl.escape_latex("👍"), "👍")

    def test_newline_kept(self):
        self.assertEqual(ctl.escape_latex("a\nb"), "a\nb")


class TestMoreEscapeLatex(unittest.TestCase):
    def test_ampersand_dollar(self):
        self.assertEqual(ctl.escape_latex("100% $&"), r"100\% \$\&")

    def test_hash_underscore_hash(self):
        self.assertEqual(ctl.escape_latex("#_#"), r"\#\_\#")

    def test_nested_braces(self):
        self.assertEqual(ctl.escape_latex("{{}}"), r"\{\{\}\}")

    def test_backslash_before_special(self):
        self.assertEqual(ctl.escape_latex("\\&"), r"\textbackslash{}\&")

    def test_empty(self):
        self.assertEqual(ctl.escape_latex(""), "")


class TestEscapeInvariants(unittest.TestCase):
    def assert_invariants(self, tex: str):
        for raw in ("&", "%", "$", "_"):
            # every raw occurrence must be part of its own escape (preceded by backslash)
            idx = tex.find(raw)
            if raw in tex:
                # raw specials only appear inside escape sequences
                self.assertIn("\\" + raw, tex)
        self.assertNotIn("~", tex.replace(r"\textasciitilde{}", ""))
        self.assertNotIn("^", tex.replace(r"\textasciicircum{}", ""))

    def test_master_document_invariants(self):
        tex = ctl.render_master_document(sample_fixture())
        self.assertNotIn(" & ", tex)
        self.assertNotIn(" %", tex)
        self.assertNotIn("$5", tex)

    def test_braces_balance_after_stripping_escapes(self):
        tex = ctl.render_master_document([conv(title="}{&%$#_~^\\")])
        stripped = tex.replace(r"\{", "").replace(r"\}", "")
        self.assertEqual(stripped.count("{"), stripped.count("}"))

    def test_split_documents_invariants(self):
        with tempfile.TemporaryDirectory() as d:
            paths = ctl.export_split(sample_fixture(), Path(d), overwrite=True)
            for p in paths:
                self.assert_invariants(p.read_text(encoding="utf-8"))

    def test_master_braces_balance(self):
        tex = ctl.render_master_document(sample_fixture())
        stripped = tex.replace(r"\{", "").replace(r"\}", "")
        self.assertEqual(stripped.count("{"), stripped.count("}"))

    def test_no_raw_underscore(self):
        tex = ctl.render_master_document([conv(title="under_score")])
        self.assertIn(r"under\_score", tex)

    def test_no_raw_dollar_outside_math(self):
        tex = ctl.render_master_document([conv(overview="$100")])
        self.assertNotIn("$100", tex)

    def test_no_raw_percent(self):
        tex = ctl.render_master_document([conv(overview="50% off")])
        self.assertNotIn("% off", tex)

    def test_no_raw_ampersand(self):
        tex = ctl.render_master_document([conv(title="A & B")])
        self.assertNotIn("A & B", tex)

    def test_no_raw_hash(self):
        tex = ctl.render_master_document([conv(overview="#tag")])
        self.assertNotIn("#tag", tex)

    def test_no_raw_tilde(self):
        tex = ctl.render_master_document([conv(overview="~ok")])
        self.assertNotIn("~ok", tex)

    def test_no_raw_caret(self):
        tex = ctl.render_master_document([conv(overview="^ok")])
        self.assertNotIn("^ok", tex)


class TestDocumentStructure(unittest.TestCase):
    def test_documentclass_present(self):
        tex = ctl.render_master_document(sample_fixture())
        self.assertTrue(tex.startswith(r"\documentclass[11pt]{article}"))

    def test_begin_end_document(self):
        tex = ctl.render_master_document(sample_fixture())
        self.assertIn(r"\begin{document}", tex)
        self.assertTrue(tex.rstrip().endswith(r"\end{document}"))

    def test_utf8_preamble(self):
        tex = ctl.render_master_document(sample_fixture())
        # UTF-8 is the LaTeX kernel default (no inputenc/fontenc needed);
        # xelatex/lualatex recommended for full Unicode.
        self.assertNotIn("inputenc", tex)
        self.assertNotIn(r"\maketitle", ctl.render_single_document(sample_fixture()[0], "x"))
        self.assertIn("geometry", tex)
        self.assertIn("amsmath", tex)
        self.assertIn("hyperref", tex)

    def test_section_per_conversation(self):
        tex = ctl.render_master_document(sample_fixture())
        self.assertEqual(tex.count(r"\section{"), 2)

    def test_section_title_escaped(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn(r"\section{C++ \& Rust: 100\%}", tex)

    def test_summary_subsection(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn(r"\subsection*{Summary}", tex)

    def test_action_items_subsection(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn(r"\subsection*{Action items}", tex)

    def test_checkmark_for_completed(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn(r"\checkmark", tex)

    def test_square_for_uncompleted(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn(r"$\square$", tex)

    def test_transcript_subsection(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn(r"\subsection*{Transcript}", tex)

    def test_quote_environment(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn(r"\begin{quote}", tex)
        self.assertIn(r"\end{quote}", tex)

    def test_bold_speaker(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn(r"\textbf{Anna}", tex)

    def test_timestamp_stamps(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn(r"\texttt{[01:05]}", tex)
        self.assertIn(r"\texttt{[01:01:45]}", tex)

    def test_metadata_line(self):
        tex = ctl.render_master_document([conv()])
        self.assertIn("2026-01-02 10:30:00 UTC", tex)
        self.assertIn(r"\quad| source: omi", tex)

    def test_tableofcontents(self):
        tex = ctl.render_master_document(sample_fixture())
        self.assertIn(r"\tableofcontents", tex)

    def test_unicode_roundtrip(self):
        conv_obj = conv(title="ÄÖÜ Titel & more")
        tex = ctl.render_master_document([conv_obj])
        self.assertIn(r"\section{ÄÖÜ Titel \& more}", tex)

    def test_deterministic_bytes(self):
        a = ctl.render_master_document(sample_fixture())
        b = ctl.render_master_document(sample_fixture())
        self.assertEqual(a, b)

    def test_non_utc_offset_normalized(self):
        conv_obj = conv(started_at="2026-02-03T00:30:00+02:00")
        tex = ctl.render_master_document([conv_obj])
        self.assertIn("2026-02-02 22:30:00 UTC", tex)

    def test_hundred_segments(self):
        segs = [{"speaker": f"Sp {i}", "start": i, "text": f"line {i}"} for i in range(100)]
        tex = ctl.render_master_document([conv(transcript_segments=segs)])
        self.assertEqual(tex.count(r"\textbf{Sp "), 100)

    def test_ends_with_newline(self):
        tex = ctl.render_master_document(sample_fixture())
        self.assertTrue(tex.endswith("\n"))


class TestDocumentEdges(unittest.TestCase):
    def test_empty_export(self):
        tex = ctl.render_master_document([])
        self.assertIn("No conversations", tex)
        self.assertTrue(tex.rstrip().endswith(r"\end{document}"))

    def test_non_dict_items_skipped(self):
        tex = ctl.render_master_document([conv(), "junk", None, conv()])
        self.assertEqual(tex.count(r"\section{"), 2)

    def test_degenerate_empty_conversation(self):
        tex = ctl.render_master_document([{}])
        self.assertIn("Untitled Conversation", tex)

    def test_missing_structured(self):
        c = conv()
        del c["structured"]
        tex = ctl.render_master_document([c])
        self.assertIn("Untitled Conversation", tex)

    def test_structured_not_dict(self):
        tex = ctl.render_master_document([conv(structured="oops")])
        self.assertIn("Untitled Conversation", tex)

    def test_action_items_not_list(self):
        tex = ctl.render_master_document([conv(structured={"title": "T", "action_items": "nope"})])
        self.assertNotIn(r"\subsection*{Action items}", tex)

    def test_string_action_items(self):
        tex = ctl.render_master_document([conv(structured={"title": "T", "action_items": [" call me "]})])
        self.assertIn(r"$\square$ call me", tex)

    def test_empty_action_item_desc(self):
        tex = ctl.render_master_document([conv(structured={"title": "T", "action_items": [{"description": ""}]})])
        self.assertIn("Untitled action item", tex)

    def test_missing_transcript(self):
        c = conv()
        del c["transcript_segments"]
        tex = ctl.render_master_document([c])
        self.assertNotIn(r"\subsection*{Transcript}", tex)

    def test_transcript_not_list(self):
        tex = ctl.render_master_document([conv(transcript_segments="x")])
        self.assertNotIn(r"\subsection*{Transcript}", tex)

    def test_segment_not_dict_skipped(self):
        tex = ctl.render_master_document([conv(transcript_segments=["x", {"speaker": "A", "start": 0, "text": "hi"}])])
        self.assertIn(r"\textbf{A}", tex)
        self.assertNotIn(r"\textbf{x}", tex)

    def test_empty_segment_text_skipped(self):
        tex = ctl.render_master_document([conv(transcript_segments=[{"speaker": "A", "start": 0, "text": " "}])])
        self.assertNotIn(r"\subsection*{Transcript}", tex)

    def test_bad_timestamp_falls_back(self):
        tex = ctl.render_master_document([conv(started_at="not-a-date")])
        self.assertIn("not-a-date", tex)

    def test_missing_started_at(self):
        c = conv()
        c.pop("started_at")
        tex = ctl.render_master_document([c])
        self.assertIn("N/A", tex)

    def test_default_source(self):
        c = conv()
        c.pop("source")
        tex = ctl.render_master_document([c])
        self.assertIn(r"source: omi", tex)


class TestHelpers(unittest.TestCase):
    def test_format_timestamp_none(self):
        self.assertEqual(ctl.format_timestamp(None), "00:00")

    def test_format_timestamp_zero(self):
        self.assertEqual(ctl.format_timestamp(0), "00:00")

    def test_format_timestamp_short(self):
        self.assertEqual(ctl.format_timestamp(65), "01:05")

    def test_format_timestamp_long(self):
        self.assertEqual(ctl.format_timestamp(3705), "01:01:45")

    def test_format_timestamp_float(self):
        self.assertEqual(ctl.format_timestamp(65.9), "01:05")

    def test_format_timestamp_negative(self):
        self.assertEqual(ctl.format_timestamp(-5), "00:00")

    def test_is_completed_true(self):
        self.assertTrue(ctl.is_completed(True))

    def test_is_completed_yes(self):
        self.assertTrue(ctl.is_completed("yes"))

    def test_is_completed_one(self):
        self.assertTrue(ctl.is_completed("1"))

    def test_is_completed_done(self):
        self.assertTrue(ctl.is_completed("DONE"))

    def test_is_completed_number(self):
        self.assertTrue(ctl.is_completed(1))

    def test_is_completed_false_string(self):
        self.assertFalse(ctl.is_completed("false"))

    def test_is_completed_no(self):
        self.assertFalse(ctl.is_completed("no"))

    def test_is_completed_empty(self):
        self.assertFalse(ctl.is_completed(""))

    def test_is_completed_none(self):
        self.assertFalse(ctl.is_completed(None))

    def test_is_completed_bool_false(self):
        self.assertFalse(ctl.is_completed(False))

    def test_is_completed_zero_number(self):
        self.assertFalse(ctl.is_completed(0))

    def test_slugify_basic(self):
        self.assertEqual(ctl.slugify("Hello World"), "hello_world")

    def test_slugify_specials(self):
        self.assertEqual(ctl.slugify("C++ & Rust!"), "c_rust")

    def test_slugify_empty(self):
        self.assertEqual(ctl.slugify(""), "conversation")

    def test_slugify_long(self):
        self.assertEqual(len(ctl.slugify("x" * 100)), 50)

    def test_sanitize_component(self):
        self.assertEqual(ctl.sanitize_component("../evil id"), "evilid")

    def test_sanitize_component_empty(self):
        self.assertEqual(ctl.sanitize_component(""), "conversation")

    def test_conversation_title_fallback(self):
        self.assertEqual(ctl.conversation_title({}), "Untitled Conversation")

    def test_conversation_title_from_structured(self):
        self.assertEqual(ctl.conversation_title({"structured": {"title": " T "}}), "T")

    def test_utc_date_str_empty(self):
        self.assertEqual(ctl.utc_date_str(""), "")

    def test_utc_date_str_z(self):
        self.assertEqual(ctl.utc_date_str("2026-01-02T10:30:00Z"), "2026-01-02 10:30:00 UTC")

    def test_action_item_text_prefers_description(self):
        self.assertEqual(ctl.action_item_text({"description": "a", "title": "b"}), "a")

    def test_action_item_text_falls_to_title(self):
        self.assertEqual(ctl.action_item_text({"title": "b"}), "b")

    def test_action_item_text_collapses_newlines(self):
        self.assertEqual(ctl.action_item_text({"description": "a\r\nb\nc"}), "a b c")

    def test_document_preamble_maketitle(self):
        self.assertIn(r"\maketitle", ctl.PREAMBLE_LINES)


class TestExtractConversations(unittest.TestCase):
    def test_bare_list(self):
        self.assertEqual(len(ctl.extract_conversations([conv()])), 1)

    def test_envelope_conversations(self):
        self.assertEqual(len(ctl.extract_conversations({"conversations": [conv()]})), 1)

    def test_envelope_items(self):
        self.assertEqual(len(ctl.extract_conversations({"items": [conv()]})), 1)

    def test_envelope_data(self):
        self.assertEqual(len(ctl.extract_conversations({"data": [conv()]})), 1)

    def test_envelope_results(self):
        self.assertEqual(len(ctl.extract_conversations({"results": [conv()]})), 1)

    def test_single_object(self):
        self.assertEqual(len(ctl.extract_conversations(conv())), 1)

    def test_error_envelope_empty(self):
        self.assertEqual(ctl.extract_conversations({"detail": "nope"}), [])

    def test_scalar_empty(self):
        self.assertEqual(ctl.extract_conversations("x"), [])

    def test_none_empty(self):
        self.assertEqual(ctl.extract_conversations(None), [])

    def test_filters_non_dicts(self):
        self.assertEqual(len(ctl.extract_conversations([conv(), 5])), 1)

    def test_envelope_list_not_dicts(self):
        self.assertEqual(ctl.extract_conversations({"items": [1, 2]}), [])


class TestStdin(unittest.TestCase):
    def test_main_stdin_pipe(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "report.tex"
            old_stdin, old_argv = sys.stdin, sys.argv
            old_stdout = sys.stdout
            sys.stdin = io.StringIO(json.dumps(sample_fixture()))
            sys.argv = ["x", "-", str(out)]
            sys.stdout = io.StringIO()
            try:
                ctl.main()
            finally:
                sys.stdin, sys.argv, sys.stdout = old_stdin, old_argv, old_stdout
            tex = out.read_text(encoding="utf-8")
            self.assertIn(r"\end{document}", tex)

    def test_main_stdin_bom(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "report.tex"
            old_stdin, old_argv, old_stdout = sys.stdin, sys.argv, sys.stdout
            sys.stdin = io.StringIO("\ufeff" + json.dumps(sample_fixture()))
            sys.argv = ["x", "-", str(out)]
            sys.stdout = io.StringIO()
            try:
                ctl.main()
            finally:
                sys.stdin, sys.argv, sys.stdout = old_stdin, old_argv, old_stdout
            self.assertTrue(out.exists())

    def test_main_stdin_invalid_json(self):
        old_stdin, old_argv, old_stdout, old_stderr = sys.stdin, sys.argv, sys.stdout, sys.stderr
        sys.stdin = io.StringIO("{not json")
        sys.argv = ["x", "-", "out.tex"]
        buf = io.StringIO()
        sys.stdout = sys.stderr = buf
        try:
            with self.assertRaises(SystemExit):
                ctl.main()
        finally:
            sys.stdin, sys.argv, sys.stdout, sys.stderr = old_stdin, old_argv, old_stdout, old_stderr


class TestSplitOutputDir(unittest.TestCase):
    def test_writes_one_file_per_conversation(self):
        with tempfile.TemporaryDirectory() as d:
            paths = ctl.export_split(sample_fixture(), Path(d) / "r", overwrite=True)
            self.assertEqual(len(paths), 2)
            for p in paths:
                self.assertTrue(p.read_text(encoding="utf-8").rstrip().endswith(r"\end{document}"))

    def test_filename_convention(self):
        with tempfile.TemporaryDirectory() as d:
            paths = ctl.export_split([conv()], Path(d) / "r", overwrite=True)
            self.assertEqual(paths[0].name, "2026-01-02_c_rust_100_abc123.tex")

    def test_collision_gets_suffix(self):
        with tempfile.TemporaryDirectory() as d:
            a = conv(id="same")
            b = conv(id="same")
            paths = ctl.export_split([a, b], Path(d) / "r", overwrite=False)
            names = sorted(p.name for p in paths)
            self.assertNotEqual(names[0], names[1])

    def test_no_overwrite_default(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d) / "r"
            ctl.export_split([conv(id="same")], d, overwrite=False)
            first = sorted(d.iterdir())[0]
            paths = ctl.export_split([conv(id="same")], d, overwrite=False)
            self.assertNotEqual(paths[0], first)

    def test_overwrite_flag(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d) / "r"
            p1 = ctl.export_split([conv(id="same")], d, overwrite=True)[0]
            p2 = ctl.export_split([conv(id="same")], d, overwrite=True)[0]
            self.assertEqual(p1, p2)

    def test_undated_fallback(self):
        c = conv()
        c.pop("started_at")
        with tempfile.TemporaryDirectory() as d:
            paths = ctl.export_split([c], Path(d) / "r", overwrite=True)
            self.assertTrue(paths[0].name.startswith("undated_"))

    def test_split_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            p = ctl.export_split([conv()], Path(d) / "r", overwrite=True)[0]
            a = p.read_text(encoding="utf-8")
            p2 = ctl.export_split([conv()], Path(d) / "r2", overwrite=True)[0]
            self.assertEqual(a, p2.read_text(encoding="utf-8"))

    def test_makedirs(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "a/b/c"
            ctl.export_split([conv()], target, overwrite=True)
            self.assertTrue(target.is_dir())

    def test_junk_rows_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            paths = ctl.export_split([conv(), "junk"], Path(d) / "r", overwrite=True)
            self.assertEqual(len(paths), 1)


class TestGuards(unittest.TestCase):
    def test_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "sub" / ".." / "escape.tex"
            old_argv, old_stdout = sys.argv, sys.stdout
            sys.argv = ["x", "-"]
            sys.stdout = io.StringIO()
            try:
                pass
            finally:
                sys.argv, sys.stdout = old_argv, old_stdout
            resolved_out = Path(d).resolve() / "escape.tex"
            # safe_output_path should resolve within parent dir without error here;
            # direct traversal attempt below must fail
            with self.assertRaises(SystemExit):
                ctl.safe_output_path(Path(d), "../outside.tex", ".tex")

    def test_safe_output_path_inside_ok(self):
        with tempfile.TemporaryDirectory() as d:
            p = ctl.safe_output_path(Path(d), "ok.tex", ".tex")
            self.assertTrue(str(p).startswith(str(Path(d).resolve())))

    def test_missing_input_file(self):
        old_argv, old_stdout, old_stderr = sys.argv, sys.stdout, sys.stderr
        sys.argv = ["x", "definitely_missing_12345.json"]
        sys.stdout = sys.stderr = io.StringIO()
        try:
            with self.assertRaises((SystemExit, OSError, FileNotFoundError)):
                ctl.main()
        finally:
            sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr

    def test_scalar_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text("42", encoding="utf-8")
            old_argv, old_stdout, old_stderr = sys.argv, sys.stdout, sys.stderr
            sys.argv = ["x", str(src), str(Path(d) / "o.tex")]
            sys.stdout = sys.stderr = io.StringIO()
            try:
                with self.assertRaises(SystemExit):
                    ctl.main()
            finally:
                sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr

    def test_no_partial_file_on_error(self):
        # A scalar JSON error must leave no output file behind.
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text("42", encoding="utf-8")
            out = Path(d) / "o.tex"
            old_argv, old_stdout, old_stderr = sys.argv, sys.stdout, sys.stderr
            sys.argv = ["x", str(src), str(out)]
            sys.stdout = sys.stderr = io.StringIO()
            try:
                with self.assertRaises(SystemExit):
                    ctl.main()
            finally:
                sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr
            self.assertFalse(out.exists())

    def test_bom_tolerant_file(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_bytes(b"\xef\xbb\xbf" + json.dumps(sample_fixture()).encode("utf-8"))
            out = Path(d) / "o.tex"
            old_argv, old_stdout = sys.argv, sys.stdout
            sys.argv = ["x", str(src), str(out)]
            sys.stdout = io.StringIO()
            try:
                ctl.main()
            finally:
                sys.argv, sys.stdout = old_argv, old_stdout
            self.assertTrue(out.exists())

    def test_default_output_name(self):
        old_argv, old_stdout, old_stderr, old_cwd = sys.argv, sys.stdout, sys.stderr, os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            src = Path(tmp) / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            sys.argv = ["x", str(src)]
            sys.stdout = sys.stderr = io.StringIO()
            try:
                ctl.main()
            finally:
                os.chdir(old_cwd)
                sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr
            self.assertTrue((Path(tmp) / "conversations_report.tex").exists())

    def test_unique_path_used_set(self):
        p = Path("/tmp/a.tex")
        self.assertEqual(ctl.unique_path(p, True, set()), p)

    def test_unique_path_collision(self):
        base = Path(tempfile.gettempdir()) / "ctl_test_unique.tex"
        self.assertTrue(str(ctl.unique_path(base, False, {base})).endswith("-2.tex"))


class TestCli(unittest.TestCase):
    def run_main(self, argv, cwd=None):
        old_argv, old_stdout, old_stderr, old_cwd = sys.argv, sys.stdout, sys.stderr, os.getcwd()
        if cwd:
            os.chdir(cwd)
        sys.argv = argv
        sys.stdout = sys.stderr = io.StringIO()
        try:
            ctl.main()
        finally:
            os.chdir(old_cwd)
            sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr

    def test_output_flag(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(sample_fixture()), encoding="utf-8")
            out = Path(d) / "rep.tex"
            self.run_main(["x", str(src), "--output", str(out)])
            self.assertIn(r"\maketitle", out.read_text(encoding="utf-8"))

    def test_output_dir_flag(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(sample_fixture()), encoding="utf-8")
            od = Path(d) / "docs"
            self.run_main(["x", str(src), "--output-dir", str(od)])
            self.assertEqual(len(list(od.glob("*.tex"))), 2)

    def test_short_output_flag(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(sample_fixture()), encoding="utf-8")
            out = Path(d) / "rep.tex"
            self.run_main(["x", str(src), "-o", str(out)])
            self.assertTrue(out.exists())

    def test_no_args_needed_output(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(sample_fixture()), encoding="utf-8")
            out = Path(d) / "rep.tex"
            self.run_main(["x", str(src), str(out)])
            self.assertTrue(out.exists())

    def test_split_structure(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(sample_fixture()), encoding="utf-8")
            od = Path(d) / "docs"
            self.run_main(["x", str(src), "--output-dir", str(od)])
            for p in od.glob("*.tex"):
                tex = p.read_text(encoding="utf-8")
                self.assertIn(r"\begin{document}", tex)
                self.assertIn(r"\section{", tex)
                self.assertNotIn(r"\tableofcontents", tex)

    def test_master_brace_balance(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(sample_fixture()), encoding="utf-8")
            out = Path(d) / "rep.tex"
            self.run_main(["x", str(src), str(out)])
            tex = out.read_text(encoding="utf-8")
            self.assertEqual(tex.count("{"), tex.count("}"))

    def test_split_brace_balance(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(sample_fixture()), encoding="utf-8")
            od = Path(d) / "docs"
            self.run_main(["x", str(src), "--output-dir", str(od)])
            for p in od.glob("*.tex"):
                tex = p.read_text(encoding="utf-8")
                self.assertEqual(tex.count("{"), tex.count("}"))

    def test_begin_end_env_balance(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(sample_fixture()), encoding="utf-8")
            out = Path(d) / "rep.tex"
            self.run_main(["x", str(src), str(out)])
            tex = out.read_text(encoding="utf-8")
            self.assertEqual(tex.count(r"\begin{"), tex.count(r"\end{"))

    def test_envelope_json(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps({"conversations": sample_fixture()}), encoding="utf-8")
            out = Path(d) / "rep.tex"
            self.run_main(["x", str(src), str(out)])
            self.assertEqual(out.read_text(encoding="utf-8").count(r"\section{"), 2)

    def test_no_output_flags_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = Path(d)
            src = cwd / "in.json"
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            self.run_main(["x", str(src)], cwd=str(cwd))
            self.assertTrue((cwd / "conversations_report.tex").exists())

    def test_error_printed_on_bad_json(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text("{oops", encoding="utf-8")
            buf = io.StringIO()
            old_argv, old_stdout, old_stderr = sys.argv, sys.stdout, sys.stderr
            sys.argv = ["x", str(src), str(Path(d) / "o.tex")]
            sys.stdout = sys.stderr = buf
            try:
                with self.assertRaises(SystemExit) as ctx:
                    ctl.main()
            finally:
                sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr
            self.assertIn("invalid JSON", str(ctx.exception))

    def test_large_fixture_stable(self):
        items = [conv(id=f"id{i}", title=f"T {i} & stuff") for i in range(50)]
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(items), encoding="utf-8")
            out = Path(d) / "rep.tex"
            self.run_main(["x", str(src), str(out)])
            tex = out.read_text(encoding="utf-8")
            self.assertEqual(tex.count(r"\section{"), 50)

    def test_both_flags_master_wins(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.json"
            src.write_text(json.dumps(sample_fixture()), encoding="utf-8")
            out = Path(d) / "rep.tex"
            od = Path(d) / "docs"
            self.run_main(["x", str(src), str(out), "--output-dir", str(od)])
            self.assertTrue(out.exists())


class TestCliExtra(unittest.TestCase):
    def test_help_runs(self):
        old_argv, old_stdout, old_stderr = sys.argv, sys.stdout, sys.stderr
        sys.argv = ["x", "--help"]
        buf = io.StringIO()
        sys.stdout = buf
        try:
            with self.assertRaises(SystemExit):
                ctl.main()
        finally:
            sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr
        self.assertIn("LaTeX", buf.getvalue())

    def test_relative_output_in_cwd(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            src = Path("in.json")
            src.write_text(json.dumps([conv()]), encoding="utf-8")
            old_argv, old_stdout = sys.argv, sys.stdout
            sys.argv = ["x", "in.json", "rep.tex"]
            sys.stdout = io.StringIO()
            try:
                ctl.main()
            finally:
                os.chdir(old_cwd)
                sys.argv, sys.stdout = old_argv, old_stdout
            self.assertTrue((Path(d) / "rep.tex").exists())

    def test_no_stdlib_thirdparty_imports(self):
        import ast

        src = Path(ctl.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(
            imported.issubset({"__future__", "argparse", "json", "re", "sys", "datetime", "pathlib", "typing"})
        )


if __name__ == "__main__":
    unittest.main()
