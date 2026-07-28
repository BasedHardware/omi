import 'package:omi/backend/schema/transcript_segment.dart';

/// Reconciles an eventually-consistent server snapshot with the segments
/// already visible in the live capture UI.
///
/// Reconnect is not a conversation boundary. An empty or stale HTTP snapshot
/// must therefore never erase segments already received from the socket.
class LiveTranscriptPreview {
  const LiveTranscriptPreview._();

  static List<TranscriptSegment> reconcile({
    required List<TranscriptSegment> current,
    required List<TranscriptSegment> serverSnapshot,
  }) {
    if (serverSnapshot.isEmpty) {
      return List<TranscriptSegment>.from(current);
    }

    final merged = List<TranscriptSegment>.from(current);
    final additions = TranscriptSegment.updateSegments(
      merged,
      serverSnapshot,
    );
    merged.addAll(additions);
    merged.sort((left, right) {
      final start = left.start.compareTo(right.start);
      return start != 0 ? start : left.end.compareTo(right.end);
    });
    return merged;
  }
}
