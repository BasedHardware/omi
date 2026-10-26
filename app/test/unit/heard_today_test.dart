import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/settings/device/heard_today.dart';

ServerConversation _conversation({
  required DateTime startedAt,
  List<TranscriptSegment> segments = const [],
  DateTime? finishedAt,
  bool discarded = false,
}) {
  final conversation = ServerConversation(
    id: 'c-${startedAt.millisecondsSinceEpoch}-${segments.length}',
    createdAt: startedAt,
    structured: Structured('', ''),
    startedAt: startedAt,
    finishedAt: finishedAt,
    transcriptSegments: segments,
  );
  conversation.discarded = discarded;
  return conversation;
}

TranscriptSegment _segment(double start, double end) => TranscriptSegment(
      id: 's-$start',
      text: 'hello',
      speaker: 'SPEAKER_00',
      isUser: true,
      personId: null,
      start: start,
      end: end,
      translations: const [],
    );

void main() {
  // 12:30 AM local: anything after local midnight is "today".
  final now = DateTime(2026, 10, 18, 0, 30);

  test('a conversation that crosses midnight contributes only its after-midnight speech', () {
    // Started 11:50 PM yesterday; segments 23:50–23:58 and 00:02–00:14 today.
    final conversation = _conversation(
      startedAt: DateTime(2026, 10, 17, 23, 50),
      segments: [
        _segment(0, 8 * 60), // before midnight: 8 min
        _segment(12 * 60, 24 * 60), // after midnight: 12 min
      ],
    );

    expect(
      heardTodaySpeechSeconds(conversations: [conversation], now: now),
      12 * 60,
    );
  });

  test('a conversation misfiled on an earlier session day still counts by its segment times', () {
    // The pendant streamed since Oct 15 without a break: startedAt is the
    // session origin, and the segments run on the session clock. Speech whose
    // absolute time lands today counts, wherever the list buckets the row.
    final sessionStart = DateTime(2026, 10, 15, 9);
    final secondsSinceSessionStart = now.difference(sessionStart).inSeconds;
    final conversation = _conversation(
      startedAt: sessionStart,
      segments: [
        _segment(0, 60),
        _segment(secondsSinceSessionStart - 120, secondsSinceSessionStart - 60),
      ],
    );

    expect(
      heardTodaySpeechSeconds(conversations: [conversation], now: now),
      60,
      reason: 'only the segment inside today counts, not the session-long span',
    );
  });

  test('the live episode counts since local midnight, including a start before it', () {
    // now is 00:30: an episode running 33 minutes began before midnight, so
    // only its 30 minutes after midnight are today's.
    expect(
      heardTodaySpeechSeconds(conversations: const [], now: now, liveEpisodeElapsed: const Duration(minutes: 33)),
      30 * 60,
    );
    // A 33-hour episode that began two days ago: the same 30 minutes after
    // midnight are today's.
    expect(
      heardTodaySpeechSeconds(
        conversations: const [],
        now: now,
        liveEpisodeElapsed: const Duration(minutes: 33 * 60),
      ),
      30 * 60,
    );
    // Started after midnight: the whole elapsed time is today's.
    final midday = DateTime(2026, 10, 18, 12);
    expect(
      heardTodaySpeechSeconds(
        conversations: const [],
        now: midday,
        liveEpisodeElapsed: const Duration(minutes: 33),
      ),
      33 * 60,
    );
  });

  test('without segment data, a conversation started today still counts its length', () {
    final conversation = _conversation(
      startedAt: DateTime(2026, 10, 18, 0, 5),
      finishedAt: DateTime(2026, 10, 18, 0, 20),
    );

    expect(
      heardTodaySpeechSeconds(conversations: [conversation], now: now),
      15 * 60,
      reason: 'no segments: finishedAt - startedAt is the length, as before',
    );
    // Yesterday's conversation stays yesterday's.
    final yesterday = _conversation(
      startedAt: DateTime(2026, 10, 17, 10),
      finishedAt: DateTime(2026, 10, 17, 11),
    );
    expect(heardTodaySpeechSeconds(conversations: [yesterday], now: now), 0);
  });

  test('discarded conversations never count', () {
    final conversation = _conversation(
      startedAt: DateTime(2026, 10, 18, 0, 5),
      segments: [_segment(0, 600)],
      discarded: true,
    );

    expect(heardTodaySpeechSeconds(conversations: [conversation], now: now), 0);
  });
}
