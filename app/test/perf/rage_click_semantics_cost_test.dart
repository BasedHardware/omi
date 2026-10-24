import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/rage_click_context_tracker.dart';

// INV-PERF-1: the iOS rage-click tracker used to hold a SemanticsHandle for the
// app's lifetime, so every production iOS frame compiled the semantics tree.
// The guard: mounting the tracker leaves semantics off. The second test prints
// what a held handle costs a scrolling, row-heavy list (informational: host
// timings are noisy, but semantics' share of the same frames is stable).
Widget _row(int i) => Material(
      child: InkWell(
        onTap: () {},
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(children: [
            const Icon(Icons.chat_bubble_outline),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Conversation title number $i about something', maxLines: 1),
                Text('Overview text for row $i that wraps onto a second line in most layouts', maxLines: 2),
                Row(children: [
                  Text('10:${i % 60}'),
                  const SizedBox(width: 8),
                  TextButton(onPressed: () {}, child: Text('tag $i')),
                ]),
              ]),
            ),
            IconButton(onPressed: () {}, icon: const Icon(Icons.more_horiz)),
          ]),
        ),
      ),
    );

Future<Map<String, double>> _fling(WidgetTester tester, {required bool semantics}) async {
  final handle = semantics ? tester.ensureSemantics() : null;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      appBar: AppBar(title: const Text('Home')),
      body: ListView.builder(itemCount: 400, itemBuilder: (_, i) => _row(i)),
    ),
  ));
  await tester.pump();
  FlutterTimeline.debugReset();
  for (var round = 0; round < 3; round++) {
    for (var i = 0; i < 40; i++) {
      await tester.drag(find.byType(ListView), const Offset(0, -60));
      await tester.pump(const Duration(milliseconds: 16));
    }
    for (var i = 0; i < 40; i++) {
      await tester.drag(find.byType(ListView), const Offset(0, 60));
      await tester.pump(const Duration(milliseconds: 16));
    }
  }
  final timings = FlutterTimeline.debugCollect();
  handle?.dispose();
  final out = <String, double>{};
  for (final block in timings.aggregatedBlocks) {
    out[block.name] = block.duration / 1000.0;
  }
  return out;
}

void main() {
  testWidgets('the rage-click tracker does not turn semantics on', (tester) async {
    String? captured;
    await tester.pumpWidget(RageClickContextTracker(
      onContext: ({screenName, required target}) => captured = target,
      child: MaterialApp(home: Scaffold(body: ListView.builder(itemCount: 50, itemBuilder: (_, i) => _row(i)))),
    ));
    expect(tester.binding.semanticsEnabled, isFalse);
    await tester.tap(find.text('tag 3'));
    await tester.pump();
    expect(captured, 'tag 3');
    expect(tester.binding.semanticsEnabled, isFalse);
  }, semanticsEnabled: false);

  testWidgets('semantics share of frame work while scrolling', (tester) async {
    FlutterTimeline.debugCollectionEnabled = true;
    final off = <Map<String, double>>[];
    final on = <Map<String, double>>[];
    for (var rep = 0; rep < 3; rep++) {
      off.add(await _fling(tester, semantics: false));
      on.add(await _fling(tester, semantics: true));
    }
    FlutterTimeline.debugCollectionEnabled = false;
    double sum(Map<String, double> m, List<String> keys) => keys.fold(0, (a, k) => a + (m[k] ?? 0));
    const pipeline = ['BUILD', 'LAYOUT', 'PAINT', 'COMPOSITING', 'SEMANTICS'];
    for (var rep = 0; rep < 3; rep++) {
      final a = off[rep], b = on[rep];
      expect(a['SEMANTICS'] ?? 0, 0, reason: 'the OFF arm must not compile semantics');
      debugPrint('rep $rep OFF pipeline=${sum(a, pipeline).toStringAsFixed(1)}ms '
          'ON pipeline=${sum(b, pipeline).toStringAsFixed(1)}ms '
          'semantics=${(b['SEMANTICS'] ?? 0).toStringAsFixed(1)}ms '
          'layout off/on=${(a['LAYOUT'] ?? 0).toStringAsFixed(1)}/${(b['LAYOUT'] ?? 0).toStringAsFixed(1)} '
          'share=${(100 * (b['SEMANTICS'] ?? 0) / sum(b, pipeline)).toStringAsFixed(1)}%');
    }
  }, semanticsEnabled: false);
}
