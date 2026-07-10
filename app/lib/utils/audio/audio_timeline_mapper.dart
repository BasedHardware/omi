/// Maps between the conversation's wall-clock timeline and the dense playback
/// artifact (one MP3 per conversation, inter-part gaps collapsed).
///
/// Spans come from the backend's `conversation_audio` stamp; `wallOffset` is
/// seconds relative to conversation.startedAt — the same basis as
/// TranscriptSegment.start — and `artifactOffset` is seconds into the MP3.
class ConversationAudioSpan {
  final String fileId;
  final double wallOffset;
  final double artifactOffset;
  final double len;

  const ConversationAudioSpan({
    required this.fileId,
    required this.wallOffset,
    required this.artifactOffset,
    required this.len,
  });

  factory ConversationAudioSpan.fromJson(Map<String, dynamic> json) {
    return ConversationAudioSpan(
      fileId: json['file_id'] ?? '',
      wallOffset: (json['wall_offset'] ?? 0).toDouble(),
      artifactOffset: (json['artifact_offset'] ?? 0).toDouble(),
      len: (json['len'] ?? 0).toDouble(),
    );
  }

  double get wallEnd => wallOffset + len;
  double get artifactEnd => artifactOffset + len;
}

class AudioTimelineMapper {
  final List<ConversationAudioSpan> spans;

  AudioTimelineMapper(List<ConversationAudioSpan> spans)
      : spans = List.of(spans)..sort((a, b) => a.wallOffset.compareTo(b.wallOffset));

  bool get isEmpty => spans.isEmpty;

  double get capturedDuration => spans.isEmpty ? 0 : spans.last.artifactEnd;

  double get wallDuration => spans.isEmpty ? 0 : spans.last.wallEnd;

  /// Wall-clock seconds -> MP3 seconds. A position inside a collapsed gap
  /// snaps forward to the next span's start; before/after the timeline clamps.
  double wallToArtifact(double wallSeconds) {
    if (spans.isEmpty) return 0;
    if (wallSeconds <= spans.first.wallOffset) return spans.first.artifactOffset;
    var lo = 0, hi = spans.length - 1;
    while (lo < hi) {
      final mid = (lo + hi + 1) >> 1;
      if (spans[mid].wallOffset <= wallSeconds) {
        lo = mid;
      } else {
        hi = mid - 1;
      }
    }
    final span = spans[lo];
    if (wallSeconds <= span.wallEnd) {
      return span.artifactOffset + (wallSeconds - span.wallOffset);
    }
    // In the gap after this span: snap to the next span, or clamp at the end.
    return lo + 1 < spans.length ? spans[lo + 1].artifactOffset : capturedDuration;
  }

  /// MP3 seconds -> wall-clock seconds.
  double artifactToWall(double artifactSeconds) {
    if (spans.isEmpty) return 0;
    if (artifactSeconds <= spans.first.artifactOffset) return spans.first.wallOffset;
    var lo = 0, hi = spans.length - 1;
    while (lo < hi) {
      final mid = (lo + hi + 1) >> 1;
      if (spans[mid].artifactOffset <= artifactSeconds) {
        lo = mid;
      } else {
        hi = mid - 1;
      }
    }
    final span = spans[lo];
    if (artifactSeconds <= span.artifactEnd) {
      return span.wallOffset + (artifactSeconds - span.artifactOffset);
    }
    return lo + 1 < spans.length ? spans[lo + 1].wallOffset : wallDuration;
  }

  /// Collapsed-gap ranges on the wall timeline, as (start, end) pairs — used
  /// to shade the scrubber where no audio was captured.
  List<(double, double)> get gapRangesWall {
    final gaps = <(double, double)>[];
    for (var i = 0; i + 1 < spans.length; i++) {
      final end = spans[i].wallEnd;
      final next = spans[i + 1].wallOffset;
      if (next > end) gaps.add((end, next));
    }
    return gaps;
  }
}
