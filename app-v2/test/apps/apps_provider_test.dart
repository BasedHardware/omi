import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:nooto_v2/apps/apps_provider.dart';
import 'package:nooto_v2/services/api_client.dart';

ApiClient _client(MockClient mock) => ApiClient(
      httpClient: mock,
      getIdToken: ({bool forceRefresh = false}) async => 'tok',
      signOut: () async {},
      baseUrl: 'https://example.test/',
    );

Map<String, dynamic> _sampleResponse() => {
      'groups': [
        {
          'capability': {'id': 'popular', 'title': 'Popular'},
          'data': [
            {
              'id': 'a1',
              'name': 'Alpha',
              'description': 'First app',
              'image': 'https://x/a1.png',
              'enabled': true,
              'installs': 42,
              'capabilities': ['chat'],
            },
            {
              'id': 'a2',
              'name': 'Beta',
              'description': 'Second app',
              'image': '',
              'enabled': false,
              'installs': 7,
              'capabilities': const [],
            },
          ],
        },
        {
          'capability': {'id': 'integrations', 'title': 'Integrations'},
          'data': [
            {
              'id': 'jira',
              'name': 'Jira',
              'description': 'Sync tickets',
              'image': 'https://x/jira.png',
              'enabled': false,
              'installs': 12,
              'capabilities': ['integration'],
            },
          ],
        },
        {
          // Empty groups should be dropped — backend can include them.
          'capability': {'id': 'empty', 'title': 'Empty'},
          'data': const [],
        },
      ],
      'meta': {'capabilities': const [], 'groupCount': 2, 'limit': 20, 'offset': 0},
    };

void main() {
  test('load() hydrates groups, drops empty groups', () async {
    final mock = MockClient((req) async {
      expect(req.url.path, '/v2/apps');
      return http.Response(jsonEncode(_sampleResponse()), 200);
    });
    final provider = AppsProvider(client: _client(mock));

    expect(provider.hasFetched, isFalse);
    await provider.load();

    expect(provider.hasFetched, isTrue);
    expect(provider.groups, hasLength(2));
    expect(provider.groups[0].title, 'Popular');
    expect(provider.groups[0].apps, hasLength(2));
    expect(provider.groups[0].apps[0].name, 'Alpha');
    expect(provider.groups[0].apps[0].installs, 42);
    expect(provider.groups[0].apps[0].enabled, isTrue);
    expect(provider.groups[1].title, 'Integrations');
    expect(provider.groups[1].apps.first.name, 'Jira');
    expect(provider.error, isNull);
  });

  test('load() is idempotent — second call no-ops without force', () async {
    var hits = 0;
    final mock = MockClient((req) async {
      hits += 1;
      return http.Response(jsonEncode(_sampleResponse()), 200);
    });
    final provider = AppsProvider(client: _client(mock));

    await provider.load();
    await provider.load();
    await provider.load();

    expect(hits, 1);
  });

  test('load(force: true) re-fetches', () async {
    var hits = 0;
    final mock = MockClient((req) async {
      hits += 1;
      return http.Response(jsonEncode(_sampleResponse()), 200);
    });
    final provider = AppsProvider(client: _client(mock));

    await provider.load();
    await provider.load(force: true);

    expect(hits, 2);
  });

  test('load() captures error and leaves groups empty on 500', () async {
    final mock = MockClient((req) async => http.Response('boom', 500));
    final provider = AppsProvider(client: _client(mock));

    await provider.load();

    expect(provider.error, isNotNull);
    expect(provider.groups, isEmpty);
    // hasFetched stays false so a subsequent load() retries.
    expect(provider.hasFetched, isFalse);
  });
}
