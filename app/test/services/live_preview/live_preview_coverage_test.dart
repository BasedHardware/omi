import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_coverage.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import '../../support/live_preview_fakes.dart';

final origin = DateTime.utc(2026, 10, 27, 8, 11, 57);
DateTime at(int s) => origin.add(Duration(seconds: s));
TranscriptSegment finalAt(double start, double end, {String text = 'different final wording'}) => TranscriptSegment(
    id: '$start',
    text: text,
    speaker: 'SPEAKER_0',
    isUser: false,
    personId: null,
    start: start,
    end: end,
    translations: []);
LivePreviewLine line(String id, int start, int end, {String text = 'same words'}) =>
    LivePreviewLine(id: id, text: text, isFinal: true, startedAt: at(start), endedAt: at(end), firstSeenAt: at(start));

void main() {
  test('coverage uses audio time, preserving repeated words at a different time', () {
    final lines = [line('earlier', 0, 4), line('repeat', 8, 12)];
    expect(LivePreviewCoverage.uncovered(lines, [finalAt(0, 4)], origin).map((l) => l.id), ['repeat']);
  });

  test('out of order finals cannot cover a missing middle batch', () {
    final lines = [line('a', 0, 4), line('b', 4, 8), line('c', 8, 12)];
    expect(LivePreviewCoverage.uncovered(lines, [finalAt(8, 12), finalAt(0, 4)], origin).map((l) => l.id), ['b']);
    expect(LivePreviewCoverage.uncovered(lines, [finalAt(8, 12), finalAt(0, 4), finalAt(4, 8)], origin), isEmpty);
  });

  test('dropped preview text in an older final gap settles after the watermark passes', () {
    final noise = line('noise', 5, 6, text: 'AM');
    final finals = [finalAt(0, 2), finalAt(14, 18)];

    expect(LivePreviewCoverage.uncovered([noise], finals, origin), isEmpty,
        reason: 'the latest final end minus the 10-second reorder tail passes the silent gap');
  });

  test('uncovered speech ahead of the settled watermark remains responsive', () {
    final speechAhead = line('ahead', 19, 21, text: 'still speaking');

    expect(LivePreviewCoverage.uncovered([speechAhead], [finalAt(0, 2), finalAt(14, 20)], origin), [speechAhead]);
  });

  test('settled watermark trims only the older timed words in a preview line', () {
    final mixed = LivePreviewLine(
        id: 'mixed',
        text: 'AM still speaking',
        isFinal: false,
        startedAt: at(5),
        endedAt: at(21),
        spans: [
          LivePreviewSpan(text: 'AM', startedAt: at(5), endedAt: at(6)),
          LivePreviewSpan(text: 'still speaking', startedAt: at(19), endedAt: at(21)),
        ]);

    expect(
        LivePreviewCoverage.uncovered([mixed], [finalAt(0, 2), finalAt(14, 20)], origin).single.text, 'still speaking');
  });

  test('a recent out of order batch hole stays visible until the reorder tail passes', () {
    final hole = line('hole', 8, 10, text: 'late batch');

    expect(LivePreviewCoverage.uncovered([hole], [finalAt(12, 16), finalAt(0, 4)], origin), [hole]);
  });

  test('out of order preview results retain coverage after sorting the cursor input', () {
    final later = line('later', 17, 19, text: 'newer speech');
    final earlier = line('earlier', 10, 11, text: 'already final');

    expect(LivePreviewCoverage.uncovered([later, earlier], [finalAt(9, 14), finalAt(20, 22)], origin), [later]);
  });

  test('adjacent and overlapping spans form a union, holes and invalid spans do not', () {
    final lines = [line('a', 0, 12)];
    expect(LivePreviewCoverage.uncovered(lines, [finalAt(6, 12), finalAt(0, 7)], origin), isEmpty);
    expect(LivePreviewCoverage.uncovered(lines, [finalAt(0, 5), finalAt(6, 12)], origin), hasLength(1));
    expect(LivePreviewCoverage.uncovered(lines, [finalAt(double.nan, 12), finalAt(12, 0)], origin), hasLength(1));
    expect(LivePreviewCoverage.uncovered(lines, [finalAt(0, 12, text: ' ')], origin), hasLength(1));
  });

  test('a partial final replaces only timed words, preserving the remaining suffix', () {
    final words =
        LivePreviewLine(id: 'a', text: 'first next last', isFinal: false, startedAt: at(0), endedAt: at(6), spans: [
      LivePreviewSpan(text: 'first', startedAt: at(0), endedAt: at(2)),
      LivePreviewSpan(text: 'next', startedAt: at(2), endedAt: at(4)),
      LivePreviewSpan(text: 'last', startedAt: at(4), endedAt: at(6)),
    ]);
    expect(LivePreviewCoverage.uncovered([words], [finalAt(0, 2)], origin).single.text, 'next last');
    expect(LivePreviewCoverage.uncovered([words], [finalAt(4, 6), finalAt(0, 2)], origin).single.text, 'next');
    expect(LivePreviewCoverage.uncovered([words], [finalAt(0, 6)], origin), isEmpty);
  });

  test('unknown timing and missing origin preserve preview instead of guessing', () {
    final unknown = LivePreviewLine(id: 'a', text: 'same words', isFinal: false, firstSeenAt: at(0));
    expect(LivePreviewCoverage.uncovered([unknown], [finalAt(0, 19)], origin), [unknown]);
    final lines = [line('a', 0, 2)];
    expect(LivePreviewCoverage.uncovered(lines, [finalAt(0, 20)], null), lines);
  });

  test('unknown-timing lines expire after the watermark passes their bounded grace', () {
    final unknown = LivePreviewLine(id: 'a', text: 'older untimed words', isFinal: true, firstSeenAt: at(0));

    expect(LivePreviewCoverage.uncovered([unknown], [finalAt(0, 19)], origin), [unknown]);
    expect(LivePreviewCoverage.uncovered([unknown], [finalAt(0, 20)], origin), isEmpty);
  });

  test('controller preserves the first observed time across untimed hypotheses', () async {
    var clock = origin;
    final engine = FakeLivePreviewEngine();
    final preview = LivePreviewController(
      engine: engine,
      now: () => clock,
      telemetry: LivePreviewTelemetry(emit: (_) {}),
      platform: LivePreviewPlatform.ios,
      osMajor: 26,
    );
    addTearDown(preview.dispose);
    preview.admit(language: 'en');
    await Future<void>.delayed(Duration.zero);

    engine.emit('untimed', 'first words', false);
    clock = at(3);
    engine.emit('untimed', 'revised words', true);

    expect(preview.lines.single.firstSeenAt, at(0));
    expect(LivePreviewCoverage.uncovered(preview.lines, [finalAt(0, 22)], origin), isEmpty);
  });

  test('native channel carries audio timestamps and timed words', () {
    final result = LivePreviewResult.fromWire({
      'segmentId': 's',
      'text': 'first',
      'isFinal': true,
      'startMs': at(0).millisecondsSinceEpoch,
      'endMs': at(2).millisecondsSinceEpoch,
      'spans': [
        {'text': 'first', 'startMs': at(0).millisecondsSinceEpoch, 'endMs': at(2).millisecondsSinceEpoch}
      ],
    })!;
    expect(result.startedAt, at(0));
    expect(result.endedAt, at(2));
    expect(result.spans.single.text, 'first');
    expect(result.spans.single.endedAt, at(2));
  });

  test('silence clear and account change remove old timeline coverage state', () async {
    var clock = origin;
    final engine = FakeLivePreviewEngine();
    final preview = LivePreviewController(
        engine: engine,
        now: () => clock,
        telemetry: LivePreviewTelemetry(emit: (_) {}),
        platform: LivePreviewPlatform.ios,
        osMajor: 26);
    addTearDown(preview.dispose);
    preview.admit(language: 'en');
    await Future<void>.delayed(Duration.zero);
    engine.emit('old', 'earlier', true, startedAt: at(0), endedAt: at(2));
    clock = at(180);
    engine.emit('new', 'later', true, startedAt: at(178), endedAt: at(180));
    expect(preview.lines.map((l) => l.id), ['new']);
    expect(LivePreviewCoverage.uncovered(preview.lines, [finalAt(0, 2)], origin).single.text, 'later');
    preview.endCapture();
    expect(preview.lines, isEmpty);
    preview.admit(language: 'en');
    await Future<void>.delayed(Duration.zero);
    engine.emit('old', 'new account', true, startedAt: at(200), endedAt: at(204));
    expect(LivePreviewCoverage.uncovered(preview.lines, [finalAt(0, 2)], origin).single.text, 'new account');
  });
}
