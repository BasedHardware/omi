import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/backend/schema/recording_speakers.dart';
import 'package:omi/env/env.dart';

class StaleSpeakerException implements Exception {
  const StaleSpeakerException();
}

class RecordingSpeakerLimitException implements Exception {
  const RecordingSpeakerLimitException();
}

class PartialSpeakerAssignmentException implements Exception {
  const PartialSpeakerAssignmentException(this.succeeded, this.failed, this.appliedCount, {this.stale = false});
  final Set<String> succeeded;
  final Set<String> failed;
  final int appliedCount;
  final bool stale;
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
                  scope: line['speaker_id_scope'],
                  label: line['stream_speaker'] ?? line['speaker'],
                  offset: (conversation['recording_offset_seconds'] as num?)?.toDouble() ?? 0),
        ], episodeId: body['episode_id'], enabled: body['enabled'] != false);
      },
    );

Future<ApiResult<int>> assignRecordingSpeakers(String conversationId, List<Map<String, dynamic>> selections,
    {required String personId, required bool wholeRecording, String? episodeId, ApiSend? send}) async {
  final url = episodeId == null
      ? '${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}/recording-speakers'
      : '${Env.apiBaseUrl}v1/episodes/${Uri.encodeComponent(episodeId)}/assign-speaker';
  final result = await executeApi<Map<String, dynamic>>(
    request: ApiRequest(
      url: url,
      method: 'PATCH',
      body: jsonEncode({
        'selections': selections,
        'whole_recording': wholeRecording,
        'is_user': personId == 'user',
        'person_id': personId == 'user' || personId.isEmpty ? null : personId,
      }),
    ),
    send: send,
    decode: (raw) {
      final body = jsonDecode(raw);
      if (body is! Map<String, dynamic>) throw const FormatException('Invalid speaker assignment response');
      if (body['enabled'] != false) {
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
      }
      return body;
    },
  );
  if (result is ApiFailure<Map<String, dynamic>>) {
    if (result.problem.statusCode == 404 || result.problem.detail == 'recording_speaker_rename_disabled') {
      return _assignLegacy(conversationId, selections, personId, send);
    }
    return ApiFailure(result.problem);
  }
  final body = (result as ApiSuccess<Map<String, dynamic>>).data;
  if (body['enabled'] == false) return _assignLegacy(conversationId, selections, personId, send);
  final outcomes = (body['conversations'] as List).cast<Map<String, dynamic>>();
  final failures = outcomes.where((row) => row['error'] != null).toList();
  final count = body['applied_count'] as int;
  if (failures.isNotEmpty) {
    if (failures.length == outcomes.length) {
      if (failures.every((row) => row['error'] == 'stale_speaker')) throw const StaleSpeakerException();
      return const ApiFailure(ApiProblem(ApiProblemKind.rejected, detail: 'speaker_save_failed'));
    }
    throw PartialSpeakerAssignmentException(
      outcomes.where((row) => row['error'] == null).map((row) => row['conversation_id'] as String).toSet(),
      failures.map((row) => row['conversation_id'] as String).toSet(),
      count,
      stale: failures.any((row) => row['error'] == 'stale_speaker'),
    );
  }
  return ApiSuccess(count);
}

Future<ApiResult<int>> _assignLegacy(
    String conversationId, List<Map<String, dynamic>> selections, String personId, ApiSend? send) async {
  recordFallback(const ApiFallbackEvent(reason: ApiFallbackReason.error, outcome: ApiFallbackOutcome.degraded));
  final ids = selections
      .where((row) => row['conversation_id'] == conversationId)
      .expand((row) => (row['segment_ids'] as List).cast<String>())
      .toSet()
      .toList();
  if (ids.isEmpty) return const ApiFailure(ApiProblem(ApiProblemKind.rejected));
  final local = selections.where((row) => row['conversation_id'] == conversationId).toList();
  final speakerId = local.length == 1 ? local.single['speaker_id'] as int? : null;
  final assignType = personId == 'user' ? 'is_user' : 'person_id';
  final value = personId == 'user' ? 'true' : (personId.isEmpty ? null : personId);
  final url = speakerId == null
      ? '${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}/segments/assign-bulk'
      : '${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}/assign-speaker/$speakerId?${Uri(queryParameters: {
              'assign_type': assignType,
              'value': value ?? 'null'
            }).query}';
  // Explicit ids keep the selection bounded; the legacy speaker route also
  // preserves its numeric stale-speaker fence when a voice was selected.
  final result = await executeApi<int>(
    request: ApiRequest(
      url: url,
      method: 'PATCH',
      body: jsonEncode({
        'segment_ids': ids,
        'assign_type': personId == 'user' ? 'is_user' : 'person_id',
        'value': personId == 'user' ? 'true' : (personId.isEmpty ? null : personId)
      }),
    ),
    send: send,
    decode: (_) => ids.length,
  );
  final other = selections
      .where((row) => row['conversation_id'] != conversationId)
      .map((row) => row['conversation_id'] as String)
      .toSet();
  if (result is ApiSuccess<int> && other.isNotEmpty) {
    throw PartialSpeakerAssignmentException({conversationId}, other, result.data);
  }
  return result;
}
