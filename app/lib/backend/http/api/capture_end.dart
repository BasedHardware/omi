import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

/// Tells the server a recording ended. Times are this phone's clock in epoch
/// seconds; [lastSpeechAt] is null when no speech was detected, and is sent as
/// null. Success carries whether the server accepted the marker; it answers
/// false while no upload of the recording is bound yet. A failure (an old
/// server, no network, a refused request) is returned as such: the caller
/// keeps the end and the server's ordinary wait stays in place.
Future<ApiResult<bool>> postSyncCaptureEnd({
  required String recordingSessionId,
  required String endType,
  required DateTime? lastSpeechAt,
  required DateTime endDecidedAt,
  required DateTime sentAt,
  required int pendingWals,
  ApiSend? send,
}) {
  double seconds(DateTime value) => value.millisecondsSinceEpoch / 1000.0;
  final base = (Env.apiBaseUrl ?? '').replaceFirst(RegExp(r'/$'), '');
  return executeApi(
    request: ApiRequest(
      url: '$base/v2/sync-capture-end',
      method: 'POST',
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({
        'recording_session_id': recordingSessionId,
        'end_type': endType,
        'last_speech_at': lastSpeechAt == null ? null : seconds(lastSpeechAt),
        'end_decided_at': seconds(endDecidedAt),
        'sent_at': seconds(sentAt),
        'pending_wals': pendingWals,
      }),
    ),
    send: send,
    decode: (body) {
      final data = jsonDecode(body);
      if (data is! Map<String, dynamic>) throw const FormatException('capture end response is not an object');
      return data['accepted'] == true;
    },
  );
}
