import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:omi_integration/omi_integration.dart';
import 'package:test/test.dart';

void main() {
  test('parses typed responses and sends bearer auth', () async {
    final responses = <http.Response>[
      http.Response(jsonEncode({'memories': []}), 200),
      http.Response(jsonEncode({'conversations': []}), 200),
    ];
    final requests = <http.Request>[];
    final mock = MockClient((request) async {
      requests.add(request);
      return responses.removeAt(0);
    });
    final client = OmiIntegrationClient(apiKey: 'key-1', appId: 'app-9', httpClient: mock);

    final memories = await client.listMemories(uid: 'user-2');
    final conversations = await client.listConversations(uid: 'user-2');

    expect(memories, isA<MemoriesResponse>());
    expect(conversations, isA<ConversationsResponse>());
    expect(requests.first.url.path, '/v2/integrations/app-9/memories');
    expect(requests.first.headers['authorization'], 'Bearer key-1');
  });

  test('preserves repeated list query params', () async {
    late http.Request seen;
    final mock = MockClient((request) async {
      seen = request;
      return http.Response(jsonEncode({'conversations': []}), 200);
    });
    final client = OmiIntegrationClient(apiKey: 'test-key', appId: 'app-123', httpClient: mock);
    await client.listConversations(uid: 'user-1', statuses: ['active', 'closed', 'pending']);
    // Verify repeated statuses params in the URL (not collapsed to single value).
    // Uri.queryParametersAll preserves repeated keys.
    final statusesParam = seen.url.queryParametersAll['statuses'];
    expect(statusesParam, isNotNull);
    expect(statusesParam, hasLength(3));
    expect(statusesParam, containsAll(['active', 'closed', 'pending']));
    client.close();
  });

  test('throws on non-2xx', () async {
    final mock = MockClient((request) async {
      return http.Response(jsonEncode({'detail': 'nope'}), 401);
    });
    final client = OmiIntegrationClient(apiKey: 'test-key', appId: 'app-123', httpClient: mock);
    expect(() => client.listMemories(uid: 'user-1'), throwsA(isA<OmiIntegrationException>()));
    client.close();
  });
}
