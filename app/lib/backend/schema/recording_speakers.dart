import 'package:omi/backend/schema/transcript_segment.dart';

class RecordingLine {
  RecordingLine(this.conversationId, this.segment, {this.scope, this.label, this.offset = 0});
  final String conversationId;
  final TranscriptSegment segment;
  final String? scope;
  final String? label;
  final double offset;
  (String, String)? get voice {
    final voiceScope = scope ?? segment.recordingVoice?.$1;
    final voiceLabel = label ?? segment.recordingVoice?.$2;
    if (voiceScope == null || voiceScope.isEmpty || voiceLabel == null || voiceLabel.isEmpty) return null;
    return (voiceScope, voiceLabel);
  }
}

class RecordingTranscript {
  RecordingTranscript(this.lines, {this.episodeId, this.enabled = true});
  final bool enabled;
  final List<RecordingLine> lines;
  final String? episodeId;
}
