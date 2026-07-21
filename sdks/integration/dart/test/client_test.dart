import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:omi_integration/omi_integration.dart';
import 'package:test/test.dart';

void main() {
  test('sends bearer auth and app_id path', () async {
    late http.Request seen;
    final mock = MockClient((request) async {
      seen = request;
      return http.Response(jsonEncode({'memories': []}), 200);
    });
    final client = OmiIntegrationClient(
      apiKey: 'test-key',
      appId: 'app-123',
      httpClient: mock,
    );
    final body = await client.listMemories(uid: 'user-1', limit: 10);
    expect(body, isA<Map>());
    expect(seen.headers['Authorization'], 'Bearer test-key');
    expect(seen.url.path, '/v2/integrations/app-123/memories');
    expect(seen.url.queryParameters['uid'], 'user-1');
    client.close();
  });

  test('throws on non-2xx', () async {
    final mock = MockClient((request) async {
      return http.Response(jsonEncode({'detail': 'nope'}), 401);
    });
    final client = OmiIntegrationClient(
      apiKey: 'test-key',
      appId: 'app-123',
      httpClient: mock,
    );
    expect(
      () => client.listMemories(uid: 'user-1'),
      throwsA(isA<OmiIntegrationException>()),
    );
    client.close();
  });
}
