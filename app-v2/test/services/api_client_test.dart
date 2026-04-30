import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:nooto_v2/services/api_client.dart';

void main() {
  group('ApiClient.get', () {
    test('attaches Bearer token and returns 200 body', () async {
      String? capturedAuth;
      final mock = MockClient((req) async {
        capturedAuth = req.headers['Authorization'];
        return http.Response('{"ok":true}', 200);
      });
      final client = ApiClient(
        httpClient: mock,
        getIdToken: ({bool forceRefresh = false}) async => 'tok-1',
        signOut: () async {},
        baseUrl: 'https://example.test/',
      );

      final res = await client.get('v1/ping');

      expect(res.statusCode, 200);
      expect(jsonDecode(res.body)['ok'], true);
      expect(capturedAuth, 'Bearer tok-1');
    });

    test('omits Authorization header when token is null', () async {
      String? capturedAuth;
      final mock = MockClient((req) async {
        capturedAuth = req.headers['Authorization'];
        return http.Response('{}', 200);
      });
      final client = ApiClient(
        httpClient: mock,
        getIdToken: ({bool forceRefresh = false}) async => null,
        signOut: () async {},
        baseUrl: 'https://example.test/',
      );

      await client.get('v1/ping');

      expect(capturedAuth, isNull);
    });
  });

  group('ApiClient.post', () {
    test('encodes body to JSON and sends Content-Type', () async {
      String? capturedBody;
      String? capturedContentType;
      final mock = MockClient((req) async {
        capturedBody = req.body;
        capturedContentType = req.headers['Content-Type'];
        return http.Response('{}', 200);
      });
      final client = ApiClient(
        httpClient: mock,
        getIdToken: ({bool forceRefresh = false}) async => 'tok',
        signOut: () async {},
        baseUrl: 'https://example.test/',
      );

      await client.post('v1/items', body: {'a': 1});

      expect(capturedBody, '{"a":1}');
      expect(capturedContentType, 'application/json');
    });
  });

  group('ApiClient 401 retry', () {
    test('refreshes token and retries once on 401', () async {
      // Mirrors Firebase's internal cache: forceRefresh:true rotates the token
      // that subsequent non-force getIdToken() calls return.
      var current = 'tok-old';
      var refreshCalls = 0;
      var requestCount = 0;
      final seenAuth = <String>[];

      final mock = MockClient((req) async {
        requestCount += 1;
        seenAuth.add(req.headers['Authorization'] ?? '');
        if (requestCount == 1) return http.Response('', 401);
        return http.Response('{"ok":true}', 200);
      });

      final client = ApiClient(
        httpClient: mock,
        getIdToken: ({bool forceRefresh = false}) async {
          if (forceRefresh) {
            refreshCalls += 1;
            current = 'tok-new';
          }
          return current;
        },
        signOut: () async {
          fail('signOut should not run when refresh succeeds');
        },
        baseUrl: 'https://example.test/',
      );

      final res = await client.get('v1/ping');

      expect(requestCount, 2);
      expect(refreshCalls, 1);
      expect(res.statusCode, 200);
      expect(seenAuth, ['Bearer tok-old', 'Bearer tok-new']);
    });

    test('signs out when refresh returns null', () async {
      var signOutCalled = false;
      final mock = MockClient((req) async => http.Response('', 401));
      final client = ApiClient(
        httpClient: mock,
        getIdToken: ({bool forceRefresh = false}) async => forceRefresh ? null : 'tok',
        signOut: () async {
          signOutCalled = true;
        },
        baseUrl: 'https://example.test/',
      );

      final res = await client.get('v1/ping');

      expect(res.statusCode, 401);
      expect(signOutCalled, isTrue);
    });

    test('signs out when retry also returns 401', () async {
      var signOutCalled = false;
      final mock = MockClient((req) async => http.Response('', 401));
      final client = ApiClient(
        httpClient: mock,
        getIdToken: ({bool forceRefresh = false}) async => 'tok',
        signOut: () async {
          signOutCalled = true;
        },
        baseUrl: 'https://example.test/',
      );

      final res = await client.get('v1/ping');

      expect(res.statusCode, 401);
      expect(signOutCalled, isTrue);
    });
  });

  group('ApiClient.stream', () {
    test('yields response chunks on 200', () async {
      final mock = MockClient.streaming((req, body) async {
        return http.StreamedResponse(
          Stream.fromIterable([utf8.encode('chunk-1'), utf8.encode('chunk-2')]),
          200,
        );
      });
      final client = ApiClient(
        httpClient: mock,
        getIdToken: ({bool forceRefresh = false}) async => 'tok',
        signOut: () async {},
        baseUrl: 'https://example.test/',
      );

      final stream = await client.stream('v2/messages', body: {'text': 'hi'});
      final collected = <String>[];
      await for (final chunk in stream) {
        collected.add(utf8.decode(chunk));
      }

      expect(collected, ['chunk-1', 'chunk-2']);
    });

    test('throws ClientException on 401 stream', () async {
      final mock = MockClient.streaming((req, body) async {
        return http.StreamedResponse(const Stream.empty(), 401);
      });
      final client = ApiClient(
        httpClient: mock,
        getIdToken: ({bool forceRefresh = false}) async => 'tok',
        signOut: () async {},
        baseUrl: 'https://example.test/',
      );

      expect(
        () => client.stream('v2/messages', body: {'text': 'hi'}),
        throwsA(isA<http.ClientException>()),
      );
    });

    test('throws on 5xx stream', () async {
      final mock = MockClient.streaming((req, body) async {
        return http.StreamedResponse(
          Stream.fromIterable([utf8.encode('boom')]),
          500,
        );
      });
      final client = ApiClient(
        httpClient: mock,
        getIdToken: ({bool forceRefresh = false}) async => 'tok',
        signOut: () async {},
        baseUrl: 'https://example.test/',
      );

      expect(
        () => client.stream('v2/messages', body: {'text': 'hi'}),
        throwsA(isA<http.ClientException>()),
      );
    });
  });
}
