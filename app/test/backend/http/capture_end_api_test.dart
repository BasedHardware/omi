import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/capture_end.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

void main() {
  setUp(() => Env.overrideApiBaseUrl('http://127.0.0.1/'));

  DateTime at(int seconds) => DateTime.fromMillisecondsSinceEpoch(seconds * 1000, isUtc: true);

  Future<ApiResult<bool>> call(ApiSend send) => postSyncCaptureEnd(
        recordingSessionId: 'rec',
        endType: 'user_initiated',
        lastSpeechAt: at(1000),
        endDecidedAt: at(1002),
        sentAt: at(1010),
        pendingWals: 2,
        send: send,
      );

  test('posts the marker in device-clock epoch seconds and returns the server answer', () async {
    late ApiRequest seen;
    final result = await call((request) async {
      seen = request;
      return http.Response(jsonEncode({'accepted': true, 'retry': false}), 200);
    });
    expect(seen.method, 'POST');
    expect(seen.url, endsWith('/v2/sync-capture-end'));
    expect(jsonDecode(seen.body), {
      'recording_session_id': 'rec',
      'end_type': 'user_initiated',
      'last_speech_at': 1000.0,
      'end_decided_at': 1002.0,
      'sent_at': 1010.0,
      'pending_wals': 2,
    });
    expect(result, isA<ApiSuccess<bool>>().having((r) => r.data, 'accepted', true));
  });

  test('no detected speech is sent as null, never as an invented time', () async {
    late ApiRequest seen;
    await postSyncCaptureEnd(
      recordingSessionId: 'rec',
      endType: 'disconnect',
      lastSpeechAt: null,
      endDecidedAt: at(1002),
      sentAt: at(1010),
      pendingWals: 0,
      send: (request) async {
        seen = request;
        return http.Response(jsonEncode({'accepted': true}), 200);
      },
    );
    final body = jsonDecode(seen.body) as Map<String, dynamic>;
    expect(body.containsKey('last_speech_at'), isTrue);
    expect(body['last_speech_at'], isNull);
  });

  test('not bound yet is a successful false, not a failure', () async {
    final result = await call((_) async => http.Response(jsonEncode({'accepted': false, 'retry': true}), 200));
    expect(result, isA<ApiSuccess<bool>>().having((r) => r.data, 'accepted', false));
  });

  test('an old server or an outage is a typed failure the caller can see', () async {
    expect(await call((_) async => http.Response('Not Found', 404)), isA<ApiFailure<bool>>());
    expect(await call((_) async => http.Response('unavailable', 503)), isA<ApiFailure<bool>>());
    expect(await call((_) async => http.Response('[]', 200)), isA<ApiFailure<bool>>());
  });
}
