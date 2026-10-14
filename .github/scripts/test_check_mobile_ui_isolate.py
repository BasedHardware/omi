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

from check_mobile_ui_isolate import (
    RULE_IDS,
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

# One violating snippet per rule, each the shape of a defect found in the 2026-10 lag audit.
VIOLATIONS: dict[str, str] = {
    "sync-file-io": "for (final entity in dir.listSync().whereType<File>()) {",
    "json-in-provider": "SharedPreferencesUtil().cache = jsonEncode(conversations);",
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

    def test_each_rule_fires_on_its_defect(self) -> None:
        for rule_id, snippet in VIOLATIONS.items():
            with self.subTest(rule=rule_id):
                counts = count_hits(snippet, PROVIDER)
                self.assertEqual(counts[rule_id], EXPECTED_COUNT.get(rule_id, 1), counts)

    def test_allow_comment_on_the_line_suppresses_the_hit(self) -> None:
        for rule_id, snippet in VIOLATIONS.items():
            with self.subTest(rule=rule_id):
                allowed = f"{snippet} // omi-perf-allow: {rule_id} -- measured, bounded input"
                self.assertEqual(count_hits(allowed, PROVIDER)[rule_id], 0)

    def test_allow_comment_on_the_line_above_suppresses_the_hit(self) -> None:
        for rule_id, snippet in VIOLATIONS.items():
            with self.subTest(rule=rule_id):
                allowed = f"  // omi-perf-allow: {rule_id} -- measured, bounded input\n{snippet}"
                self.assertEqual(count_hits(allowed, PROVIDER)[rule_id], 0)

    def test_allow_comment_without_reason_is_ignored(self) -> None:
        snippet = VIOLATIONS["sync-file-io"] + " // omi-perf-allow: sync-file-io"
        self.assertEqual(count_hits(snippet, PROVIDER)["sync-file-io"], 1)

    def test_allow_for_another_rule_does_not_suppress(self) -> None:
        snippet = VIOLATIONS["sync-file-io"] + " // omi-perf-allow: blur-filter -- unrelated"
        self.assertEqual(count_hits(snippet, PROVIDER)["sync-file-io"], 1)

    def test_comments_and_strings_do_not_count(self) -> None:
        self.assertEqual(count_hits("// dir.listSync() used to block here", PROVIDER)["sync-file-io"], 0)
        self.assertEqual(count_hits("final s = 'file.existsSync()';", PROVIDER)["sync-file-io"], 0)

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

    def test_slow_periodic_timer_is_clean(self) -> None:
        snippet = "Timer.periodic(const Duration(milliseconds: 500), (_) => tick());"
        self.assertEqual(count_hits(snippet, PROVIDER)["fast-periodic-timer"], 0)
        self.assertEqual(count_hits("Timer.periodic(const Duration(seconds: 1), tick);", PROVIDER)["fast-periodic-timer"], 0)

    def test_sized_network_image_is_clean(self) -> None:
        sized = "CachedNetworkImage(imageUrl: url, memCacheWidth: (15 * dpr).round(), width: 15)"
        self.assertEqual(count_hits(sized, PROVIDER)["unsized-network-image"], 0)
        resized = "Image(image: ResizeImage(NetworkImage(url), width: 120))"
        self.assertEqual(count_hits(resized, PROVIDER)["unsized-network-image"], 1, "the inner NetworkImage call")
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


if __name__ == "__main__":
    unittest.main()
