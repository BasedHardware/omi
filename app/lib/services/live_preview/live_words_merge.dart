import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';

/// Reliability experiment `vendor_recognizer_on_opened_app`: one list of live words from two sources.
///
/// The phone's own recogniser comes first. A word from the vendor stream shows only where the phone's
/// recogniser returned nothing: no line of its own within [tolerance] of that word. When the phone's
/// recogniser later fills the stretch, the vendor's words for it drop out on the next merge. With no
/// lines from the phone's recogniser at all, every vendor line shows.
///
/// Both sources are timed on the phone's capture clock, so only audio time decides. Display only:
/// nothing here is stored.
final class LiveWordsMerge {
  LiveWordsMerge._();

  static const tolerance = Duration(seconds: 1);

  /// A line without audio times is taken to cover this long before the recogniser first reported it.
  static const untimedReach = Duration(seconds: 10);

  /// The stretches the phone's recogniser has words for, each widened by [tolerance], sorted and
  /// joined. Microseconds since epoch.
  static List<(int, int)> coverage(Iterable<LivePreviewLine> own) {
    final spans = <(int, int)>[];
    final pad = tolerance.inMicroseconds;
    for (final line in own) {
      if (line.text.trim().isEmpty) continue;
      var start = line.startedAt?.microsecondsSinceEpoch;
      var end = line.endedAt?.microsecondsSinceEpoch;
      for (final span in line.spans) {
        final spanStart = span.startedAt.microsecondsSinceEpoch;
        final spanEnd = span.endedAt.microsecondsSinceEpoch;
        if (start == null || spanStart < start) start = spanStart;
        if (end == null || spanEnd > end) end = spanEnd;
      }
      if (start == null || end == null) {
        final seen = line.firstSeenAt?.microsecondsSinceEpoch;
        if (seen == null) continue;
        start ??= seen - untimedReach.inMicroseconds;
        end ??= seen;
      }
      if (end < start) end = start;
      spans.add((start - pad, end + pad));
    }
    spans.sort((a, b) => a.$1.compareTo(b.$1));
    final joined = <(int, int)>[];
    for (final span in spans) {
      if (joined.isEmpty || span.$1 > joined.last.$2) {
        joined.add(span);
      } else if (span.$2 > joined.last.$2) {
        joined[joined.length - 1] = (joined.last.$1, span.$2);
      }
    }
    return joined;
  }

  /// Whether [start]..[end] touches a covered stretch.
  static bool covered(List<(int, int)> coverage, DateTime start, DateTime end) {
    final startUs = start.microsecondsSinceEpoch;
    final endUs = end.microsecondsSinceEpoch < startUs ? startUs : end.microsecondsSinceEpoch;
    var low = 0, high = coverage.length;
    while (low < high) {
      final mid = (low + high) >> 1;
      if (coverage[mid].$2 < startUs) {
        low = mid + 1;
      } else {
        high = mid;
      }
    }
    return low < coverage.length && coverage[low].$1 <= endUs;
  }

  /// The vendor's lines cut down to the words the phone's recogniser has nothing for. A line the
  /// phone's recogniser covers in the middle becomes two.
  static List<LivePreviewLine> uncovered(List<LivePreviewLine> vendor, List<(int, int)> coverage) {
    if (coverage.isEmpty) return List.of(vendor);
    final out = <LivePreviewLine>[];
    for (final line in vendor) {
      if (line.spans.isEmpty) {
        final start = line.startedAt, end = line.endedAt;
        if (start == null || end == null || !covered(coverage, start, end)) out.add(line);
        continue;
      }
      var run = <LivePreviewSpan>[];
      var part = 0;
      void close() {
        if (run.isEmpty) return;
        out.add(LivePreviewLine(
          id: part == 0 && run.length == line.spans.length ? line.id : '${line.id}#$part',
          text: run.map((span) => span.text).join(' '),
          isFinal: line.isFinal,
          startedAt: run.first.startedAt,
          endedAt: run.last.endedAt,
          firstSeenAt: line.firstSeenAt,
          spans: run,
        ));
        part++;
        run = <LivePreviewSpan>[];
      }

      for (final span in line.spans) {
        if (covered(coverage, span.startedAt, span.endedAt)) {
          close();
        } else {
          run.add(span);
        }
      }
      close();
    }
    return out;
  }

  /// [own] with the [vendor] words it has nothing for, in audio order.
  static List<LivePreviewLine> merge(List<LivePreviewLine> own, List<LivePreviewLine> vendor) {
    if (vendor.isEmpty) return own;
    final extra = uncovered(vendor, coverage(own));
    if (extra.isEmpty) return own;
    if (own.isEmpty) return extra;
    int key(LivePreviewLine line) => (line.startedAt ?? line.firstSeenAt)?.microsecondsSinceEpoch ?? 0x7fffffffffffffff;
    // Each list is already in order; keep that order and interleave by start.
    final out = <LivePreviewLine>[];
    var i = 0, j = 0;
    while (i < own.length || j < extra.length) {
      if (j >= extra.length || (i < own.length && key(own[i]) <= key(extra[j]))) {
        out.add(own[i++]);
      } else {
        out.add(extra[j++]);
      }
    }
    return out;
  }
}
