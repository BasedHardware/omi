import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';

/// Final offsets are relative to the server conversation, never the Home
/// capture timer. Union coverage preserves holes when batches land out of order.
abstract final class LivePreviewCoverage {
  /// The transcript API has no processed-through signal. Hold a 10-second tail
  /// behind its latest final segment to allow a late batch to fill recent holes;
  /// older gaps are authoritative too, including silence omitted by final STT.
  static const settledTail = Duration(seconds: 10);

  /// Timing-less previews get one more bounded interval after the watermark
  /// passes their first observed time before they are discarded.
  static const untimedGrace = Duration(seconds: 10);

  static List<LivePreviewLine> uncovered(
      List<LivePreviewLine> lines, List<TranscriptSegment> finals, DateTime? origin) {
    if (origin == null) return List.of(lines);

    final originUs = origin.microsecondsSinceEpoch;
    final finalSpans = <_TimeSpan>[];
    for (final segment in finals) {
      if (segment.text.trim().isEmpty ||
          !segment.start.isFinite ||
          !segment.end.isFinite ||
          segment.end <= segment.start) {
        continue;
      }
      finalSpans.add((
        originUs + (segment.start * Duration.microsecondsPerSecond).round(),
        originUs + (segment.end * Duration.microsecondsPerSecond).round(),
      ));
    }

    // The normal transcript snapshot is time ordered. Preserve its O(n) path,
    // while still accepting snapshots whose batches arrived out of order.
    if (!_isSortedByStart(finalSpans)) {
      finalSpans.sort((a, b) => a.$1.compareTo(b.$1));
    }
    final merged = <_TimeSpan>[];
    for (final span in finalSpans) {
      if (merged.isEmpty || span.$1 > merged.last.$2) {
        merged.add(span);
      } else if (span.$2 > merged.last.$2) {
        merged[merged.length - 1] = (merged.last.$1, span.$2);
      }
    }

    // Segment ends do not prove that every earlier batch arrived. Moving this
    // watermark behind the latest end leaves a reorder window while letting
    // dropped words in older gaps settle without needing segment coverage.
    final watermarkUs = merged.isEmpty ? null : merged.last.$2 - settledTail.inMicroseconds;
    bool settledByEnd(DateTime? endAt) {
      final watermark = watermarkUs;
      final end = endAt?.microsecondsSinceEpoch;
      return watermark != null && end != null && end <= watermark;
    }

    bool untimedExpired(LivePreviewLine line) {
      final watermark = watermarkUs;
      final firstSeen = line.firstSeenAt?.microsecondsSinceEpoch;
      return watermark != null && firstSeen != null && watermark >= firstSeen + untimedGrace.inMicroseconds;
    }

    final wholeLineKeep = List<bool>.filled(lines.length, false);
    final spanKeep = List<List<bool>?>.filled(lines.length, null);
    final candidates = <_PreviewCandidate>[];

    for (var lineIndex = 0; lineIndex < lines.length; lineIndex++) {
      final line = lines[lineIndex];
      if (line.spans.isEmpty) {
        final start = line.startedAt?.microsecondsSinceEpoch;
        final end = line.endedAt?.microsecondsSinceEpoch;
        if (start != null && end != null && end > start) {
          candidates.add(_PreviewCandidate(lineIndex, null, start, end));
        } else {
          wholeLineKeep[lineIndex] = !settledByEnd(line.endedAt) && !untimedExpired(line);
        }
        continue;
      }

      final keep = List<bool>.filled(line.spans.length, false);
      spanKeep[lineIndex] = keep;
      for (var spanIndex = 0; spanIndex < line.spans.length; spanIndex++) {
        final span = line.spans[spanIndex];
        final start = span.startedAt.microsecondsSinceEpoch;
        final end = span.endedAt.microsecondsSinceEpoch;
        if (end > start) {
          candidates.add(_PreviewCandidate(lineIndex, spanIndex, start, end));
        } else {
          keep[spanIndex] = !settledByEnd(span.endedAt) && !untimedExpired(line);
        }
      }
    }

    // Preview results are normally ordered by audio time. If a platform emits
    // late results out of order, sort only that exceptional candidate list.
    if (!_areCandidatesSortedByStart(candidates)) {
      candidates.sort((a, b) {
        final startOrder = a.startUs.compareTo(b.startUs);
        if (startOrder != 0) return startOrder;
        final lineOrder = a.lineIndex.compareTo(b.lineIndex);
        return lineOrder != 0 ? lineOrder : (a.spanIndex ?? -1).compareTo(b.spanIndex ?? -1);
      });
    }

    // Merged final spans are disjoint, so a single forward cursor answers each
    // sorted preview interval in O(1) amortized time instead of rescanning all
    // finals for every line/word.
    var finalIndex = 0;
    for (final candidate in candidates) {
      if (watermarkUs != null && candidate.endUs <= watermarkUs) continue;
      while (finalIndex < merged.length && merged[finalIndex].$2 <= candidate.startUs) {
        finalIndex++;
      }
      final covered = finalIndex < merged.length &&
          merged[finalIndex].$1 <= candidate.startUs &&
          merged[finalIndex].$2 >= candidate.endUs;
      if (covered) continue;
      final spanIndex = candidate.spanIndex;
      if (spanIndex == null) {
        wholeLineKeep[candidate.lineIndex] = true;
      } else {
        spanKeep[candidate.lineIndex]![spanIndex] = true;
      }
    }

    final result = <LivePreviewLine>[];
    for (var lineIndex = 0; lineIndex < lines.length; lineIndex++) {
      final line = lines[lineIndex];
      if (line.spans.isEmpty) {
        if (wholeLineKeep[lineIndex]) result.add(line);
        continue;
      }

      final keep = spanKeep[lineIndex]!;
      final remaining = [
        for (var spanIndex = 0; spanIndex < keep.length; spanIndex++)
          if (keep[spanIndex]) line.spans[spanIndex].text,
      ];
      final text = remaining.join(' ').trim();
      if (text.isNotEmpty) {
        result.add(LivePreviewLine(
          id: line.id,
          isFinal: line.isFinal,
          text: text,
          startedAt: line.startedAt,
          endedAt: line.endedAt,
          firstSeenAt: line.firstSeenAt,
        ));
      }
    }
    return result;
  }

  static bool _isSortedByStart(Iterable<_TimeSpan> spans) {
    int? previousStart;
    for (final span in spans) {
      if (previousStart != null && span.$1 < previousStart) return false;
      previousStart = span.$1;
    }
    return true;
  }

  static bool _areCandidatesSortedByStart(List<_PreviewCandidate> candidates) {
    int? previousStart;
    for (final candidate in candidates) {
      if (previousStart != null && candidate.startUs < previousStart) return false;
      previousStart = candidate.startUs;
    }
    return true;
  }
}

typedef _TimeSpan = (int, int);

class _PreviewCandidate {
  const _PreviewCandidate(this.lineIndex, this.spanIndex, this.startUs, this.endUs);

  final int lineIndex;
  final int? spanIndex;
  final int startUs;
  final int endUs;
}
