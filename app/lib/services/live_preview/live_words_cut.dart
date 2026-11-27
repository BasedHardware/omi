import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';

/// Reliability experiment `live_words_cascade`: live words cut at an instant, per word.
///
/// A word belongs to the side its start falls on, so a line that straddles the instant is split
/// there. A line without word times is taken whole, by its own start (audio time, else when the
/// recogniser first reported it). Display only: nothing here is stored.
final class LiveWordsCut {
  LiveWordsCut._();

  /// [lines] cut down to the words that start at or after [from] and before [before]. Either bound
  /// may be null. Returns [lines] itself when nothing is cut away.
  static List<LivePreviewLine> within(List<LivePreviewLine> lines, {DateTime? from, DateTime? before}) {
    if (from == null && before == null) return lines;
    bool inside(DateTime at) => (from == null || !at.isBefore(from)) && (before == null || at.isBefore(before));
    List<LivePreviewLine>? out;
    for (var index = 0; index < lines.length; index++) {
      final line = lines[index];
      LivePreviewLine? kept;
      if (line.spans.isEmpty) {
        final start = line.startedAt ?? line.firstSeenAt;
        if (start == null || inside(start)) kept = line;
      } else {
        final spans = [
          for (final span in line.spans)
            if (inside(span.startedAt)) span,
        ];
        if (spans.length == line.spans.length) {
          kept = line;
        } else if (spans.isNotEmpty) {
          kept = _part(line, spans);
        }
      }
      if (identical(kept, line)) {
        out?.add(line);
        continue;
      }
      out ??= lines.sublist(0, index);
      if (kept != null) out.add(kept);
    }
    return out ?? lines;
  }

  /// The words that start at or after [at]: what the conversation that begins there shows.
  static List<LivePreviewLine> after(List<LivePreviewLine> lines, DateTime at) => within(lines, from: at);

  static LivePreviewLine _part(LivePreviewLine line, List<LivePreviewSpan> spans) => LivePreviewLine(
        // One part of a line survives a cut, so it keeps the line's id (and its place on screen).
        id: line.id,
        text: LivePreviewLine.textOf(spans),
        isFinal: line.isFinal,
        startedAt: spans.first.startedAt,
        endedAt: spans.last.endedAt,
        firstSeenAt: line.firstSeenAt,
        spans: spans,
      );
}
