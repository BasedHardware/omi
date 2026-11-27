import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';

/// Final offsets are relative to the server conversation, never the Home
/// capture timer. Union coverage preserves holes when batches land out of order.
final class LivePreviewCoverage {
  /// The transcript API has no processed-through signal. Hold a 10-second tail
  /// behind its latest final segment to allow a late batch to fill recent holes;
  /// older gaps are authoritative too, including silence omitted by final STT.
  static const settledTail = Duration(seconds: 10);

  /// Timing-less previews get one more bounded interval after the watermark
  /// passes their first observed time before they are discarded.
  static const untimedGrace = Duration(seconds: 10);

  /// Reliability experiment `live_words_cascade`: a live word counts as stored when its middle lies
  /// within this much of a stored line. The two texts are timed by different recognisers.
  static const cascadeReach = Duration(seconds: 2);

  /// Reliability experiment `live_words_cascade`: a live word that no stored line has replaced is
  /// dropped once it is this old, where stored text exists to compare it with.
  static const cascadeTimeout = Duration(minutes: 5);

  /// Prepare final intervals once for a transcript snapshot. Preview revisions
  /// can reuse them without walking the final history again.
  ///
  /// [cascade] (default: reliability experiment `live_words_cascade` is on) replaces the settled-tail
  /// rule with one rule per word, whatever state the conversation is in: a live word stays until a
  /// stored line covers its moment of audio ([cascadeReach]) or it is [cascadeTimeout] old.
  LivePreviewCoverage.forFinals(List<TranscriptSegment> finals, DateTime? origin,
      {bool? cascade, DateTime Function()? now})
      : _hasOrigin = origin != null,
        _merged = origin == null ? const [] : _mergedFinalSpans(finals, origin),
        _cascade = cascade ?? LivePreviewController.cascadeEnabled(),
        _now = now ?? DateTime.now;

  final bool _hasOrigin;
  final List<_TimeSpan> _merged;
  final bool _cascade;
  final DateTime Function() _now;

  /// Stored text, else live words: [lines] without the words a stored line covers, and without the
  /// words older than [cascadeTimeout] that none has replaced. With no stored line at all there is
  /// nothing to wait for and nothing is dropped.
  List<LivePreviewLine> _cascadeUncovered(List<LivePreviewLine> lines) {
    final merged = _merged;
    if (merged.isEmpty) return List.of(lines);
    final reach = cascadeReach.inMicroseconds;
    final oldest = _now().microsecondsSinceEpoch - cascadeTimeout.inMicroseconds;
    bool stored(int at) {
      var low = 0, high = merged.length;
      while (low < high) {
        final mid = (low + high) >> 1;
        if (merged[mid].$2 + reach < at) {
          low = mid + 1;
        } else {
          high = mid;
        }
      }
      return low < merged.length && merged[low].$1 - reach <= at;
    }

    bool keep(int startUs, int endUs) =>
        startUs >= oldest && !stored((startUs + (endUs < startUs ? startUs : endUs)) ~/ 2);

    final result = <LivePreviewLine>[];
    for (final line in lines) {
      if (line.spans.isEmpty) {
        final start = (line.startedAt ?? line.firstSeenAt)?.microsecondsSinceEpoch;
        if (start == null || keep(start, line.endedAt?.microsecondsSinceEpoch ?? start)) result.add(line);
        continue;
      }
      final spans = [
        for (final span in line.spans)
          if (keep(span.startedAt.microsecondsSinceEpoch, span.endedAt.microsecondsSinceEpoch)) span,
      ];
      if (spans.length == line.spans.length) {
        result.add(line);
      } else if (spans.isNotEmpty) {
        final text = LivePreviewLine.textOf(spans);
        if (text.isEmpty) continue;
        result.add(LivePreviewLine(
          id: line.id,
          isFinal: line.isFinal,
          text: text,
          startedAt: spans.first.startedAt,
          endedAt: spans.last.endedAt,
          firstSeenAt: line.firstSeenAt,
          spans: spans,
        ));
      }
    }
    return result;
  }

  static List<LivePreviewLine> uncovered(
          List<LivePreviewLine> lines, List<TranscriptSegment> finals, DateTime? origin) =>
      LivePreviewCoverage.forFinals(finals, origin).excludeCovered(lines);

  static List<_TimeSpan> _mergedFinalSpans(List<TranscriptSegment> finals, DateTime origin) {
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
    return merged;
  }

  List<LivePreviewLine> excludeCovered(List<LivePreviewLine> lines) {
    if (!_hasOrigin) return List.of(lines);
    if (_cascade) return _cascadeUncovered(lines);
    final merged = _merged;

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
