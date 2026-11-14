import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

/// Tells the server a recording ended. Times are this phone's clock in epoch
/// seconds. Returns whether the server accepted it; false covers "no upload of
/// this recording is bound yet", an old server and any transport failure, all
/// of which leave the server's ordinary wait in place.
Future<bool> postSyncCaptureEnd({
  required String recordingSessionId,
  required String endType,
  required DateTime lastSpeechAt,
  required DateTime endDecidedAt,
  required DateTime sentAt,
  required int pendingWals,
}) async {
  double seconds(DateTime value) => value.millisecondsSinceEpoch / 1000.0;
  try {
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v2/sync-capture-end',
      headers: const {},
      body: jsonEncode({
        'recording_session_id': recordingSessionId,
        'end_type': endType,
        'last_speech_at': seconds(lastSpeechAt),
        'end_decided_at': seconds(endDecidedAt),
        'sent_at': seconds(sentAt),
        'pending_wals': pendingWals,
      }),
      method: 'POST',
    );
    if (response?.statusCode != 200) return false;
    final body = jsonDecode(response!.body);
    return body is Map<String, dynamic> && body['accepted'] == true;
  } catch (_) {
    return false;
  }
}
