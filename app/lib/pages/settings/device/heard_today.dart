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
/// The running live episode has no segments yet; its runtime since local
/// midnight is today's speech while it runs, capped by the day's length.
///
/// When segment data is not available (list responses may omit it), the
/// conversation keeps its own length, filed by the finest time the server
/// reported — its start, as before.
int heardTodaySpeechSeconds({
  required Iterable<ServerConversation> conversations,
  required DateTime now,
  Duration? liveEpisodeElapsed,
}) {
  final windowStart = DateTime(now.year, now.month, now.day);
  final windowStartSeconds = windowStart.millisecondsSinceEpoch / 1000;
  final windowEndSeconds = now.millisecondsSinceEpoch / 1000;
  var total = 0.0;

  for (final conversation in conversations) {
    if (conversation.discarded) continue;
    final startedAt = conversation.startedAt;
    if (startedAt == null) continue;
    final startedSeconds = startedAt.millisecondsSinceEpoch / 1000;
    final segments = conversation.transcriptSegments;
    if (segments.isEmpty) {
      if (startedSeconds >= windowStartSeconds && startedSeconds <= windowEndSeconds) {
        total += conversation.getDurationInSeconds();
      }
      continue;
    }
    for (final segment in segments) {
      final segStart = startedSeconds + segment.start;
      final segEnd = startedSeconds + segment.end;
      if (segEnd <= windowStartSeconds || segStart >= windowEndSeconds) continue;
      total += min(segEnd, windowEndSeconds) - max(segStart, windowStartSeconds);
    }
  }

  if (liveEpisodeElapsed != null && liveEpisodeElapsed.inSeconds > 0) {
    total += min(liveEpisodeElapsed.inSeconds.toDouble(), windowEndSeconds - windowStartSeconds);
  }
  return total.round();
}
