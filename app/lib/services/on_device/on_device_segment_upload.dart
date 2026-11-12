import 'dart:convert';
import 'dart:math';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

/// Chunk boundaries never merge speakers or reset timestamps. Retrying the same
/// recording resends the same indices under its original client_session_id.
Future<String> uploadOnDeviceSegments(
    {required String baseUrl,
    required String sessionId,
    required List<TranscriptSegment> segments,
    required Map<String, dynamic> metadata,
    required bool chunked,
    required bool Function() canSend,
    ApiSend? send,
    Map<String, dynamic>? projection}) async {
  if (segments.isEmpty || (!chunked && segments.length > 500)) {
    throw StateError('Transcript exceeds ingestion limit; audio retained');
  }
  final count = chunked ? (segments.length / 500).ceil() : 1;
  if (count > 128) throw StateError('Transcript exceeds continuation budget; audio retained');
  var resultId = sessionId;
  for (var index = 0; index < count; index++) {
    if (!canSend()) throw StateError('Transcript upload cancelled');
    final chunk = segments.sublist(index * 500, min((index + 1) * 500, segments.length));
    final response = await executeApi<String>(
        send: send,
        canSend: canSend,
        request: ApiRequest(
            url: '${baseUrl}v1/conversations/from-segments',
            method: 'POST',
            body: jsonEncode({
              ...metadata,
              'client_session_id': sessionId,
              'transcript_segments': chunk.map((s) => s.toJson()).toList(),
              if (chunked) 'chunk_index': index,
              if (chunked) 'chunk_count': count,
              if (projection != null && index == count - 1) 'client_processing': projection,
            })),
        decode: (body) => (jsonDecode(body) as Map<String, dynamic>)['id'] as String);
    switch (response) {
      case ApiSuccess<String>():
        resultId = response.data;
      case ApiFailure<String>():
        throw StateError('Transcript ingestion ${response.problem.kind.name}');
    }
  }
  if (!canSend()) throw StateError('Transcript upload cancelled');
  return resultId;
}
