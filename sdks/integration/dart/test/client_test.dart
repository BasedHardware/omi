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

  test('serializes typed post bodies', () async {
    late http.Request seen;
    final mock = MockClient((request) async {
      seen = request;
      return http.Response(
        jsonEncode({'conversations': [], 'current_page': 1, 'per_page': 20, 'total_pages': 1}),
        200,
      );
    });
    final client = OmiIntegrationClient(apiKey: 'test-key', appId: 'app-123', httpClient: mock);
    await client.searchConversations(uid: 'user-1', body: const SearchRequest(query: 'project alpha'));
    expect(jsonDecode(seen.body), {'query': 'project alpha'});
    client.close();
  });

  test('accepts JSON numbers for integer and double fields', () {
    final pageJson = <String, dynamic>{
      'conversations': [],
      'current_page': 1.0,
      'per_page': 20.0,
      'total_pages': 1.0,
    };
    final locationJson = <String, dynamic>{'latitude': 40, 'longitude': -74};
    final page = SearchConversationsResponse.fromJson(pageJson);
    final location = ConversationItemGeolocation.fromJson(locationJson);

    expect(page.currentPage, 1);
    expect(page.perPage, 20);
    expect(location.latitude, 40.0);
    expect(location.longitude, -74.0);
  });
}
