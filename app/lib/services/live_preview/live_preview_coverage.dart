import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';

/// Final offsets are relative to the server conversation, never the Home
/// capture timer. Union coverage preserves holes when batches land out of order.
abstract final class LivePreviewCoverage {
  static List<LivePreviewLine> uncovered(
      List<LivePreviewLine> lines, List<TranscriptSegment> finals, DateTime? origin) {
    if (origin == null) return List.of(lines);
    final spans = [
      for (final segment in finals)
        if (segment.text.trim().isNotEmpty &&
            segment.start.isFinite &&
            segment.end.isFinite &&
            segment.end > segment.start)
          (
            origin.microsecondsSinceEpoch + (segment.start * 1000000).round(),
            origin.microsecondsSinceEpoch + (segment.end * 1000000).round()
          ),
    ]..sort((a, b) => a.$1.compareTo(b.$1));
    bool covered(DateTime? startAt, DateTime? endAt) {
      final start = startAt?.microsecondsSinceEpoch;
      final end = endAt?.microsecondsSinceEpoch;
      if (start == null || end == null || end <= start) return false;
      var cursor = start;
      for (final span in spans) {
        if (span.$2 <= cursor) continue;
        if (span.$1 > cursor) return false;
        cursor = span.$2;
        if (cursor >= end) return true;
      }
      return false;
    }

    return [
      for (final line in lines)
        if (!covered(line.startedAt, line.endedAt))
          // Timed words let a batch replace just the prefix without repeating
          // that prefix or dropping the rest. Unknown timing always stays.
          if (line.spans.isEmpty)
            line
          else if (line.spans.any((span) => !covered(span.startedAt, span.endedAt)))
            LivePreviewLine(
                id: line.id,
                isFinal: line.isFinal,
                text: line.spans
                    .where((span) => !covered(span.startedAt, span.endedAt))
                    .map((span) => span.text)
                    .join(' ')
                    .trim(),
                startedAt: line.startedAt,
                endedAt: line.endedAt),
    ];
  }
}
