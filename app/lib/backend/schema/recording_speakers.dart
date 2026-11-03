import 'dart:convert';

import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/backend/schema/gen/recording_speakers_wire.g.dart' as wire;

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
  RecordingTranscript(this.lines, {this.episodeId, this.enabled = true, this.coverage = 'partial'});
  factory RecordingTranscript.fromResponse(String raw) {
    final body = wire.GeneratedRecordingTranscriptResponse.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    return RecordingTranscript([
      for (final conversation in body.conversations)
        for (final line in conversation.transcriptSegments)
          RecordingLine(conversation.id, TranscriptSegment.fromJson(line.toJson()),
              scope: line.speakerIdScope, label: line.streamSpeaker, offset: conversation.recordingOffsetSeconds),
    ], episodeId: body.episodeId, enabled: body.enabled, coverage: body.coverage);
  }
  final bool enabled;
  final String coverage;
  bool get coverageComplete => enabled && coverage == 'complete';
  final List<RecordingLine> lines;
  final String? episodeId;
}

Map<String, dynamic> decodeRecordingAssignment(String raw) {
  final body = jsonDecode(raw);
  if (body is! Map<String, dynamic>) throw const FormatException('Invalid speaker assignment response');
  if (body['enabled'] == false) return body;
  final outcomes = body['conversations'];
  if (body['applied_count'] is! int ||
      outcomes is! List ||
      outcomes.any((row) =>
          row is! Map<String, dynamic> ||
          row['conversation_id'] is! String ||
          row['applied_count'] is! int ||
          (row['error'] != null && row['error'] is! String))) {
    throw const FormatException('Invalid speaker assignment outcomes');
  }
  return wire.GeneratedRecordingSpeakerResponse.fromJson(body).toJson();
}
