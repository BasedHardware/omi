import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_coverage.dart';

/// Reliability experiment `vendor_recognizer_on_opened_app`, step 4: what the Listening page holds at
/// one moment, as numbers. The page shows the stored transcript first and the live words under it; the
/// hole is the audio between the end of the last stored line and the start of the first live line
/// still shown. Local measure only, never any text.
final class LiveWordsHole {
  LiveWordsHole._();

  static Map<String, Object?> measure({
    required List<TranscriptSegment> stored,
    required DateTime? origin,
    required List<LivePreviewLine> live,
    required DateTime now,
  }) {
    DateTime? storedUntil;
    if (origin != null) {
      for (final segment in stored) {
        if (segment.text.trim().isEmpty || !segment.end.isFinite) continue;
        final end = origin.add(Duration(microseconds: (segment.end * Duration.microsecondsPerSecond).round()));
        if (storedUntil == null || end.isAfter(storedUntil)) storedUntil = end;
      }
    }
    final shown = LivePreviewCoverage.forFinals(stored, origin).excludeCovered(live);
    DateTime? firstLive;
    for (final line in shown) {
      final start = line.startedAt ?? line.firstSeenAt;
      if (start != null && (firstLive == null || start.isBefore(firstLive))) firstLive = start;
    }
    // The longest stretch after the stored text, and before the newest live line, that no shown live
    // line covers: what a reader sees as missing after reopening the app in the middle of speech.
    int? maxGapMs;
    if (storedUntil != null && shown.isNotEmpty) {
      final spans = [
        for (final line in shown)
          if ((line.startedAt ?? line.firstSeenAt) case final start?) (start, line.endedAt ?? start),
      ]..sort((a, b) => a.$1.compareTo(b.$1));
      var cursor = storedUntil;
      var longest = Duration.zero;
      for (final (start, end) in spans) {
        if (!end.isAfter(cursor)) continue;
        if (start.isAfter(cursor) && start.difference(cursor) > longest) longest = start.difference(cursor);
        cursor = end;
      }
      maxGapMs = longest.inMilliseconds;
    }
    return {
      'max_gap_ms': maxGapMs,
      'stored_lines': stored.length,
      'live_lines': live.length,
      'live_lines_shown': shown.length,
      'stored_until_ago_ms': storedUntil == null ? null : now.difference(storedUntil).inMilliseconds,
      'first_live_ago_ms': firstLive == null ? null : now.difference(firstLive).inMilliseconds,
      // Positive: audio after the last stored line that no live line covers yet.
      'hole_ms': storedUntil == null || firstLive == null ? null : firstLive.difference(storedUntil).inMilliseconds,
    };
  }
}
