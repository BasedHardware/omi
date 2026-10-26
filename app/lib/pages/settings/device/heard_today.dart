import 'dart:math';

import 'package:omi/backend/schema/conversation.dart';

/// How much Omi heard today, in seconds of speech.
///
/// `startedAt` is the streaming session's origin, not this conversation's
/// start, so a pendant that streams without a break files today's
/// conversations under an earlier day and a per-day duration sum reads 0s
/// while a live episode runs. Speech is measured on the transcript clock
/// instead: each segment maps to absolute time on the session clock
/// (`startedAt` + its offset), and only the part inside today's local day
/// counts — a conversation that crosses midnight contributes its after-midnight
/// half to today.
///
/// The active live episode contributes its own interval since its start or
/// anchor ([liveEpisodeStart] — never the capture session's origin, which a
/// pendant that streams all day never resets). Because every contribution is
/// an interval on one clock, all intervals are clipped to today and merged
/// before summing: audio the episode's own transcript segments already
/// counted is not counted again from the running interval.
///
/// When segment data is not available (list responses may omit it), the
/// conversation keeps its own length, filed by the finest time the server
/// reported — its start, as before.
int heardTodaySpeechSeconds({
  required Iterable<ServerConversation> conversations,
  required DateTime now,
  DateTime? liveEpisodeStart,
}) {
  final windowStart = DateTime(now.year, now.month, now.day);
  final windowStartSeconds = windowStart.millisecondsSinceEpoch / 1000;
  final windowEndSeconds = now.millisecondsSinceEpoch / 1000;

  final intervals = <(double, double)>[];
  for (final conversation in conversations) {
    if (conversation.discarded) continue;
    final startedAt = conversation.startedAt;
    if (startedAt == null) continue;
    final startedSeconds = startedAt.millisecondsSinceEpoch / 1000;
    final segments = conversation.transcriptSegments;
    if (segments.isEmpty) {
      if (startedSeconds >= windowStartSeconds && startedSeconds <= windowEndSeconds) {
        intervals.add((startedSeconds, startedSeconds + conversation.getDurationInSeconds()));
      }
      continue;
    }
    for (final segment in segments) {
      final segStart = startedSeconds + segment.start;
      final segEnd = startedSeconds + segment.end;
      if (segEnd <= windowStartSeconds || segStart >= windowEndSeconds) continue;
      intervals.add((segStart, segEnd));
    }
  }
  if (liveEpisodeStart != null) {
    final start = liveEpisodeStart.millisecondsSinceEpoch / 1000;
    if (windowEndSeconds > start) intervals.add((start, windowEndSeconds));
  }

  return _mergedSeconds(intervals, windowStartSeconds, windowEndSeconds);
}

/// The union of [intervals] clipped to [windowStartSeconds, windowEndSeconds]:
/// overlapping speech is counted once, never once per row that names it.
int _mergedSeconds(List<(double, double)> intervals, double windowStartSeconds, double windowEndSeconds) {
  if (intervals.isEmpty) return 0;
  final clipped = [
    for (final (start, end) in intervals)
      if (end > windowStartSeconds && start < windowEndSeconds)
        (max(start, windowStartSeconds), min(end, windowEndSeconds)),
  ]..sort((a, b) => a.$1.compareTo(b.$1));
  var total = 0.0;
  var mergeStart = clipped.first.$1;
  var mergeEnd = clipped.first.$2;
  for (final (start, end) in clipped.skip(1)) {
    if (start > mergeEnd) {
      total += mergeEnd - mergeStart;
      mergeStart = start;
    }
    if (end > mergeEnd) mergeEnd = end;
  }
  total += mergeEnd - mergeStart;
  return total.round();
}
