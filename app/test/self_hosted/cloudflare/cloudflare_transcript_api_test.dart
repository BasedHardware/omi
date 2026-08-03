import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_api.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_configuration.dart';
import 'package:omi/self_hosted/cloudflare/cloudflare_transcript_models.dart';

void main() {
  const token = 'test-token-that-must-not-appear-in-errors';
  const configuration = CloudflareTranscriptConfiguration(
    workerUrl: 'https://worker.example.test/base/',
    token: token,
  );
  Matcher isNonSecretApiException() => predicate(
        (Object error) => error is CloudflareTranscriptApiException && !error.message.contains(token),
        'a non-secret CloudflareTranscriptApiException',
      );

  test('invalid Worker configuration stays disabled and does not invoke HTTP', () async {
    var requestCount = 0;
    const invalidConfiguration = CloudflareTranscriptConfiguration(
      workerUrl: 'http://worker.example.test',
      token: token,
    );
    final api = CloudflareTranscriptHttpApi(
      configuration: invalidConfiguration,
      client: MockClient((_) async {
        requestCount += 1;
        return http.Response('{}', 200);
      }),
    );

    expect(api.enabled, isFalse);
    expect(await api.listSessions(), isEmpty);
    expect(requestCount, 0);
  });

  test('lists every cursor page with bearer authorization', () async {
    final requests = <http.Request>[];
    final client = MockClient((request) async {
      requests.add(request);
      if (request.url.queryParameters['cursor'] == null) {
        return http.Response('{"sessions":[{"id":"one","status":"ready"}],"next_cursor":"page-2"}', 200);
      }
      return http.Response('{"sessions":[{"id":"two","status":"ready"}]}', 200);
    });
    final api = CloudflareTranscriptHttpApi(configuration: configuration, client: client);

    final sessions = await api.listSessions(limit: 20);

    expect(sessions.map((session) => session.id), ['one', 'two']);
    expect(requests.map((request) => request.url.toString()), [
      'https://worker.example.test/base/v1/transcript-sessions?limit=20',
      'https://worker.example.test/base/v1/transcript-sessions?limit=20&cursor=page-2',
    ]);
    expect(requests.first.headers['authorization'], 'Bearer $token');
  });

  test('does not follow Worker redirects and reports the 3xx response safely', () async {
    http.Request? capturedRequest;
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((request) async {
        capturedRequest = request;
        return http.Response('', 302, headers: {'location': 'https://redirect.example.test/leak'});
      }),
    );

    await expectLater(
      api.listSessions(),
      throwsA(
        predicate(
          (Object error) =>
              error is CloudflareTranscriptApiException &&
              error.message == 'Worker request failed with HTTP 302.' &&
              !error.message.contains(token),
        ),
      ),
    );
    final request = capturedRequest;
    expect(request, isNotNull);
    expect(request!.method, 'GET');
    expect(request.followRedirects, isFalse);
    expect(request.maxRedirects, 0);
  });

  test('maps the Worker list fixture transcript_char_count and keeps the legacy fallback explicit', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient(
        (_) async => http.Response(
          '{"sessions":['
          '{"id":"worker-canonical","status":"transcribed","transcript_char_count":42},'
          '{"id":"legacy-fallback","status":"ready","character_count":7}'
          ']}',
          200,
        ),
      ),
    );

    final sessions = await api.listSessions();

    expect(sessions.map((session) => session.characterCount), [42, 7]);
  });

  test('rejects a non-object session in the Worker list response', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) async => http.Response('{"sessions":["not-a-session"]}', 200)),
    );

    await expectLater(api.listSessions(), throwsA(isA<CloudflareTranscriptApiException>()));
  });

  test('rejects a Worker list session without an id', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) async => http.Response('{"sessions":[{"status":"ready"}]}', 200)),
    );

    await expectLater(api.listSessions(), throwsA(isA<CloudflareTranscriptApiException>()));
  });

  test('rejects malformed JSON from the Worker list fixture without exposing the token', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) async => http.Response('{not-valid-json', 200)),
    );

    await expectLater(api.listSessions(), throwsA(isNonSecretApiException()));
  });

  test('rejects a Worker list fixture without top-level sessions', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) async => http.Response('{}', 200)),
    );

    await expectLater(api.listSessions(), throwsA(isNonSecretApiException()));
  });

  test('rejects a Worker list fixture with a repeated cursor', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) async => http.Response('{"sessions":[],"next_cursor":"again"}', 200)),
    );

    await expectLater(api.listSessions(), throwsA(isNonSecretApiException()));
  });

  test('sorts transcript chunks by sequence', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient(
        (_) async => http.Response(
          '{"session":{"id":"session/one","status":"ready"},"chunks":['
          '{"sequence":2,"text":"second"},{"sequence":1,"text":"first"}]}',
          200,
        ),
      ),
    );

    final transcript = await api.getTranscript('session/one');

    expect(transcript.fullText, 'first\nsecond');
  });

  test('accepts only JSON integers for transcript chunk sequence values', () async {
    for (final invalidSequence in <String>['"1"', 'null', '1.5', 'true']) {
      final api = CloudflareTranscriptHttpApi(
        configuration: configuration,
        client: MockClient(
          (_) async => http.Response(
            '{"session":{"id":"session-1"},"chunks":[{"sequence":$invalidSequence,"text":"chunk"}]}',
            200,
          ),
        ),
      );

      await expectLater(api.getTranscript('session-1'), throwsA(isA<CloudflareTranscriptApiException>()));
    }
  });

  test('chunk model rejects non-integer JSON sequence values', () {
    for (final invalidSequence in <Object?>['1', null, 1.5, true]) {
      expect(
        () => CloudflareTranscriptChunk.fromJson({'sequence': invalidSequence, 'text': 'chunk'}),
        throwsA(isA<CloudflareTranscriptApiException>()),
      );
    }
  });

  test('rejects a non-object transcript chunk in the Worker detail response', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient(
        (_) async => http.Response('{"session":{"id":"session-1"},"chunks":["not-a-chunk"]}', 200),
      ),
    );

    await expectLater(api.getTranscript('session-1'), throwsA(isA<CloudflareTranscriptApiException>()));
  });

  test('rejects a malformed transcript chunk in the Worker detail response', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient(
        (_) async => http.Response('{"session":{"id":"session-1"},"chunks":[{"sequence":1}]}', 200),
      ),
    );

    await expectLater(api.getTranscript('session-1'), throwsA(isA<CloudflareTranscriptApiException>()));
  });

  test('rejects a Worker detail fixture without top-level chunks', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) async => http.Response('{"session":{"id":"session-1"}}', 200)),
    );

    await expectLater(api.getTranscript('session-1'), throwsA(isNonSecretApiException()));
  });

  test('refuses non-loopback HTTP Worker URLs', () {
    const configuration = CloudflareTranscriptConfiguration(workerUrl: 'http://worker.example.test', token: token);

    expect(() => configuration.baseUri, throwsA(isA<CloudflareTranscriptConfigurationException>()));
  });

  test('refuses credentials and query values embedded in the Worker URL', () {
    const configuration = CloudflareTranscriptConfiguration(
      workerUrl: 'https://credential@worker.example.test/?token=not-allowed',
      token: token,
    );

    expect(() => configuration.baseUri, throwsA(isA<CloudflareTranscriptConfigurationException>()));
  });

  test('Worker failures and timeouts do not expose the bearer token', () async {
    final failingApi = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) async => http.Response('not relevant', 401)),
    );
    final timeoutApi = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) => Completer<http.Response>().future),
      timeout: Duration.zero,
    );

    await expectLater(
      failingApi.listSessions(),
      throwsA(predicate((Object error) => !error.toString().contains(token))),
    );
    await expectLater(
      timeoutApi.listSessions(),
      throwsA(predicate((Object error) => !error.toString().contains(token))),
    );
  });

  test('preserves known Cloudflare errors without replacing their safe message', () async {
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) async => http.Response('not relevant', 404)),
    );

    await expectLater(
      api.listSessions(),
      throwsA(
        predicate(
          (Object error) =>
              error is CloudflareTranscriptApiException && error.message == 'Worker request failed with HTTP 404.',
        ),
      ),
    );
  });

  test('preserves injected Cloudflare errors without replacing their safe message', () async {
    const knownMessage = 'known safe domain error';
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient((_) async => throw const CloudflareTranscriptApiException(knownMessage)),
    );

    await expectLater(
      api.listSessions(),
      throwsA(
        predicate(
          (Object error) => error is CloudflareTranscriptApiException && error.message == knownMessage,
        ),
      ),
    );
  });

  test('wraps ClientException values in a fixed safe Cloudflare error', () async {
    const sensitiveSentinel = 'token-url-request-response-secret';
    final api = CloudflareTranscriptHttpApi(
      configuration: configuration,
      client: MockClient(
        (request) async => throw http.ClientException(
          'transport failure $sensitiveSentinel $token ${request.url}',
          request.url,
        ),
      ),
    );

    await expectLater(
      api.listSessions(),
      throwsA(
        predicate(
          (Object error) =>
              error is CloudflareTranscriptApiException &&
              error.message == 'Worker request failed.' &&
              !error.message.contains(sensitiveSentinel) &&
              !error.message.contains(token) &&
              !error.message.contains('worker.example.test'),
        ),
      ),
    );
  });
}
