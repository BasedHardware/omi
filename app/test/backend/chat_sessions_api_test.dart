import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/chat_session.dart';

void main() {
  test('successful empty history is different from network or malformed history', () async {
    for (final (status, body, success) in [
      (200, '[]', true),
      (500, '[]', false),
      (200, '{}', false),
      (200, '[{"id":7}]', false)
    ]) {
      final api = ChatSessionsApi(baseUrl: 'https://example.invalid/', send: (_) async => http.Response(body, status));
      expect(await api.list(),
          success ? isA<ApiSuccess<List<ChatSessionSummary>>>() : isA<ApiFailure<List<ChatSessionSummary>>>());
    }
  });
  test('partial history preserves valid rows, rejected count and one bounded fallback event', () async {
    var fallbacks = 0;
    final api = ChatSessionsApi(
      baseUrl: 'https://example.invalid/',
      fallback: (_) => fallbacks++,
      send: (_) async => http.Response(
          jsonEncode([
            {'id': 'kept', 'title': 'Thread', 'updated_at': '2026-09-29T01:00:00Z'},
            {'id': 7},
          ]),
          200),
    );
    final result = await api.list() as ApiSuccess<List<ChatSessionSummary>>;
    expect(result.data.single.id, 'kept');
    expect(result.rejectedRows, 1);
    expect(fallbacks, 1);
  });

  test('pagination and explicit message target are encoded, never routed to current chat', () async {
    final requests = <ApiRequest>[];
    final api = ChatSessionsApi(
        baseUrl: 'https://example.invalid/',
        send: (request) async {
          requests.add(request);
          return http.Response('[]', 200);
        });
    await api.list(offset: 50);
    await api.messages('old & chat', offset: 100);
    expect(Uri.parse(requests.first.url).queryParameters, {'offset': '50', 'limit': '50'});
    expect(Uri.parse(requests.last.url).queryParameters,
        {'chat_session_id': 'old & chat', 'offset': '100', 'limit': '100'});
  });
  test('creation decodes server identity and malformed identity fails closed', () async {
    for (final valid in [true, false]) {
      final api = ChatSessionsApi(
          baseUrl: 'https://example.invalid/',
          send: (request) async {
            expect(request.method, 'POST');
            expect(jsonDecode(request.body), isEmpty);
            return http.Response(jsonEncode({'id': valid ? 'new' : '', 'created_at': '2026-09-29T01:00:00Z'}), 200);
          });
      final result = await api.create();
      expect(result, valid ? isA<ApiSuccess<ChatSessionSummary>>() : isA<ApiFailure<ChatSessionSummary>>());
    }
  });
  test('deletion encodes path identity and reports server failure', () async {
    final api = ChatSessionsApi(
        baseUrl: 'https://example.invalid/',
        send: (request) async {
          expect(Uri.parse(request.url).pathSegments.last, 'a/b');
          expect(request.method, 'DELETE');
          return http.Response('{}', 503);
        });
    expect(await api.delete('a/b'), isA<ApiFailure<void>>());
  });
}
