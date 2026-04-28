import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/ambient_capture/ambient_capture_models.dart';

Future<String?> uploadAmbientFallbackSegments({
  required String deviceId,
  String? conversationId,
  required List<AmbientFallbackSegment> segments,
}) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/ambient-capture/fallback-segments',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'device_id': deviceId,
      if (conversationId != null) 'conversation_id': conversationId,
      'segments': segments.map((segment) => segment.toJson()).toList(),
    }),
  );
  if (response == null || response.statusCode >= 300) return null;
  return jsonDecode(response.body)['conversation_id']?.toString();
}

Future<bool> sendAmbientTelemetry({
  required String type,
  Map<String, dynamic> metadata = const {},
}) async {
  final safeMetadata = Map<String, dynamic>.from(metadata)
    ..remove('text')
    ..remove('transcript')
    ..remove('audio')
    ..remove('raw_audio')
    ..remove('payload');
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/ambient-capture/telemetry',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'type': type,
      'timestamp': DateTime.now().toUtc().toIso8601String(),
      'metadata': safeMetadata,
    }),
  );
  return response != null && response.statusCode < 300;
}
