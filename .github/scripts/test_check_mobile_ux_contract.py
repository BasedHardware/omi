#!/usr/bin/env python3
"""Unit tests for check_mobile_ux_contract.py (INV-UI-3).

Each rule gets a case that proves it fires on the defect it targets, and the ratchet gets cases
that prove it passes with an allow comment, on an unchanged count and on a decrease.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from check_mobile_ux_contract import RULE_IDS, compare, count_hits, is_contract_source
from check_mobile_ux_contract import main as _main


def main(argv: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return _main(argv)


# One violating snippet per rule, each the shape of a defect that shipped (audit 2026-09-23).
VIOLATIONS: dict[str, str] = {
    "raw-back-glyph": "leading: IconButton(icon: const Icon(Icons.arrow_back_ios_new), onPressed: pop),",
    "page-route-builder": "Navigator.pushReplacement(context, PageRouteBuilder(pageBuilder: (_, __, ___) => page));",
    "raw-bottom-sheet": "showModalBottomSheet(context: context, builder: (_) => const Sheet());",
    "raw-dialog": "showDialog(context: context, builder: (_) => AlertDialog(title: title));",
    "raw-snackbar": "ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));",
    "raw-clipboard": "await Clipboard.setData(ClipboardData(text: text));",
    "date-pattern": "final label = DateFormat('h:mm a').format(date);",
    "color-literal": "color: const Color(0xFF1F1F25),",
    "font-size-literal": "style: const TextStyle(fontSize: 13),",
    "radius-literal": "borderRadius: BorderRadius.circular(12),",
    "raw-spinner": "child: const CircularProgressIndicator(),",
    "three-dot-ellipsis": "hintText: 'Search conversations...',",
    "hardcoded-text": "child: const Text('Link Event'),",
    # Outcome rules (§17, audit 2026-11-19).
    "silent-catch": "try { await save(); } catch (e) { Logger.debug('save failed: $e'); }",
    "generic-error": "OmiFeedback.error(context, context.l10n.somethingWentWrong);",
    "material-page-route": "Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));",
    "pop-before-await": "onPressed: () async { Navigator.pop(context); await provider.submitApp(); },",
}


class RuleTests(unittest.TestCase):
    def test_every_rule_has_a_violation_case(self) -> None:
        self.assertEqual(set(VIOLATIONS), set(RULE_IDS))

    def test_each_rule_fires_on_its_defect(self) -> None:
        for rule_id, snippet in VIOLATIONS.items():
            with self.subTest(rule=rule_id):
                counts = count_hits(snippet)
                self.assertEqual(counts[rule_id], 1, counts)

    def test_allow_comment_with_reason_suppresses_the_hit(self) -> None:
        for rule_id, snippet in VIOLATIONS.items():
            with self.subTest(rule=rule_id):
                allowed = f"{snippet} // omi-ux-allow: {rule_id} -- fixed-scale illustration"
                self.assertEqual(count_hits(allowed)[rule_id], 0)

    def test_allow_comment_on_a_multi_line_hit_goes_on_the_first_line(self) -> None:
        text = "try {\n  x();\n} catch (_) { // omi-ux-allow: silent-catch -- best-effort cache warm\n}\n"
        self.assertEqual(count_hits(text)["silent-catch"], 0)

    def test_allow_comment_without_reason_is_ignored(self) -> None:
        line = VIOLATIONS["color-literal"] + " // omi-ux-allow: color-literal"
        self.assertEqual(count_hits(line)["color-literal"], 1)

    def test_allow_comment_names_the_rule_it_excuses(self) -> None:
        line = VIOLATIONS["color-literal"] + " // omi-ux-allow: font-size-literal -- wrong rule"
        self.assertEqual(count_hits(line)["color-literal"], 1)
        both = "Text('Hi', style: TextStyle(fontSize: 9)) // omi-ux-allow: hardcoded-text, font-size-literal -- demo"
        counts = count_hits(both)
        self.assertEqual(counts["hardcoded-text"], 0)
        self.assertEqual(counts["font-size-literal"], 0)


class PrecisionTests(unittest.TestCase):
    def test_primitives_and_their_callers_are_not_counted(self) -> None:
        text = "\n".join(
            [
                "showOmiSheet(context: context, builder: (_) => const Sheet());",
                "builder: (_) => OmiAlertDialog(title: title, actions: const []),",
                "OmiFeedback.confirm(context, l10n.copied);",
                "messenger.showSnackBar(snackBar);",
                "await OmiClipboard.copy(context, text);",
                "final time = OmiDateFormat.of(context).time(date);",
                "DateFormat.jm(locale).format(date);",
                "const OmiSpinner();",
                "Text(context.l10n.save),",
                "leading: const OmiBackButton(),",
            ]
        )
        self.assertEqual(sum(count_hits(text).values()), 0, count_hits(text))

    def test_comments_do_not_count(self) -> None:
        text = "// AlertDialog( with Color(0xFF000000) and fontSize: 12\n/// Use SnackBar( never.\n"
        self.assertEqual(sum(count_hits(text).values()), 0)

    def test_trailing_comment_after_code_does_not_count(self) -> None:
        self.assertEqual(count_hits("foo(); // was SnackBar(content: x)")["raw-snackbar"], 0)

    def test_url_in_string_is_not_a_comment(self) -> None:
        # `//` inside a string literal must not hide a real hit later on the line.
        self.assertEqual(count_hits("launch('https://omi.me'); Color(0xFF000000);")["color-literal"], 1)

    def test_spread_operator_is_not_an_ellipsis(self) -> None:
        self.assertEqual(count_hits("children: ['a', ...rows, 'b'],")["three-dot-ellipsis"], 0)
        self.assertEqual(count_hits("if (x) ...[const Divider()],")["three-dot-ellipsis"], 0)

    def test_ellipsis_character_is_fine(self) -> None:
        self.assertEqual(count_hits("hintText: 'Search…',")["three-dot-ellipsis"], 0)

    def test_text_without_letters_is_not_hardcoded_copy(self) -> None:
        for snippet in ("Text('${count}')", "Text('$count')", "Text('•')", "Text(' · ')", "Text('12:00')"):
            with self.subTest(snippet=snippet):
                self.assertEqual(count_hits(snippet)["hardcoded-text"], 0)

    def test_text_with_interpolation_and_words_is_hardcoded(self) -> None:
        self.assertEqual(count_hits("Text('$count items')")["hardcoded-text"], 1)
        self.assertEqual(count_hits('Text(\n  "Exported to ${name}",\n)')["hardcoded-text"], 1)

    def test_chevron_left_counts_only_as_a_leading_control(self) -> None:
        self.assertEqual(count_hits("IconButton(icon: Icon(Icons.chevron_left), onPressed: prevMonth)")["raw-back-glyph"], 0)
        self.assertEqual(
            count_hits("AppBar(leading: IconButton(icon: Icon(Icons.chevron_left), onPressed: pop))")["raw-back-glyph"], 1
        )

    def test_date_helper_with_pattern_counts(self) -> None:
        self.assertEqual(count_hits("dateTimeFormat('MMM d', date)")["date-pattern"], 1)
        self.assertEqual(count_hits("dateTimeFormat(pattern, date)")["date-pattern"], 0)

    def test_catch_that_reports_or_recovers_is_not_silent(self) -> None:
        for snippet in (
            "try { a(); } catch (e) { OmiFeedback.error(context, l10n.couldNotSave); }",
            "try { a(); } catch (e) { setState(() => _error = e); }",
            "try { a(); } catch (e) { Logger.debug('x'); rethrow; }",
            "try { a(); } on StateError catch (_) { return null; }",
        ):
            with self.subTest(snippet=snippet):
                self.assertEqual(count_hits(snippet)["silent-catch"], 0)

    def test_empty_and_log_only_catches_are_silent(self) -> None:
        for snippet in (
            "try { a(); } catch (_) {}",
            "try { a(); } catch (_) {\n  // Offline: ignore.\n}",
            "try { a(); } on Exception catch (e, st) { Logger.error('a', e, st); debugPrint('b'); }",
            "try { a(); } catch (e) { Logger.debug('braces { in } a string; $e'); }",
        ):
            with self.subTest(snippet=snippet):
                self.assertEqual(count_hits(snippet)["silent-catch"], 1)

    def test_silent_catch_applies_to_pages_and_providers_only(self) -> None:
        snippet = VIOLATIONS["silent-catch"]
        self.assertEqual(count_hits(snippet, "app/lib/pages/foo.dart")["silent-catch"], 1)
        self.assertEqual(count_hits(snippet, "app/lib/providers/foo.dart")["silent-catch"], 1)
        self.assertEqual(count_hits(snippet, "app/lib/services/foo.dart")["silent-catch"], 0)
        self.assertEqual(compare("app/lib/services/foo.dart", snippet, None), [])

    def test_generic_error_with_an_action_passes(self) -> None:
        text = (
            "OmiFeedback.error(\n  context,\n  l10n.somethingWentWrong,\n"
            "  actionLabel: l10n.tryAgain,\n  onAction: retry,\n);"
        )
        self.assertEqual(count_hits(text)["generic-error"], 0)
        self.assertEqual(count_hits("OmiErrorState(message: l10n.somethingWentWrongTryAgain)")["generic-error"], 1)
        # A page state's retry is a way forward too.
        self.assertEqual(
            count_hits("OmiErrorState(message: l10n.somethingWentWrong, onRetry: load)")["generic-error"], 0
        )
        # A label with nothing to run renders no action, so it is still a dead end.
        self.assertEqual(
            count_hits("OmiFeedback.error(context, l10n.somethingWentWrong, actionLabel: l10n.tryAgain);")[
                "generic-error"
            ],
            1,
        )
        # The action has to be in the same call, not a neighbouring one.
        self.assertEqual(
            count_hits("show(a(l10n.somethingWentWrong), b(actionLabel: l10n.tryAgain));")["generic-error"], 1
        )

    def test_commented_out_material_page_route_is_not_counted(self) -> None:
        self.assertEqual(count_hits("// Navigator.push(context, MaterialPageRoute(builder: b));")["material-page-route"], 0)
        self.assertEqual(count_hits("/* MaterialPageRoute(builder: b) */")["material-page-route"], 0)

    def test_omi_page_route_is_not_material_page_route(self) -> None:
        self.assertEqual(count_hits("Navigator.of(context).push(omiPageRoute((_) => page));")["material-page-route"], 0)
        self.assertEqual(count_hits("Navigator.push<void>(context, MaterialPageRoute<void>(builder: b));")["material-page-route"], 1)

    def test_pop_after_the_request_or_into_the_next_surface_passes(self) -> None:
        for snippet in (
            "onPressed: () async { final ok = await provider.submitApp(); if (ok) Navigator.pop(context); },",
            "OmiDialogAction(label: l10n.cancel, onPressed: () => Navigator.pop(context, false)),",
            "onTap: () async { Navigator.pop(context); await showOmiConfirm(context, title: t); await provider.clear(); },",
            "onPressed: () async { Navigator.of(ctx).pop(); await openAppSettings(); },",
            "void _pick(Choice c) => Navigator.of(context).pop(c);\nFuture<void> other() async { await api.load(); }",
            "switch (o) {\n  case A.paid:\n    Navigator.of(context).pop(true);\n  case A.free:\n    await tell('free');\n}",
        ):
            with self.subTest(snippet=snippet):
                self.assertEqual(count_hits(snippet)["pop-before-await"], 0)

    def test_pop_then_request_in_the_same_block_counts(self) -> None:
        text = "Future<void> _apply() async {\n  if (mounted) Navigator.of(context).pop();\n  await startSummary(provider, appId);\n}"
        self.assertEqual(count_hits(text)["pop-before-await"], 1)

    def test_scope(self) -> None:
        self.assertTrue(is_contract_source("app/lib/pages/chat/page.dart"))
        self.assertFalse(is_contract_source("app/lib/ui/feedback/omi_feedback.dart"))
        self.assertFalse(is_contract_source("app/lib/l10n/app_localizations_en.dart"))
        self.assertFalse(is_contract_source("app/lib/gen/pigeon.g.dart"))
        self.assertFalse(is_contract_source("app/lib/backend/schema/conversation.g.dart"))
        self.assertFalse(is_contract_source("app/test/foo_test.dart"))
        self.assertFalse(is_contract_source("desktop/macos/Desktop/Sources/Foo.swift"))


class RatchetTests(unittest.TestCase):
    PATH = "app/lib/pages/example.dart"

    def test_increase_fails(self) -> None:
        base = VIOLATIONS["raw-dialog"]
        head = base + "\n" + VIOLATIONS["raw-dialog"]
        regressions = compare(self.PATH, head, base)
        self.assertEqual(len(regressions), 1)
        self.assertIn("raw-dialog 1 → 2", regressions[0])
        self.assertIn("showOmiConfirm", regressions[0])

    def test_new_file_starts_at_zero(self) -> None:
        regressions = compare(self.PATH, VIOLATIONS["raw-snackbar"], None)
        self.assertEqual(len(regressions), 1)

    def test_unchanged_and_decreasing_counts_pass(self) -> None:
        base = VIOLATIONS["raw-dialog"] + "\n" + VIOLATIONS["raw-dialog"]
        self.assertEqual(compare(self.PATH, base, base), [])
        self.assertEqual(compare(self.PATH, VIOLATIONS["raw-dialog"], base), [])

    def test_rules_are_counted_separately(self) -> None:
        # Removing a dialog does not buy an extra snackbar.
        base = VIOLATIONS["raw-dialog"]
        head = VIOLATIONS["raw-snackbar"]
        regressions = compare(self.PATH, head, base)
        self.assertEqual(len(regressions), 1)
        self.assertIn("raw-snackbar", regressions[0])

    def test_allowed_increase_passes(self) -> None:
        head = VIOLATIONS["color-literal"] + " // omi-ux-allow: color-literal -- brand gradient stop"
        self.assertEqual(compare(self.PATH, head, None), [])


class CliTests(unittest.TestCase):
    """End to end through git: base commit, head working tree, --changed-files."""

    def _git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    def test_cli_fails_on_increase_and_passes_on_decrease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "t@example.com")
            self._git(root, "config", "user.name", "t")
            target = root / "app/lib/pages/example.dart"
            target.parent.mkdir(parents=True)
            target.write_text(VIOLATIONS["raw-dialog"] + "\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "base")
            changed = root / "changed.txt"
            changed.write_text("app/lib/pages/example.dart\n", encoding="utf-8")

            target.write_text(VIOLATIONS["raw-dialog"] + "\n" + VIOLATIONS["raw-dialog"] + "\n", encoding="utf-8")
            args = ["--changed-files", str(changed), "--base", "HEAD", "--root", str(root)]
            self.assertEqual(main(args), 1)

            target.write_text("builder: (_) => OmiAlertDialog(title: t, actions: const []),\n", encoding="utf-8")
            self.assertEqual(main(args), 0)

    def test_cli_requires_base_when_sources_changed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "changed.txt"
            changed.write_text("app/lib/pages/example.dart\n", encoding="utf-8")
            self.assertEqual(main(["--changed-files", str(changed), "--root", tmp]), 1)

    def test_cli_ignores_files_outside_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "changed.txt"
            changed.write_text("backend/main.py\napp/lib/ui/feedback/omi_feedback.dart\n", encoding="utf-8")
            self.assertEqual(main(["--changed-files", str(changed), "--root", tmp]), 0)


if __name__ == "__main__":
    unittest.main()
