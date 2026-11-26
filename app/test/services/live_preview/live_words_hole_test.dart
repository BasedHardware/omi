import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_words_hole.dart';

// Reliability experiment vendor_recognizer_on_opened_app, step 4: the hole on the Listening page is the
// audio between the end of the last stored line and the start of the first live line still shown.

final origin = DateTime.utc(2026, 11, 25, 12);
DateTime at(double seconds) => origin.add(Duration(milliseconds: (seconds * 1000).round()));

TranscriptSegment stored(String id, double start, double end) => TranscriptSegment(
    id: id,
    text: 'stored $id',
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: start,
    end: end,
    translations: []);

LivePreviewLine live(String id, double start, double end) => LivePreviewLine(
    id: id, text: 'live $id', isFinal: true, startedAt: at(start), endedAt: at(end), firstSeenAt: at(end));

void main() {
  test('stored text up to 60 s and live words from 75 s leave a 15 s hole', () {
    final result = LiveWordsHole.measure(
      stored: [stored('a', 0, 30), stored('b', 40, 60)],
      origin: origin,
      live: [live('covered', 41, 45), live('x', 75, 80), live('y', 82, 85)],
      now: at(90),
    );
    expect(result['stored_lines'], 2);
    expect(result['live_lines'], 3);
    expect(result['live_lines_shown'], 2); // The line the stored text covers is not shown.
    expect(result['stored_until_ago_ms'], 30000);
    expect(result['first_live_ago_ms'], 15000);
    expect(result['hole_ms'], 15000);
  });

  test('nothing stored yet, or nothing live: the parts that exist are still reported', () {
    final onlyLive = LiveWordsHole.measure(stored: const [], origin: origin, live: [live('x', 5, 8)], now: at(10));
    expect(onlyLive['hole_ms'], isNull);
    expect(onlyLive['first_live_ago_ms'], 5000);
    final onlyStored = LiveWordsHole.measure(stored: [stored('a', 0, 4)], origin: origin, live: const [], now: at(10));
    expect(onlyStored['hole_ms'], isNull);
    expect(onlyStored['stored_until_ago_ms'], 6000);
    expect(onlyStored['live_lines_shown'], 0);
  });

  test('a gap in the middle of the live lines is found even when an older live line overlaps the stored text', () {
    // Stored text to 60 s. Live lines from before a 45 s stay in the background (55..62 s), then from 107 s.
    final result = LiveWordsHole.measure(
      stored: [stored('a', 0, 60)],
      origin: origin,
      live: [live('old', 55, 62), live('new1', 107, 110), live('new2', 111, 113)],
      now: at(115),
    );
    expect(result['hole_ms'], -5000); // The first shown line starts before the stored text ends.
    expect(result['max_gap_ms'], 45000); // 62 s to 107 s: nothing on screen for it yet.
    final none = LiveWordsHole.measure(
        stored: [stored('a', 0, 60)], origin: origin, live: [live('x', 58, 64), live('y', 64.5, 70)], now: at(71));
    expect(none['max_gap_ms'], 500);
  });

  test('the record holds numbers only', () {
    final result =
        LiveWordsHole.measure(stored: [stored('a', 0, 4)], origin: origin, live: [live('x', 9, 12)], now: at(20));
    expect(result.values.every((value) => value == null || value is int), isTrue);
  });
}
