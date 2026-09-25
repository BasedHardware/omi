import 'dart:typed_data';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/services/sockets/transcription_polling_service.dart';

void main() {
  final audio = Uint8List.fromList([1, 2, 3]);

  SchemaBasedSttProvider providerWith(http.Client client) {
    // Mirrors how the custom STT provider is actually configured
    // (multipart_form is "the real path used for custom STT" per its
    // provider config in stt_provider.dart).
    return SchemaBasedSttProvider(
      apiUrl: 'http://127.0.0.1:8080/inference',
      schema: SttResponseSchema.openAI,
      audioFieldName: 'file',
      requestBodyType: SttRequestBodyType.multipartForm,
      client: client,
    );
  }

  test('retries a multipart request on 5xx and succeeds once the endpoint recovers', () {
    fakeAsync((async) {
      var calls = 0;
      final client = MockClient((request) async {
        calls++;
        if (calls < 3) return http.Response('server error', 503);
        return http.Response('{"segments": [{"text": "hi", "start": 0, "end": 1}]}', 200);
      });

      int? segmentCount;
      providerWith(client).transcribe(audio).then((r) => segmentCount = r?.segments.length);

      async.elapse(const Duration(seconds: 10));

      expect(calls, 3);
      expect(segmentCount, 1);
    });
  });

  test('does not retry a 4xx response', () {
    fakeAsync((async) {
      var calls = 0;
      final client = MockClient((request) async {
        calls++;
        return http.Response('bad request', 400);
      });

      var completed = false;
      providerWith(client).transcribe(audio).then((_) => completed = true);

      async.elapse(const Duration(seconds: 10));

      expect(calls, 1);
      expect(completed, isTrue);
    });
  });

  test('gives up after the max attempts and rethrows', () {
    fakeAsync((async) {
      var calls = 0;
      final client = MockClient((request) async {
        calls++;
        throw Exception('connection refused');
      });

      Object? error;
      providerWith(client).transcribe(audio).catchError((e) {
        error = e;
        return null;
      });

      async.elapse(const Duration(seconds: 10));

      expect(calls, 3);
      expect(error, isNotNull);
    });
  });

  test('a hanging endpoint fails well under the old 60s-per-chunk hang', () {
    fakeAsync((async) {
      var calls = 0;
      final client = MockClient((request) async {
        calls++;
        // Never responds — exercises the per-attempt timeout instead of
        // hanging for a real 60s like before this patch.
        await Future.delayed(const Duration(minutes: 5));
        return http.Response('{"segments": []}', 200);
      });

      Object? error;
      providerWith(client).transcribe(audio).catchError((e) {
        error = e;
        return null;
      });

      // Old behavior needed 60s+ to fail a *single* attempt; 3 attempts at a
      // 10s timeout plus backoff should all resolve well before 40s.
      async.elapse(const Duration(seconds: 40));

      expect(calls, 3);
      expect(error, isNotNull);
    });
  });
}
