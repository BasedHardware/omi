import 'package:omi/services/live_preview/live_preview_controller.dart';

/// Reliability experiment `live_words_cascade`: the live words the phone was showing for the
/// conversation being ended, as the End request carries them (`live_tail`).
///
/// The server keeps it with the stored End only, drops every word stored text already covers, and
/// gives what is left to that conversation's summary. It never becomes transcript. Plain words with
/// their times on the phone's capture clock (seconds since the epoch), nothing else; when the words
/// exceed the bounds the newest are kept, because the oldest are the ones stored text covers first.
final class LiveTail {
  LiveTail._();

  static const version = 1;
  static const maxWords = 600;
  static const maxChars = 6000;
  static const maxWordChars = 48;

  /// The request field for [lines] (already cut to the conversation being ended), or null when they
  /// hold no words. Each line is a list of `[text, start, end]`.
  static Map<String, Object?>? payload(List<LivePreviewLine> lines, {required DateTime endedAt}) {
    final kept = <List<List<Object>>>[];
    var words = 0, chars = 0;
    var full = false;
    for (final line in lines.reversed) {
      if (full) break;
      final entries = <List<Object>>[];
      // Newest first inside the line too, so the bound drops the oldest words.
      for (final (text, start, end) in _entries(line).reversed) {
        final count = text.split(RegExp(r'\s+')).where((word) => word.isNotEmpty).length;
        if (count == 0) continue;
        if (words + count > maxWords || chars + text.length > maxChars) {
          full = true;
          break;
        }
        words += count;
        chars += text.length;
        entries.add([text, _seconds(start), _seconds(end)]);
      }
      if (entries.isNotEmpty) kept.add(entries.reversed.toList());
    }
    if (kept.isEmpty) return null;
    return {
      'v': version,
      'ended_at': _seconds(endedAt),
      'lines': kept.reversed.toList(),
    };
  }

  /// How many words [payload] carries (for the local record; never the words themselves).
  static int wordCount(Map<String, Object?>? payload) {
    final lines = payload?['lines'];
    if (lines is! List) return 0;
    var count = 0;
    for (final line in lines) {
      if (line is! List) continue;
      for (final entry in line) {
        if (entry is List && entry.isNotEmpty && entry[0] is String) {
          count += (entry[0] as String).split(RegExp(r'\s+')).where((word) => word.isNotEmpty).length;
        }
      }
    }
    return count;
  }

  static Iterable<(String, DateTime, DateTime)> _entriesOf(LivePreviewLine line) sync* {
    if (line.spans.isNotEmpty) {
      for (final span in line.spans) {
        final text = _plain(span.text, maxWordChars);
        if (text.isNotEmpty) yield (text, span.startedAt, span.endedAt);
      }
      return;
    }
    // A line without word times goes as one entry with the line's own times.
    final start = line.startedAt ?? line.firstSeenAt;
    if (start == null) return;
    final text = _plain(line.text, 600);
    if (text.isNotEmpty) yield (text, start, line.endedAt ?? start);
  }

  static List<(String, DateTime, DateTime)> _entries(LivePreviewLine line) => _entriesOf(line).toList();

  // Plain text only: control characters out, runs of white space to one space, bounded.
  static String _plain(String text, int limit) {
    final clean = text.replaceAll(RegExp(r'[\u0000-\u001f\u007f]'), ' ').replaceAll(RegExp(r'\s+'), ' ').trim();
    return clean.length <= limit ? clean : clean.substring(0, limit);
  }

  static double _seconds(DateTime at) => at.toUtc().millisecondsSinceEpoch / 1000;
}
