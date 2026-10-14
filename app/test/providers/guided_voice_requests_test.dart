import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/env/env.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/http/streaming_error.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import 'package:omi/pages/onboarding/guided_voice_requests.dart';

String done(String text) => 'done: ${base64Encode(utf8.encode(jsonEncode({
          'id': 'answer',
          'text': text,
          'created_at': '2026-10-13T00:00:00Z',
          'sender': 'ai',
          'type': 'text',
          'memories': [],
        })))}';

void main() {
  setUp(() => Env.overrideApiBaseUrl('http://127.0.0.1/'));
  tearDown(Env.clearApiBaseUrlOverride);
  test('preflight requires a reachable, decodable, affirmative health response', () async {
    for (final response in [
      http.Response('{}', 200),
      http.Response('invalid', 200),
      http.Response('{"available":false}', 200),
      http.Response('{"available":true}', 503)
    ]) {
      expect(await guidedVoicePreflight(probe: (_) async => response), isFalse);
    }
    expect(await guidedVoicePreflight(probe: (_) async => http.Response('{"available":true}', 200)), isTrue);
    expect(await guidedVoicePreflight(probe: (_) async => throw const SocketException('offline')), isFalse);
  });
  test('slow preflight is unknown rather than unavailable', () async {
    final probe = Completer<http.Response>();
    expect(await guidedVoicePreflight(probe: (_) => probe.future, timeout: const Duration(milliseconds: 2)), isTrue);
    expect(await guidedVoicePreflight(probe: (_) async => throw TimeoutException('slow')), isTrue);
    probe.complete(http.Response('{"available":false}', 200));
  });
  test('chat acceptance is emitted after HTTP 200, never offline or rejected', () async {
    for (final status in [200, 503, 402, -1]) {
      var accepted = 0;
      final asking = askGuidedPayoff('Question', ['Saved'],
          onAccepted: () => accepted++,
          seams: ApiStreamingSeams(
            headers: (_) async => {},
            transport: (_) async {
              expect(accepted, 0);
              if (status == -1) throw const SocketException('offline');
              return http.StreamedResponse(Stream.value(utf8.encode('${done('Answer')}\n\n')), status);
            },
          ));
      if (status == 200) {
        expect(await asking, 'Answer');
      } else {
        await expectLater(asking, throwsA(anything));
      }
      expect(accepted, status == 200 ? 1 : 0);
    }
  });
  test('transcription keeps empty and HTTP errors separate without swallowing timeout', () async {
    final file = File('/synthetic/no-read.wav');
    for (final status in [401, 402, 500, 503]) {
      await expectLater(transcribeGuidedAnswer(file, 'en', upload: () async => http.Response('{}', status)),
          throwsA(isA<GuidedVoiceFailure>().having((e) => e.failureClass, 'kind', 'transcribe_http_error')));
    }
    await expectLater(transcribeGuidedAnswer(file, 'en', upload: () async => http.Response('{"transcript":" "}', 200)),
        throwsA(isA<GuidedVoiceFailure>().having((e) => e.failureClass, 'kind', 'transcribe_empty')));
    await expectLater(transcribeGuidedAnswer(file, 'en', upload: () async => throw TimeoutException('synthetic')),
        throwsA(isA<TimeoutException>()));
    expect(
        await transcribeGuidedAnswer(file, 'en',
            upload: () async => http.Response('{"transcript":" I build bicycles. "}', 200)),
        'I build bicycles.');
  });
  test('payoff uses persisted done frame, explicit saved facts and no device tools', () async {
    String? body;
    final text = await askGuidedPayoff('What should I focus on this week?', ['I build bicycles.'], stream: (sent) {
      body = sent;
      return Stream.fromIterable([': heartbeat', 'data: Partial', done('Finish your bicycle project.')]);
    });
    expect(text, 'Finish your bicycle project.');
    final decoded = jsonDecode(body!) as Map;
    expect(decoded['device_tools'], isEmpty);
    expect(decoded['text'], contains('> I build bicycles.'));
    expect(decoded['text'], isNot(contains('Base a brief answer')),
        reason: 'chat history contains user-facing question and quotes, not helper instructions');
    expect(decoded['text'], startsWith('What should I focus on this week?'));
  });
  for (final frame in [
    'error:402:{}',
    'error: {"error":"quota_exceeded","message":"quota_exceeded"}',
    'unrecognized frame',
    'data: Partial'
  ]) {
    test('payoff does not accept quota/errors/malformed/partial-only frame $frame', () async {
      await expectLater(askGuidedPayoff('Question', ['Saved'], stream: (_) => Stream.value(frame)), throwsStateError);
    });
  }
  test('server timeout frame preserves timeout fallback classification', () async {
    await expectLater(
        askGuidedPayoff('Question', ['Saved'],
            stream: (_) => Stream.value('error: {"error":"timeout","message":"timeout"}')),
        throwsA(isA<ChatStreamException>().having((e) => e.kind, 'kind', ChatStreamFailureClass.timeout)));
  });
  test('payoff cancels a silent stream at its total deadline', () async {
    var cancelled = false;
    final source = StreamController<String>(onCancel: () => cancelled = true);
    await expectLater(
        askGuidedPayoff('Question', ['Saved'], stream: (_) => source.stream, timeout: const Duration(milliseconds: 2)),
        throwsA(isA<TimeoutException>()));
    await Future<void>.delayed(Duration.zero);
    expect(cancelled, isTrue);
    await source.close();
  });
}
