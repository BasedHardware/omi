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
        if (part == 0 && run.length == line.spans.length) {
          // Nothing of this line is covered: it stays the line the recogniser sent.
          out.add(line);
          run = <LivePreviewSpan>[];
          part++;
          return;
        }
        out.add(LivePreviewLine(
          id: '${line.id}#$part',
          text: LivePreviewLine.textOf(run),
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
    return _interleaved(own, extra);
  }

  /// Reliability experiment `live_words_cascade`: the same merge with the roles the other way round.
  /// Per stretch of audio time the vendor's words show where it has them, and the phone's own
  /// recogniser's words only where the vendor has none within [tolerance]: a draft the vendor's words
  /// replace when they arrive. A line of the phone's recogniser the vendor covers in part keeps only its
  /// uncovered words.
  ///
  /// The phone's recogniser reports each finished phrase as a result of its own, a few words long; the
  /// vendor's lines are a whole turn of speech. Shown one line per phrase, the draft is a column of
  /// short paragraphs that collapses into one when the vendor's line replaces it. So consecutive draft
  /// lines are joined into one paragraph ([paragraphs]); the vendor's lines are left as they come.
  static List<LivePreviewLine> cascade(List<LivePreviewLine> own, List<LivePreviewLine> vendor) {
    if (own.isEmpty) return vendor;
    if (vendor.isEmpty) return paragraphs(own, own);
    final draft = uncovered(own, coverage(vendor));
    if (draft.isEmpty) return vendor;
    return paragraphs(_interleaved(vendor, draft), draft);
  }

  /// A pause this long starts a new paragraph of the draft, as it starts a new line of the vendor's.
  static const paragraphGap = Duration(seconds: 3);

  /// A paragraph of the draft is at most this long, like a line of the vendor's.
  static const paragraphMaxChars = 600;

  /// [lines] with each run of consecutive [draft] lines (the phone's recogniser's, with word times)
  /// joined into one line, as long as no pause of [paragraphGap] lies between two of them and the text
  /// stays under [paragraphMaxChars]. Every other line passes through untouched and ends a run, so the
  /// order of the words never changes.
  static List<LivePreviewLine> paragraphs(List<LivePreviewLine> lines, List<LivePreviewLine> draft) {
    if (draft.length < 2) return lines;
    final joinable = Set<LivePreviewLine>.identity()..addAll(draft.where((line) => line.spans.isNotEmpty));
    final out = <LivePreviewLine>[];
    var run = <LivePreviewLine>[];
    var chars = 0;
    void close() {
      if (run.length == 1) {
        out.add(run.single);
      } else if (run.isNotEmpty) {
        out.add(LivePreviewLine(
          // The paragraph keeps its place on screen while its first phrase stays.
          id: 'p:${run.first.id}',
          text: run.map((line) => line.text.trim()).where((text) => text.isNotEmpty).join(' '),
          isFinal: run.every((line) => line.isFinal),
          startedAt: run.first.startedAt,
          endedAt: run.last.endedAt,
          firstSeenAt: run.first.firstSeenAt,
          spans: [for (final line in run) ...line.spans],
        ));
      }
      run = <LivePreviewLine>[];
      chars = 0;
    }

    for (final line in lines) {
      if (!joinable.contains(line)) {
        close();
        out.add(line);
        continue;
      }
      if (run.isNotEmpty) {
        final pause = line.spans.first.startedAt.difference(run.last.spans.last.endedAt);
        if (pause >= paragraphGap || chars + line.text.length + 1 > paragraphMaxChars) close();
      }
      run.add(line);
      chars += line.text.length + 1;
    }
    close();
    return out;
  }

  // Each list is already in order; keep that order and interleave by start. [first] wins a tie.
  static List<LivePreviewLine> _interleaved(List<LivePreviewLine> first, List<LivePreviewLine> second) {
    int key(LivePreviewLine line) => (line.startedAt ?? line.firstSeenAt)?.microsecondsSinceEpoch ?? 0x7fffffffffffffff;
    final out = <LivePreviewLine>[];
    var i = 0, j = 0;
    while (i < first.length || j < second.length) {
      if (j >= second.length || (i < first.length && key(first[i]) <= key(second[j]))) {
        out.add(first[i++]);
      } else {
        out.add(second[j++]);
      }
    }
    return out;
  }

  /// Microseconds of [start]..[end] that neither [a] nor [b] covers (both as [coverage] returns them).
  static int uncoveredMicros(int start, int end, List<(int, int)> a, List<(int, int)> b) {
    if (end <= start) return 0;
    final spans = [
      for (final span in a)
        if (span.$2 > start && span.$1 < end) span,
      for (final span in b)
        if (span.$2 > start && span.$1 < end) span,
    ]..sort((x, y) => x.$1.compareTo(y.$1));
    var free = 0;
    var cursor = start;
    for (final span in spans) {
      if (span.$1 > cursor) free += span.$1 - cursor;
      if (span.$2 > cursor) cursor = span.$2;
      if (cursor >= end) break;
    }
    if (cursor < end) free += end - cursor;
    return free;
  }
}
