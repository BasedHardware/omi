import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';

/// Final offsets are relative to the server conversation, never the Home
/// capture timer. Union coverage preserves holes when batches land out of order.
final class LivePreviewCoverage {
  /// Prepare final intervals once for a transcript snapshot. Preview revisions
  /// can reuse them without walking and sorting the final history again.
  LivePreviewCoverage.forFinals(List<TranscriptSegment> finals, DateTime? origin)
      : _hasOrigin = origin != null,
        _spans = _finalSpans(finals, origin);

  static List<(int, int)> _finalSpans(List<TranscriptSegment> finals, DateTime? origin) {
    if (origin == null) return [];
    final sorted = [
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
    final merged = <(int, int)>[];
    for (final span in sorted) {
      if (merged.isEmpty || span.$1 > merged.last.$2) {
        merged.add(span);
      } else if (span.$2 > merged.last.$2) {
        merged[merged.length - 1] = (merged.last.$1, span.$2);
      }
    }
    return merged;
  }

  final bool _hasOrigin;
  final List<(int, int)> _spans;

  static List<LivePreviewLine> uncovered(
          List<LivePreviewLine> lines, List<TranscriptSegment> finals, DateTime? origin) =>
      LivePreviewCoverage.forFinals(finals, origin).excludeCovered(lines);

  List<LivePreviewLine> excludeCovered(List<LivePreviewLine> lines) {
    if (!_hasOrigin) return List.of(lines);
    bool covered(DateTime? startAt, DateTime? endAt) {
      final start = startAt?.microsecondsSinceEpoch;
      final end = endAt?.microsecondsSinceEpoch;
      if (start == null || end == null || end <= start) return false;
      // Intervals are disjoint after preparation. Find the last one starting
      // at/before this line, without scanning the final history on preview ticks.
      var low = 0;
      var high = _spans.length;
      while (low < high) {
        final middle = (low + high) ~/ 2;
        if (_spans[middle].$1 <= start) {
          low = middle + 1;
        } else {
          high = middle;
        }
      }
      return low > 0 && _spans[low - 1].$2 >= end;
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
