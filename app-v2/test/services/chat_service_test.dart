import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:nooto_v2/services/api_client.dart';
import 'package:nooto_v2/services/chat_service.dart';

ApiClient _client(MockClient mock) => ApiClient(
      httpClient: mock,
      getIdToken: ({bool forceRefresh = false}) async => 'tok',
      signOut: () async {},
      baseUrl: 'https://example.test/',
    );

http.StreamedResponse _streamed(List<String> lines) {
  final body = lines.map((l) => '$l\n').join();
  return http.StreamedResponse(
    Stream.fromIterable([utf8.encode(body)]),
    200,
  );
}

void main() {
  group('ChatService.fetchBrief', () {
    test('accumulates data: chunks until done:', () async {
      final mock = MockClient.streaming((req, body) async {
        return _streamed([
          'data: Yesterday you said ',
          'data: you would email John. ',
          'data: Today, three meetings.',
          'done: ${base64.encode(utf8.encode("{}"))}',
        ]);
      });
      final svc = ChatService(client: _client(mock));

      final body = await svc.fetchBrief(prompt: 'hi');

      expect(
        body,
        'Yesterday you said you would email John. Today, three meetings.',
      );
    });

    test('decodes __CRLF__ as newline', () async {
      final mock = MockClient.streaming((req, body) async {
        return _streamed([
          'data: line one__CRLF__line two',
          'done: ${base64.encode(utf8.encode("{}"))}',
        ]);
      });
      final svc = ChatService(client: _client(mock));

      final body = await svc.fetchBrief(prompt: 'hi');

      expect(body, 'line one\nline two');
    });

    test('ignores think: and message: lines', () async {
      final mock = MockClient.streaming((req, body) async {
        return _streamed([
          'think: pondering',
          'data: visible',
          'message: ${base64.encode(utf8.encode("{}"))}',
          'done: ${base64.encode(utf8.encode("{}"))}',
        ]);
      });
      final svc = ChatService(client: _client(mock));

      final body = await svc.fetchBrief(prompt: 'hi');

      expect(body, 'visible');
    });

    test('completes on stream close even without done:', () async {
      final mock = MockClient.streaming((req, body) async {
        return _streamed([
          'data: partial result',
        ]);
      });
      final svc = ChatService(client: _client(mock));

      final body = await svc.fetchBrief(prompt: 'hi');

      expect(body, 'partial result');
    });

    test('throws TimeoutException when stream stalls', () async {
      final controller = StreamController<List<int>>();
      addTearDown(() => controller.close());
      final mock = MockClient.streaming((req, body) async {
        return http.StreamedResponse(controller.stream, 200);
      });
      final svc = ChatService(client: _client(mock));

      await expectLater(
        svc.fetchBrief(
          prompt: 'hi',
          timeout: const Duration(milliseconds: 50),
        ),
        throwsA(isA<TimeoutException>()),
      );
    });

    test('hits /v2/messages with the prompt body', () async {
      String? capturedPath;
      String? capturedBody;
      final mock = MockClient.streaming((req, body) async {
        capturedPath = req.url.toString();
        capturedBody = utf8.decode(await body.expand((b) => b).toList());
        return _streamed(['data: ok', 'done: ${base64.encode(utf8.encode("{}"))}']);
      });
      final svc = ChatService(client: _client(mock));

      await svc.fetchBrief(prompt: 'brief me');

      expect(capturedPath, contains('v2/messages'));
      expect(jsonDecode(capturedBody!)['text'], 'brief me');
    });
  });
}
