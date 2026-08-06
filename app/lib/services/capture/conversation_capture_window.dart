import 'dart:math';

import 'package:omi/backend/schema/transcript_segment.dart';

class ConversationCaptureWindow {
  const ConversationCaptureWindow({
    required this.startSeconds,
    required this.endSeconds,
  });

  final int startSeconds;
  final int endSeconds;

  static bool hasServerSpeechProof(List<TranscriptSegment> segments) =>
      segments.any((segment) => segment.text.trim().isNotEmpty && segment.end > segment.start);

  factory ConversationCaptureWindow.fromTranscript({
    required int sessionOriginSeconds,
    required int fallbackStartSeconds,
    required int fallbackEndSeconds,
    required List<TranscriptSegment> segments,
    int transcriptMarginSeconds = 2,
  }) {
    if (segments.isEmpty) {
      return ConversationCaptureWindow(
        startSeconds: fallbackStartSeconds,
        endSeconds: fallbackEndSeconds,
      );
    }

    final firstSpeechOffset = segments.map((segment) => segment.start).reduce(min).floor();
    final lastSpeechOffset = segments.map((segment) => segment.end).reduce(max).ceil();
    return ConversationCaptureWindow(
      startSeconds: sessionOriginSeconds + firstSpeechOffset - transcriptMarginSeconds,
      endSeconds: sessionOriginSeconds + lastSpeechOffset + transcriptMarginSeconds,
    );
  }
}
