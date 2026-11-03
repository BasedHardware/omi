import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';

class StaleSpeakerException implements Exception {
  const StaleSpeakerException();
}

class RecordingLine {
  RecordingLine(this.conversationId, this.segment, {this.scope, this.label});
  final String conversationId;
  final TranscriptSegment segment;
  final String? scope;
  final String? label;
  (String, String)? get voice => scope == null || label == null ? null : (scope!, label!);
}

class RecordingTranscript {
  RecordingTranscript(this.lines, {this.episodeId});
  final List<RecordingLine> lines;
  final String? episodeId;
}

typedef RecordingAssignmentCall = Future<ApiResult<int>> Function(
    String conversationId, List<Map<String, dynamic>> selections,
    {required String personId, required bool wholeRecording, String? episodeId});

Future<ApiResult<RecordingTranscript>> getRecordingTranscript(String conversationId) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}/recording-speakers',
        method: 'GET',
      ),
      decode: (raw) {
        final body = jsonDecode(raw) as Map<String, dynamic>;
        return RecordingTranscript([
          for (final conversation in body['conversations'])
            for (final line in conversation['transcript_segments'])
              RecordingLine(conversation['id'], TranscriptSegment.fromJson(line),
                  scope: line['speaker_id_scope'], label: line['stream_speaker'] ?? line['speaker']),
        ], episodeId: body['episode_id']);
      },
    );

Future<ApiResult<int>> assignRecordingSpeakers(String conversationId, List<Map<String, dynamic>> selections,
    {required String personId, required bool wholeRecording, String? episodeId, ApiSend? send}) async {
  final route = episodeId == null
      ? 'conversations/${Uri.encodeComponent(conversationId)}/recording-speakers'
      : 'episodes/${Uri.encodeComponent(episodeId)}/assign-speaker';
  return executeApi(
    request: ApiRequest(
      url: '${Env.apiBaseUrl}v1/$route',
      method: 'PATCH',
      body: jsonEncode({
        'selections': selections,
        'whole_recording': wholeRecording,
        'is_user': personId == 'user',
        'person_id': personId == 'user' || personId.isEmpty ? null : personId,
      }),
    ),
    send: send,
    decode: (body) => (jsonDecode(body) as Map<String, dynamic>)['applied_count'] as int,
  );
}
