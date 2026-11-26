import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/live_preview/live_words_merge.dart';
import 'package:omi/services/live_preview/speech_after_end.dart';

import '../../support/live_preview_fakes.dart';

// Reliability experiment vendor_recognizer_on_opened_app: the iOS engines time a result on one unbroken
// audio timeline from the first chunk fed. A pendant that sends nothing while it is quiet makes that
// timeline fall behind the capture clock by every gap. Under the experiment a result is moved back onto
// the capture clock before anything reads its times.

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final t0 = DateTime.utc(2026, 11, 25, 12);
  DateTime at(double seconds) => t0.add(Duration(milliseconds: (seconds * 1000).round()));
  late FakeLivePreviewEngine engine;
  late LivePreviewController preview;
  var clock = t0;
  var retime = true;

  /// [seconds] of phone-microphone audio in 100 ms chunks, the clock moving with it.
  Future<void> feed(double seconds) async {
    for (var i = 0; i < (seconds * 10).round(); i++) {
      clock = clock.add(const Duration(milliseconds: 100));
      preview.onPhonePcm(List.filled(3200, 1));
      await pumpEventQueue();
    }
  }

  setUp(() async {
    engine = FakeLivePreviewEngine();
    clock = t0;
    retime = true;
    preview = LivePreviewController(
      engine: engine,
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
      now: () => clock,
      ownResultsMuted: () => false,
      retimeOwnResults: () => retime,
    );
    preview.admit(language: 'en');
    await pumpEventQueue();
  });
  tearDown(() => preview.dispose());

  /// What the engine reports for audio [seconds] into what it was fed.
  void engineSays(String id, String text, double start, double end) {
    engine.emit(id, text, true, startedAt: at(start), endedAt: at(end));
  }

  test('audio fed without a gap keeps the engine\'s times', () async {
    await feed(3);
    engineSays('s1', 'hello there', 1.0, 2.5);
    await pumpEventQueue();
    expect(preview.lines.single.startedAt, at(1.0));
    expect(preview.lines.single.endedAt, at(2.5));
  });

  test('audio after a quiet gap is timed where it was captured, not where the engine counts it', () async {
    await feed(1); // captured 0..1 s
    clock = clock.add(const Duration(seconds: 60)); // the pendant sends nothing for a minute
    await feed(2); // captured 61..63 s; the engine counts it as 1..3 s
    engineSays('before', 'early words', 0.2, 0.8);
    engineSays('after', 'late words', 1.5, 2.5);
    await pumpEventQueue();
    final before = preview.lines.firstWhere((line) => line.id == 'before');
    final after = preview.lines.firstWhere((line) => line.id == 'after');
    expect(before.startedAt, at(0.2));
    expect(after.startedAt, at(61.5));
    expect(after.endedAt, at(62.5));
  });

  test('several gaps add up', () async {
    await feed(1);
    clock = clock.add(const Duration(seconds: 30));
    await feed(1);
    clock = clock.add(const Duration(seconds: 30));
    await feed(1);
    engineSays('s', 'third burst', 2.5, 2.9);
    await pumpEventQueue();
    expect(preview.lines.single.startedAt, at(62.5));
  });

  test('off: the engine\'s times are shown as they come, as before', () async {
    retime = false;
    await feed(1);
    clock = clock.add(const Duration(seconds: 60));
    await feed(2);
    engineSays('after', 'late words', 1.5, 2.5);
    await pumpEventQueue();
    expect(preview.lines.single.startedAt, at(1.5));
  });

  test('a restarted engine starts a new timeline', () async {
    await feed(1);
    clock = clock.add(const Duration(seconds: 60));
    preview.revoke();
    await pumpEventQueue();
    preview.admit(language: 'en');
    await pumpEventQueue();
    await feed(2); // The new run's first chunk is its origin: captured from 61 s.
    engine.emit('s', 'new run', true,
        startedAt: at(61.0).add(const Duration(milliseconds: 500)), endedAt: at(61.0).add(const Duration(seconds: 1)));
    await pumpEventQueue();
    expect(preview.lines.single.startedAt, at(61.5));
  });

  test('lines stay in spoken order: a phrase after a quiet gap goes last, never above earlier ones', () async {
    // What was seen on the phone before the fix: after a quiet gap the engine stamped a new phrase early,
    // so it landed above lines spoken before it, and the vendor's copy of it landed at the very end.
    await feed(2); // captured 0..2 s
    engineSays('first', 'first phrase', 0.5, 1.5);
    await pumpEventQueue();
    clock = clock.add(const Duration(seconds: 40));
    await feed(2); // captured 42..44 s; the engine counts 2..4 s
    clock = at(50);
    // The vendor heard something in between that the phone's recogniser has no line for.
    preview.onVendorLines([
      LivePreviewLine(
        id: 'v-mid',
        text: 'only the vendor',
        isFinal: true,
        startedAt: at(20),
        endedAt: at(21),
        firstSeenAt: at(26),
        spans: [LivePreviewSpan(text: 'only the vendor', startedAt: at(20), endedAt: at(21))],
      ),
    ]);
    engineSays('second', 'second phrase', 2.5, 3.5); // really 42.5..43.5 s
    await pumpEventQueue();
    preview.onVendorLines([
      LivePreviewLine(
        id: 'v-second',
        text: 'Second phrase.',
        isFinal: true,
        startedAt: at(42.6),
        endedAt: at(43.4),
        firstSeenAt: at(49),
        spans: [LivePreviewSpan(text: 'Second phrase.', startedAt: at(42.6), endedAt: at(43.4))],
      ),
    ]);
    expect(preview.lines.map((line) => line.id), ['first', 'v-mid', 'second']);
    final starts = [for (final line in preview.lines) line.startedAt!];
    expect(starts, [...starts]..sort());
    // A later phrase is appended, not inserted.
    engineSays('third', 'third phrase', 3.6, 3.9);
    await pumpEventQueue();
    expect(preview.lines.last.id, 'third');
  });

  test('with the times right, the vendor\'s words for the same audio are covered and the End rule holds', () async {
    await feed(1);
    clock = clock.add(const Duration(seconds: 60));
    await feed(3); // captured 61..64 s
    engineSays('own', 'said after the gap', 1.2, 3.8); // really 61.2..63.8 s
    await pumpEventQueue();
    final vendor = LivePreviewLine(
      id: 'v',
      text: 'said after the gap',
      isFinal: true,
      startedAt: at(61.3),
      endedAt: at(63.7),
      firstSeenAt: at(69),
      spans: [
        LivePreviewSpan(text: 'said', startedAt: at(61.3), endedAt: at(61.6)),
        LivePreviewSpan(text: 'after', startedAt: at(62.0), endedAt: at(62.4)),
        LivePreviewSpan(text: 'the', startedAt: at(62.8), endedAt: at(63.0)),
        LivePreviewSpan(text: 'gap', startedAt: at(63.3), endedAt: at(63.7)),
      ],
    );
    clock = at(69);
    preview.onVendorLines([vendor]);
    // No duplicate: the phone's own line covers the vendor's words.
    expect(preview.lines.map((line) => line.id), ['own']);
    expect(preview.vendorFilledWords, 0);
    expect(LiveWordsMerge.uncovered([vendor], LiveWordsMerge.coverage(preview.lines)), isEmpty);
    // An End at 30 s (inside the quiet gap): the words were spoken after it.
    expect(SpeechAfterEnd.heard(preview.lines, at(30)), isTrue);
  });
}
