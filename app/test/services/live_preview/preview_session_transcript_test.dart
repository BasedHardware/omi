import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversation_detail/widgets/quick_summary_card.dart';
import 'package:omi/services/experiments/quick_summary_gate.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';

import '../../support/live_preview_fakes.dart';

void main() {
  late FakeLivePreviewEngine engine;
  late LivePreviewController preview;
  final start = DateTime.utc(2026, 11, 17, 20);

  setUp(() {
    QuickSummaryGate.debugOverride = true;
    engine = FakeLivePreviewEngine();
    preview = LivePreviewController(
      engine: engine,
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
      now: () => start,
      maxLines: 3,
    );
    engine.nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
  });
  tearDown(() {
    preview.dispose();
    QuickSummaryGate.debugOverride = null;
  });

  test('the session transcript keeps every line past the display cap, in order', () async {
    preview.admit(language: 'en');
    await pumpEventQueue();
    for (var i = 0; i < 6; i++) {
      engine.emit('s$i', 'line $i', true);
    }
    await pumpEventQueue();
    expect(preview.lines.map((l) => l.text), ['line 3', 'line 4', 'line 5'], reason: 'display keeps the newest 3');
    expect(preview.sessionLines.map((l) => l.text), [for (var i = 0; i < 6; i++) 'line $i']);
  });

  test('with Quick Summary off nothing beyond the display lines is kept', () async {
    QuickSummaryGate.debugOverride = false;
    preview.admit(language: 'en');
    await pumpEventQueue();
    engine.emit('s1', 'line 1', true);
    await pumpEventQueue();
    expect(preview.lines, hasLength(1));
    expect(preview.sessionLines, isEmpty);
  });

  test('volatile updates replace in place; a withdrawn hypothesis leaves the session', () async {
    preview.admit(language: 'en');
    await pumpEventQueue();
    engine.emit('s1', 'hel', false);
    engine.emit('s1', 'Hello there.', true);
    engine.emit('s2', 'um', false);
    engine.emit('s2', '', false);
    await pumpEventQueue();
    expect(preview.sessionLines.map((l) => (l.text, l.isFinal)), [('Hello there.', true)]);
  });

  test('capture end clears the session transcript with the display', () async {
    preview.admit(language: 'en');
    await pumpEventQueue();
    engine.emit('s1', 'Remember the banner.', true);
    await pumpEventQueue();
    expect(preview.sessionLines, hasLength(1));
    preview.endCapture();
    expect(preview.sessionLines, isEmpty);
  });

  test('preview lines become transcript segments timed from the first line', () {
    final lines = [
      LivePreviewLine(
          id: 'a',
          text: ' Move the launch to Thursday. ',
          isFinal: true,
          startedAt: start.add(const Duration(seconds: 2)),
          endedAt: start.add(const Duration(seconds: 5))),
      const LivePreviewLine(id: 'b', text: '   ', isFinal: true),
      LivePreviewLine(
          id: 'c',
          text: 'Call the photographer.',
          isFinal: false,
          startedAt: start.add(const Duration(seconds: 6)),
          endedAt: start.add(const Duration(milliseconds: 8500))),
    ];
    final segments = transcriptFromPreview(lines);
    expect(segments.map((s) => s.text), ['Move the launch to Thursday.', 'Call the photographer.']);
    expect(segments.map((s) => (s.start, s.end)), [(0.0, 3.0), (4.0, 6.5)]);
    expect(segments.first.id, 'preview-a');
  });
}
