#!/usr/bin/env python3
"""Unit tests for check_mobile_ui_isolate.py (INV-PERF-1).

Each rule gets a case that proves it fires on the defect it targets, the ratchet gets cases
that prove it passes with an allow comment, on an unchanged count and on a decrease, and the
provider graph check gets a case per shape of proxy update hook.
"""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check_mobile_ui_isolate import (
    RULE_IDS,
    SEMANTICS_ALLOWLIST,
    _mask,
    check_semantics,
    check_provider_graph,
    compare,
    count_hits,
    hook_violations,
    is_contract_source,
    proxy_hooks,
)
from check_mobile_ui_isolate import main as _main


def main(argv: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return _main(argv)


PROVIDER = "app/lib/providers/foo_provider.dart"
WAL_INDEX = "app/lib/utils/wal_file_manager.dart"

# One violating snippet per rule, each the shape of a defect found in the 2026-10 lag audit.
VIOLATIONS: dict[str, str] = {
    "forced-semantics": "SemanticsBinding.instance.ensureSemantics();",
    "global-input-listener": "return Listener(onPointerMove: observe, child: child);",
    "unselected-provider-listener": "CaptureProvider capture;\ncapture.addListener(onCapture);",
    "json-in-build": "Widget build(BuildContext context) => Text(jsonDecode(raw));",
    "sort-in-build": "Widget build(BuildContext context) {\n final rows = items..sort(compare);\n return list;\n}",
    "list-item-layer": "ListView.builder(itemBuilder: (c, i) => Opacity(opacity: .5, child: row));",
    "sync-file-io": "for (final entity in dir.listSync().whereType<File>()) {",
    "json-in-provider": "SharedPreferencesUtil().cache = jsonEncode(conversations);",
    "history-json-on-ui": "final jsonString = jsonEncode(jsonData);",
    "fast-periodic-timer": "_timer = Timer.periodic(const Duration(milliseconds: 16), (_) => notifyListeners());",
    "blur-filter": "child: BackdropFilter(filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18), child: box),",
    "unsized-network-image": "child: CachedNetworkImage(imageUrl: app.image, width: 15, height: 15),",
    "shrink-wrap-list": "ListView.builder(shrinkWrap: true, itemCount: n, itemBuilder: build)",
}
# blur-filter's snippet holds two hits (the widget and the filter).
EXPECTED_COUNT = {"blur-filter": 2}


class RuleTests(unittest.TestCase):
    def test_every_rule_has_a_violation_case(self) -> None:
        self.assertEqual(set(VIOLATIONS), set(RULE_IDS))

    @staticmethod
    def _path(rule_id: str) -> str:
        return WAL_INDEX if rule_id == "history-json-on-ui" else PROVIDER

    def test_each_rule_fires_on_its_defect(self) -> None:
        for rule_id, snippet in VIOLATIONS.items():
            with self.subTest(rule=rule_id):
                counts = count_hits(snippet, self._path(rule_id))
                self.assertEqual(counts[rule_id], EXPECTED_COUNT.get(rule_id, 1), counts)

    def test_allow_comment_on_the_line_suppresses_the_hit(self) -> None:
        for rule_id, snippet in VIOLATIONS.items():
            with self.subTest(rule=rule_id):
                allowed = "\n".join(f"{line} // omi-perf-allow: {rule_id} -- measured, bounded input" for line in snippet.splitlines())
                self.assertEqual(count_hits(allowed, self._path(rule_id))[rule_id], int(rule_id == "forced-semantics"))

    def test_allow_comment_on_the_line_above_suppresses_the_hit(self) -> None:
        for rule_id, snippet in VIOLATIONS.items():
            with self.subTest(rule=rule_id):
                allowed = "\n".join(f"  // omi-perf-allow: {rule_id} -- measured, bounded input\n{line}" for line in snippet.splitlines())
                self.assertEqual(count_hits(allowed, self._path(rule_id))[rule_id], int(rule_id == "forced-semantics"))

    def test_allow_comment_without_reason_is_ignored(self) -> None:
        snippet = VIOLATIONS["sync-file-io"] + " // omi-perf-allow: sync-file-io"
        self.assertEqual(count_hits(snippet, PROVIDER)["sync-file-io"], 1)

    def test_allow_for_another_rule_does_not_suppress(self) -> None:
        snippet = VIOLATIONS["sync-file-io"] + " // omi-perf-allow: blur-filter -- unrelated"
        self.assertEqual(count_hits(snippet, PROVIDER)["sync-file-io"], 1)

    def test_comments_and_strings_do_not_count(self) -> None:
        self.assertEqual(count_hits("// dir.listSync() used to block here", PROVIDER)["sync-file-io"], 0)
        self.assertEqual(count_hits("final s = 'file.existsSync()';", PROVIDER)["sync-file-io"], 0)

    def test_interpolated_code_counts(self) -> None:
        self.assertEqual(count_hits("final s = 'raw: ${file.readAsStringSync()}';", PROVIDER)["sync-file-io"], 1)
        self.assertEqual(count_hits("log('index ${jsonEncode(history)}');", WAL_INDEX)["history-json-on-ui"], 1)
        self.assertEqual(count_hits("final s = 'call file.existsSync() later';", PROVIDER)["sync-file-io"], 0)

    def test_async_io_is_clean(self) -> None:
        clean = "final files = await dir.list().toList(); if (await file.exists()) await file.readAsString();"
        self.assertEqual(count_hits(clean, PROVIDER)["sync-file-io"], 0)

    def test_json_rule_only_applies_to_providers(self) -> None:
        snippet = VIOLATIONS["json-in-provider"]
        self.assertEqual(count_hits(snippet, "app/lib/backend/http/api/conversations.dart")["json-in-provider"], 0)
        self.assertEqual(count_hits(snippet, "app/lib/pages/foo/bar_provider.dart")["json-in-provider"], 1)

    def test_microsecond_timer_counts(self) -> None:
        snippet = "Timer.periodic(const Duration(microseconds: 16667), (_) => tick());"
        self.assertEqual(count_hits(snippet, PROVIDER)["fast-periodic-timer"], 1)

    def test_history_json_inside_off_ui_isolate_is_clean(self) -> None:
        wrapped = (
            "final s = await offUiIsolate(() => jsonEncode(jsonData),\n"
            "    size: wals.length, threshold: backgroundEncodeThreshold);"
        )
        self.assertEqual(count_hits(wrapped, WAL_INDEX)["history-json-on-ui"], 0)
        unwrapped = "final s = jsonEncode(jsonData);"
        self.assertEqual(count_hits(unwrapped, WAL_INDEX)["history-json-on-ui"], 1)
        self.assertEqual(count_hits(unwrapped, "app/lib/backend/http/api/apps.dart")["history-json-on-ui"], 0)

    def test_a_comment_naming_the_wrapper_does_not_exempt_json(self) -> None:
        text = "// Large indexes go through offUiIsolate(\nfinal s = jsonEncode(jsonData);\nfinal t = 'offUiIsolate(';\nfinal u = jsonEncode(other);"
        self.assertEqual(count_hits(text, WAL_INDEX)["history-json-on-ui"], 2)

    def test_removing_the_off_ui_isolate_wrapper_fails_the_ratchet(self) -> None:
        base = "final s = await offUiIsolate(() => jsonEncode(data), size: n, threshold: t);"
        head = "final s = jsonEncode(data);"
        self.assertTrue(compare(WAL_INDEX, head, base))

    def test_slow_periodic_timer_is_clean(self) -> None:
        snippet = "Timer.periodic(const Duration(milliseconds: 500), (_) => tick());"
        self.assertEqual(count_hits(snippet, PROVIDER)["fast-periodic-timer"], 0)
        self.assertEqual(count_hits("Timer.periodic(const Duration(seconds: 1), tick);", PROVIDER)["fast-periodic-timer"], 0)

    def test_sized_network_image_is_clean(self) -> None:
        sized = "CachedNetworkImage(imageUrl: url, memCacheWidth: (15 * dpr).round(), width: 15)"
        self.assertEqual(count_hits(sized, PROVIDER)["unsized-network-image"], 0)
        resized = "Image(image: ResizeImage(NetworkImage(url), width: 120))"
        self.assertEqual(count_hits(resized, PROVIDER)["unsized-network-image"], 0, "ResizeImage sizes the decode")
        self.assertEqual(
            count_hits("Image.network(url, cacheWidth: 240, fit: BoxFit.cover)", PROVIDER)["unsized-network-image"], 0
        )

    def test_shrink_wrap_false_is_clean(self) -> None:
        self.assertEqual(count_hits("ListView(shrinkWrap: false)", PROVIDER)["shrink-wrap-list"], 0)

    def test_scope(self) -> None:
        self.assertTrue(is_contract_source("app/lib/providers/capture_provider.dart"))
        self.assertTrue(is_contract_source("app/lib/ui/components/omi_locked_preview.dart"))
        self.assertFalse(is_contract_source("app/lib/gen/pigeon_communicator.g.dart"))
        self.assertFalse(is_contract_source("app/lib/env/dev_env.g.dart"))
        self.assertFalse(is_contract_source("app/test/foo_test.dart"))


class ReviewRegressionTests(unittest.TestCase):
    def test_selected_guard_must_compare_selected_and_stored_value(self):
        template = """CaptureProvider capture;
void initState() { capture.addListener(onCapture); }
void onCapture() {
 final next = capture.version;
 if (CONDITION) return;
 _version = next;
 work();
}"""
        for condition in ("next > 0 && _version == 0", "!identical(next, _version)", "!(next == _version)", "identical(next, _version) == false"):
            self.assertEqual(count_hits(template.replace("CONDITION", condition))["unselected-provider-listener"], 1, condition)
        for condition in ("next == _version", "identical(next, _version)", "_version == next"):
            self.assertEqual(count_hits(template.replace("CONDITION", condition))["unselected-provider-listener"], 0, condition)

    def test_positional_sliver_rows_inline_and_named(self):
        for body in ("Opacity(opacity: .5, child: row)", "CustomPaint(painter: canvas..saveLayer(bounds, paint))"):
            self.assertEqual(count_hits(f"SliverChildBuilderDelegate((c, i) => {body})")["list-item-layer"], 1)
        text = """SliverChildBuilderDelegate(buildRow);
Widget buildRow(BuildContext c, int i) => Opacity(opacity: .5, child: row);"""
        self.assertEqual(count_hits(text)["list-item-layer"], 1)

    def test_all_scroll_notification_subclasses_are_input(self):
        for kind in ("OverscrollNotification", "UserScrollNotification", "ScrollStartNotification", "ScrollUpdateNotification", "ScrollEndNotification", "ScrollMetricsNotification"):
            self.assertEqual(count_hits(f"NotificationListener<{kind}>(onNotification: work, child: child)")["global-input-listener"], 1, kind)

    def test_named_listener_cannot_borrow_another_class_guard(self):
        text = """class A {
 CaptureProvider capture;
 void initState() { capture.addListener(onCapture); }
 void onCapture() {
  final next = capture.version;
  if (next == _version) return;
  _version = next;
  work();
 }
}
class B {
 CaptureProvider capture;
 void initState() { capture.addListener(onCapture); }
 void onCapture() { work(); }
}"""
        self.assertEqual(count_hits(text)["unselected-provider-listener"], 1)

    def test_build_helpers_do_not_visit_other_class_data_methods(self):
        text = """class A {
 Widget build(BuildContext c) => helper();
 Widget helper() => Text('x');
}
class B {
 void load() { helper(); }
 void helper() { jsonDecode(raw); items..sort(compare); }
}"""
        self.assertEqual(count_hits(text)["json-in-build"], 0)
        self.assertEqual(count_hits(text)["sort-in-build"], 0)
        self.assertEqual(count_hits(text.replace("Text('x')", "Text(jsonDecode(raw))"))["json-in-build"], 1)

    def test_forwarded_widget_fields_and_aliases_are_not_name_dependent(self):
        for name in ("content", "body", "page"):
            template = f"""class Wrapper extends StatelessWidget {{
 final Widget {name};
 Widget build(BuildContext c) => Listener(onPointerMove: work, child: CHILD);
}}"""
            for child in (name, f"widget.{name}"):
                self.assertEqual(count_hits(template.replace("CHILD", child))["global-input-listener"], 1)
        alias = """class Wrapper {
 final Widget content;
 Widget build(BuildContext c) {
  final forwarded = content;
  return Listener(onPointerMove: work, child: forwarded);
 }
}"""
        self.assertEqual(count_hits(alias)["global-input-listener"], 1)
        local = "Widget build(BuildContext c) { final Widget content = Slider(); return Listener(onPointerMove: work, child: content); }"
        self.assertEqual(count_hits(local)["global-input-listener"], 0)


class ScopedRatchetTests(unittest.TestCase):
    def test_all_new_mutations_fail_on_new_and_existing_files(self) -> None:
        for rule in ("global-input-listener", "unselected-provider-listener", "json-in-build", "sort-in-build", "list-item-layer"):
            snippet = VIOLATIONS[rule]
            with self.subTest(rule=rule):
                self.assertTrue(any(rule in problem for problem in compare(PROVIDER, snippet, None)))
                self.assertEqual(compare(PROVIDER, snippet, snippet), [])
                self.assertEqual(compare(PROVIDER, "", snippet), [])
                self.assertTrue(any(rule in problem for problem in compare(PROVIDER, snippet + "\n" + snippet, snippet)))

    def test_semantics_is_absolute_even_in_existing_files(self) -> None:
        snippet = VIOLATIONS["forced-semantics"]
        self.assertTrue(compare(PROVIDER, snippet, snippet))
        self.assertTrue(compare(PROVIDER, snippet, "void existing() {}"))
        self.assertTrue(compare(PROVIDER, snippet + " // omi-perf-allow: forced-semantics -- reason", snippet))

    def test_semantics_allowlist_is_call_specific_and_single_use(self) -> None:
        snippet = VIOLATIONS["forced-semantics"]
        key = (PROVIDER, "SemanticsBinding.instance.ensureSemantics();")
        with patch.dict(SEMANTICS_ALLOWLIST, {key: "reviewed explicit accessibility owner"}):
            self.assertEqual(count_hits(snippet, PROVIDER)["forced-semantics"], 0)
            self.assertEqual(count_hits(snippet + "\n" + snippet, PROVIDER)["forced-semantics"], 1)
            self.assertEqual(count_hits(snippet, "app/lib/existing.dart")["forced-semantics"], 1)
            self.assertEqual(count_hits("other.ensureSemantics();", PROVIDER)["forced-semantics"], 1)

    def test_mask_handles_multiline_nested_comments_raw_strings_and_interpolation(self) -> None:
        for rule, snippet in VIOLATIONS.items():
            with self.subTest(rule=rule):
                # A comment starts on a different line; ordinary per-line regex masking misses this.
                for masked in (f"/* outer\n /* nested */\n{snippet}\n*/", f"final s = r'''\n{snippet}\n''';", f'final s = """\n{snippet}\n""";'):
                    self.assertEqual(count_hits(masked, PROVIDER)[rule], 0)
        text = "final url = 'https://example.com';\nfinal s = '${SemanticsBinding.instance.ensureSemantics()}';"
        self.assertEqual(len(_mask(text)), len(text))
        self.assertEqual(count_hits(text, PROVIDER)["forced-semantics"], 1)
        self.assertEqual(count_hits("final s = r'${ensureSemantics()}';", PROVIDER)["forced-semantics"], 0)

    def test_local_gestures_and_domain_notifications_are_not_global_input(self) -> None:
        for snippet in (
            "Listener(onPointerMove: drag, child: Slider(value: value));",
            "Listener(onPointerUp: commit, child: child);",
            "NotificationListener<SelectAppNotification>(onNotification: selectApp, child: child);",
            "Listener(child: child);",
            "NotificationListener<ScrollNotification>(onNotification: (_) => false, child: child);",
            "Listener(onPointerMove: (_) {}, child: child);",
        ):
            self.assertEqual(count_hits(snippet)["global-input-listener"], 0, snippet)
        for snippet in (
            "NotificationListener<ScrollNotification>(onNotification: observe, child: child);",
            "NotificationListener(onNotification: observe, child: widget.child);",
            "Listener(onPointerDown: inspect, child: MaterialApp(home: home));",
        ):
            self.assertEqual(count_hits(snippet)["global-input-listener"], 1, snippet)
        self.assertEqual(count_hits("Listener(onPointerMove: inspect, child: guidedContent)", "app/lib/main.dart")["global-input-listener"], 1)
        self.assertEqual(count_hits("Listener(onPointerUp: commit, child: Listener(onPointerMove: drag, child: child));")["global-input-listener"], 1)

    def test_provider_types_aliases_inline_and_named_callbacks(self) -> None:
        for snippet in (
            "final p = context.read<CaptureProvider>();\np.addListener(onChange);",
            "context.read<SyncProvider>().addListener(() { setState(() {}); });",
            "final p = Provider.of<MessageProvider>(context, listen: false);\np.addListener(refresh);",
            "CaptureProvider _capture;\n_capture?.addListener(_onCapture);",
            "CaptureProvider _capture;\n_capture..addListener(_onCapture);",
            "CaptureProvider capture;\nfinal first = capture;\nfinal second = first;\nsecond.addListener(refresh);",
        ):
            self.assertEqual(count_hits(snippet)["unselected-provider-listener"], 1, snippet)
        for snippet in (
            "FocusNode focus;\nfocus.addListener(onFocus);",
            "AnimationController controller;\ncontroller.addListener(paint);",
            "ValueNotifier<int> tick;\ntick.addListener(paint);",
            "CaptureProvider capture;\ncapture.waveformTick.addListener(paint);",
            "Selector<CaptureProvider, int>(selector: (_, p) => p.version, builder: build);",
        ):
            self.assertEqual(count_hits(snippet)["unselected-provider-listener"], 0, snippet)
        unrelated_selector = "Selector<CaptureProvider, int>(selector: (_, p) => p.version, builder: build);"
        self.assertEqual(count_hits(VIOLATIONS["unselected-provider-listener"] + unrelated_selector)["unselected-provider-listener"], 1)

    def test_adding_callback_to_existing_global_wrapper_is_an_increase(self) -> None:
        base = "Listener(onPointerDown: inspect, child: child);"
        head = "Listener(onPointerDown: inspect, onPointerMove: walkTree, child: child);"
        self.assertEqual(count_hits(base)["global-input-listener"], 1)
        self.assertEqual(count_hits(head)["global-input-listener"], 2)
        self.assertTrue(any("global-input-listener 1 → 2" in problem for problem in compare(PROVIDER, head, base)))

    def test_global_input_exception_only_covers_its_callback_line(self) -> None:
        text = """Listener(
  // omi-perf-allow: global-input-listener -- one bounded on-demand hit test
  onPointerDown: inspect,
  onPointerMove: walkTree,
  child: child,
);"""
        self.assertEqual(count_hits(text)["global-input-listener"], 1)

    def test_selected_callback_requires_guard_before_work(self) -> None:
        text = """
CaptureProvider capture;
void initState() { capture.addListener(onCapture); }
void onCapture() {
  final next = capture.version;
  if (next == _version) return;
  _version = next;
  setState(() {});
}
"""
        self.assertEqual(count_hits(text)["unselected-provider-listener"], 0)
        for changed in (
            text.replace("if (next == _version) return;", "if (disposed == true) return;"),
            text.replace("  final next", "  setState(() {});\n  final next"),
            text.replace("  final next", "  walkTranscript();\n  final next"),
            text.replace("if (next == _version) return;", "if (next == _version) logSame();"),
        ):
            self.assertEqual(count_hits(changed)["unselected-provider-listener"], 1)

    def test_json_and_sort_build_scope_and_helper_resolution(self) -> None:
        for call, rule in (("jsonDecode(raw)", "json-in-build"), ("json.decode(raw)", "json-in-build"), ("items..sort(compare)", "sort-in-build")):
            for text in (
                f"Widget build(BuildContext context) => Text({call});",
                f"build(context) => Text({call});",
                f"Widget build(BuildContext context) {{\n return helper();\n}}\nWidget helper() => Text({call});",
                f"Consumer<Foo>(builder: (c, p, child) {{ final data = {call}; return row; }});",
                f"Widget build(BuildContext c) {{ handleTap(); return Button(onPressed: handleTap); }}\nvoid handleTap() {{ final data = {call}; }}",
            ):
                self.assertEqual(count_hits(text)[rule], 1, text)
            for text in (
                f"Future<void> load() async {{ final data = {call}; }}",
                f"Widget build(BuildContext c) => row;\nvoid notCalled() {{ final data = {call}; }}",
                f"Widget build(BuildContext c) => offUiIsolate(() => {call}, size: n, threshold: t);",
                f"Widget build(BuildContext c) => Button(onPressed: () {{ final data = {call}; }});",
                f"Widget build(BuildContext c) => Button(onPressed: handleTap);\nvoid handleTap() {{ final data = {call}; }}",
            ):
                self.assertEqual(count_hits(text)[rule], 0, text)

    def test_list_layers_inline_referenced_eager_and_row_classes(self) -> None:
        for text in (
            "ListView.builder(itemBuilder: buildRow);\nWidget buildRow(c, i) => Opacity(opacity: .5, child: row);",
            "ListView(children: [Opacity(opacity: alpha, child: row)]);",
            "class ConversationListItem extends StatelessWidget {\n Widget build(BuildContext c) => Opacity(opacity: alpha, child: row);\n}",
            "class MessageRow extends StatelessWidget {\n Widget build(BuildContext c) => draw();\n void draw() { canvas.saveLayer(bounds, paint); }\n}",
            "ListView.builder(itemBuilder: (c, i) { canvas.saveLayer(bounds, paint); return row; });",
            "ListView.builder(itemBuilder: (c, i) => CustomPaint(painter: BubblePainter()));\nclass BubblePainter extends CustomPainter {\n void paint(Canvas canvas, Size size) { canvas.saveLayer(bounds, paint); }\n}",
        ):
            self.assertEqual(count_hits(text)["list-item-layer"], 1, text)
        for text in (
            "Widget build(BuildContext c) => Opacity(opacity: .5, child: hero);",
            "ListView.builder(itemBuilder: (c, i) => FadeTransition(opacity: alpha, child: row));",
            "void paint(Canvas canvas) { canvas.saveLayer(bounds, paint); }",
            "ListView.builder(itemBuilder: (c, i) => row);\nclass UnusedPainter extends CustomPainter {\n void paint(Canvas canvas, Size size) { canvas.saveLayer(bounds, paint); }\n}",
        ):
            self.assertEqual(count_hits(text)["list-item-layer"], 0, text)


class RatchetTests(unittest.TestCase):
    def test_new_file_with_a_hit_fails(self) -> None:
        self.assertTrue(compare(PROVIDER, VIOLATIONS["sync-file-io"], None))

    def test_unchanged_count_passes(self) -> None:
        text = VIOLATIONS["sync-file-io"]
        self.assertEqual(compare(PROVIDER, text, text), [])

    def test_decrease_passes(self) -> None:
        base = VIOLATIONS["sync-file-io"] + "\nfile.existsSync();"
        self.assertEqual(compare(PROVIDER, VIOLATIONS["sync-file-io"], base), [])

    def test_increase_fails_and_names_the_fix(self) -> None:
        base = VIOLATIONS["sync-file-io"]
        head = base + "\nfinal raw = file.readAsStringSync();"
        regressions = compare(PROVIDER, head, base)
        self.assertEqual(len(regressions), 1)
        self.assertIn("sync-file-io 1 → 2", regressions[0])
        self.assertIn("async File/Directory API", regressions[0])


GUARDED = """
class DeviceProvider extends ChangeNotifier {
  void setProviders(CaptureProvider provider, LocalRecordingsProvider recordings) {
    if (identical(captureProvider, provider) && identical(localRecordingsProvider, recordings)) return;
    captureProvider = provider;
    notifyListeners();
  }
}
"""
UNGUARDED = """
class CaptureController extends ChangeNotifier {
  void updateExternalActions(CaptureExternalActions? actions) {
    externalActions = actions ?? const NoopCaptureExternalActions();
    notifyListeners();
  }
}
"""
BRACED_GUARD = """
class CaptureController extends ChangeNotifier {
  void updateExternalActions(CaptureExternalActions? actions) {
    final next = actions ?? const NoopCaptureExternalActions();
    if (next == externalActions) {
      return;
    }
    externalActions = next;
    notifyListeners();
  }
}
"""
SILENT = """
class MessageProvider extends ChangeNotifier {
  void updateAppProvider(AppProvider p) {
    appProvider = p;
  }
}
"""
MAIN = """
ChangeNotifierProxyProvider<A, B>(update: (context, a, previous) => (previous?..setProviders(a, b)) ?? B()),
ChangeNotifierProxyProvider<A, C>(update: (context, a, previous) => (previous?..updateExternalActions(x)) ?? C()),
ChangeNotifierProxyProvider<A, D>(update: (context, a, previous) => (previous?..updateAppProvider(a)) ?? D()),
"""


class ProviderGraphTests(unittest.TestCase):
    def test_hooks_are_read_from_main(self) -> None:
        self.assertEqual(proxy_hooks(MAIN), ["setProviders", "updateAppProvider", "updateExternalActions"])

    def test_unguarded_notify_fails(self) -> None:
        problems = hook_violations("updateExternalActions", {"app/lib/x.dart": UNGUARDED})
        self.assertEqual(len(problems), 1)
        self.assertIn("app/lib/x.dart:3", problems[0])

    def test_guarded_notify_passes(self) -> None:
        self.assertEqual(hook_violations("setProviders", {"app/lib/x.dart": GUARDED}), [])

    def test_hook_that_never_notifies_passes(self) -> None:
        self.assertEqual(hook_violations("updateAppProvider", {"app/lib/x.dart": SILENT}), [])

    def test_allow_above_the_declaration_passes(self) -> None:
        allowed = UNGUARDED.replace(
            "  void updateExternalActions",
            "  // omi-perf-allow: proxy-hook-notify -- page derives from upstream state\n  void updateExternalActions",
        )
        self.assertEqual(hook_violations("updateExternalActions", {"app/lib/x.dart": allowed}), [])

    def test_block_form_update_calls_are_hooks(self) -> None:
        main_text = "update: (c, a, previous) {\n  previous?.setFoo(a);\n  previous!.setBaz(a);\n  return previous ?? Foo();\n}"
        self.assertEqual(proxy_hooks(main_text), ["setBaz", "setFoo"])

    def test_bang_and_bare_cascades_are_hooks(self) -> None:
        main_text = "update: (c, a, previous) => previous!..setFoo(a), update2: (c, a, previous) { return previous..setBar(a); }"
        self.assertEqual(proxy_hooks(main_text), ["setBar", "setFoo"])

    def test_async_future_hook_with_function_params_fails(self) -> None:
        text = """
  Future<void> setFoo(void Function() onDone, FooProvider p) async {
    foo = p;
    notifyListeners();
  }
"""
        self.assertEqual(len(hook_violations("setFoo", {"app/lib/x.dart": text})), 1)

    def test_arrow_hook_that_notifies_fails(self) -> None:
        text = "  void setFoo(FooProvider p) => (foo = p, notifyListeners());"
        self.assertEqual(len(hook_violations("setFoo", {"app/lib/x.dart": text})), 1)

    def test_return_in_a_nested_closure_or_comment_is_not_a_guard(self) -> None:
        text = """
  void setFoo(FooProvider p) {
    // return early when unchanged
    items.forEach((e) { return; });
    final note = 'return';
    foo = p;
    notifyListeners();
  }
"""
        self.assertEqual(len(hook_violations("setFoo", {"app/lib/x.dart": text})), 1)

    def test_braced_guard_passes(self) -> None:
        self.assertEqual(hook_violations("updateExternalActions", {"app/lib/x.dart": BRACED_GUARD}), [])

    def test_return_inside_a_loop_block_counts_but_a_closure_does_not(self) -> None:
        looped = (
            "  void setFoo(FooProvider p) {\n    for (final x in xs) { if (identical(foo, p)) { return; } }\n"
            "    foo = p;\n    notifyListeners();\n  }\n"
        )
        self.assertEqual(hook_violations("setFoo", {"app/lib/x.dart": looped}), [])
        closure = "  void setFoo(FooProvider p) {\n    run(() { return; });\n    notifyListeners();\n  }\n"
        self.assertEqual(len(hook_violations("setFoo", {"app/lib/x.dart": closure})), 1)

    def test_declaration_without_return_type_is_checked(self) -> None:
        text = "  setFoo(FooProvider p) {\n    foo = p;\n    notifyListeners();\n  }\n"
        self.assertEqual(len(hook_violations("setFoo", {"app/lib/x.dart": text})), 1)

    def test_calls_are_not_declarations(self) -> None:
        text = "  void other() {\n    device.setFoo(p);\n    setFoo(p);\n  }\n"
        problems = hook_violations("setFoo", {"app/lib/x.dart": text})
        self.assertEqual(len(problems), 1)
        self.assertIn("no declaration", problems[0])

    def test_a_hook_with_no_declaration_fails(self) -> None:
        problems = hook_violations("setMissing", {"app/lib/x.dart": SILENT})
        self.assertEqual(len(problems), 1)
        self.assertIn("no declaration", problems[0])

    def test_a_null_check_is_not_an_unchanged_guard(self) -> None:
        text = "  void setFoo(FooProvider? p) {\n    if (p == null) return;\n    foo = p;\n    notifyListeners();\n  }\n"
        self.assertEqual(len(hook_violations("setFoo", {"app/lib/x.dart": text})), 1)

    def test_an_unrelated_return_does_not_borrow_an_equality_check(self) -> None:
        text = (
            "  void setFoo(FooProvider p) {\n    if (foo == p) log('same');\n    if (disposed) return;\n"
            "    foo = p;\n    notifyListeners();\n  }\n"
        )
        self.assertEqual(len(hook_violations("setFoo", {"app/lib/x.dart": text})), 1)

    def test_compound_unchanged_guard_passes(self) -> None:
        text = (
            "  void setFoo(FooProvider p, BarProvider b) {\n"
            "    if (identical(foo, p) && identical(bar, b)) return;\n    foo = p;\n    notifyListeners();\n  }\n"
        )
        self.assertEqual(hook_violations("setFoo", {"app/lib/x.dart": text}), [])

    def test_a_guard_on_unrelated_state_fails(self) -> None:
        text = "  void setFoo(FooProvider p) {\n    if (disposed == true) return;\n    foo = p;\n    notifyListeners();\n  }\n"
        self.assertEqual(len(hook_violations("setFoo", {"app/lib/x.dart": text})), 1)

    def test_a_guard_on_a_local_derived_from_a_parameter_passes(self) -> None:
        self.assertEqual(hook_violations("updateExternalActions", {"app/lib/x.dart": BRACED_GUARD}), [])

    def test_comparing_the_parameter_with_something_else_fails(self) -> None:
        text = (
            "  void setFoo(FooProvider p) {\n    if (p == fallbackProvider) return;\n    foo = p;\n"
            "    notifyListeners();\n  }\n"
        )
        self.assertEqual(len(hook_violations("setFoo", {"app/lib/x.dart": text})), 1)

    def test_commented_out_update_calls_are_not_hooks(self) -> None:
        main_text = "// previous?.setFoo(a);\nfinal s = 'previous?.setBar(';\nupdate: (c, a, previous) => previous?..setBaz(a),"
        self.assertEqual(proxy_hooks(main_text), ["setBaz"])

    def test_a_graph_with_no_recognised_hooks_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app/lib").mkdir(parents=True)
            (root / "app/lib/main.dart").write_text("ChangeNotifierProvider(create: (_) => Foo()),")
            self.assertEqual(len(check_provider_graph(root)), 1)

    def test_graph_check_on_a_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app/lib/providers").mkdir(parents=True)
            (root / "app/lib/main.dart").write_text(MAIN)
            (root / "app/lib/providers/device.dart").write_text(GUARDED)
            (root / "app/lib/providers/message.dart").write_text(SILENT)
            (root / "app/lib/providers/capture.dart").write_text(BRACED_GUARD)
            self.assertEqual(check_provider_graph(root), [])
            (root / "app/lib/providers/capture.dart").write_text(UNGUARDED)
            self.assertEqual(len(check_provider_graph(root)), 1)


class CliTests(unittest.TestCase):
    def _repo(self, tmp: str) -> Path:
        root = Path(tmp)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
        (root / "app/lib/providers").mkdir(parents=True)
        (root / "app/lib/main.dart").write_text(MAIN)
        (root / "app/lib/providers/device.dart").write_text(GUARDED)
        (root / "app/lib/providers/message.dart").write_text(SILENT)
        (root / "app/lib/providers/capture.dart").write_text(BRACED_GUARD)
        (root / PROVIDER).write_text(VIOLATIONS["sync-file-io"] + "\n")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"], cwd=root, check=True
        )
        return root

    def test_ratchet_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            changed = root / "changed.txt"
            changed.write_text(PROVIDER + "\n")
            self.assertEqual(main(["--root", str(root), "--changed-files", str(changed), "--base", "HEAD"]), 0)
            (root / PROVIDER).write_text(VIOLATIONS["sync-file-io"] + "\nfile.existsSync();\n")
            self.assertEqual(main(["--root", str(root), "--changed-files", str(changed), "--base", "HEAD"]), 1)

    def test_graph_failure_fails_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._repo(tmp)
            (root / "app/lib/providers/capture.dart").write_text(UNGUARDED)
            changed = root / "changed.txt"
            changed.write_text("app/lib/providers/capture.dart\n")
            self.assertEqual(main(["--root", str(root), "--changed-files", str(changed), "--base", "HEAD"]), 1)
            self.assertEqual(main(["--root", str(root), "--graph"]), 1)

    def test_semantics_in_an_unchanged_file_fails_even_without_changed_dart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "app/lib/existing.dart"
            source.parent.mkdir(parents=True)
            source.write_text(VIOLATIONS["forced-semantics"])
            changed = root / "changed.txt"
            changed.write_text(".github/scripts/check_mobile_ui_isolate.py\n")
            self.assertEqual(len(check_semantics(root)), 1)
            self.assertEqual(main(["--root", str(root), "--changed-files", str(changed), "--base", "HEAD"]), 1)


if __name__ == "__main__":
    unittest.main()
