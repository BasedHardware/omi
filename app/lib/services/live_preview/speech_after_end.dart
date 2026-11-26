import 'package:omi/services/live_preview/live_preview_controller.dart';

/// Reliability experiment `instant_live_text`: whether the on-device recogniser has heard words spoken
/// after a conversation was ended. Lines survive an End, so the earlier conversation's lines are still
/// in the list; only audio time decides.
class SpeechAfterEnd {
  SpeechAfterEnd._();

  /// True when some non-empty line has a word that starts at or after [endedAt]. A line without word
  /// times counts from its own start (audio time, else when the recogniser first reported it).
  static bool heard(Iterable<LivePreviewLine> lines, DateTime endedAt) => firstHeard(lines, endedAt) != null;

  /// When the earliest such word was spoken, or null when there is none. Same rule as [heard]; used only
  /// to time how long after that word the Listening row came back.
  static DateTime? firstHeard(Iterable<LivePreviewLine> lines, DateTime endedAt) {
    DateTime? first;
    void note(DateTime at) {
      if (first == null || at.isBefore(first!)) first = at;
    }

    for (final line in lines) {
      if (line.text.trim().isEmpty) continue;
      var counted = false;
      for (final span in line.spans) {
        if (span.text.trim().isNotEmpty && !span.startedAt.isBefore(endedAt)) {
          note(span.startedAt);
          counted = true;
        }
      }
      if (counted) continue;
      final start = line.startedAt ?? line.firstSeenAt;
      if (start != null && !start.isBefore(endedAt)) note(start);
    }
    return first;
  }
}
