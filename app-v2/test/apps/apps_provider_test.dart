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

Map<String, dynamic> _sampleCatalog() => {
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

/// Routes both /v2/apps and /v1/apps/enabled. enabledList is the user's
/// installed-set returned for /v1/apps/enabled.
MockClient _routedMock({List<String> enabledList = const []}) {
  return MockClient((req) async {
    if (req.url.path == '/v2/apps') {
      return http.Response(jsonEncode(_sampleCatalog()), 200);
    }
    if (req.url.path == '/v1/apps/enabled') {
      return http.Response(jsonEncode(enabledList), 200);
    }
    if (req.url.path == '/v1/apps/enable') {
      return http.Response('{"status":"ok"}', 200);
    }
    if (req.url.path == '/v1/apps/disable') {
      return http.Response('{"status":"ok"}', 200);
    }
    return http.Response('not found', 404);
  });
}

void main() {
  test('load() hydrates groups, drops empty, marks enabled from /v1/apps/enabled', () async {
    final provider = AppsProvider(client: _client(_routedMock(enabledList: ['a1', 'jira'])));

    await provider.load();

    expect(provider.groups, hasLength(2));
    expect(provider.isEnabled('a1'), isTrue);
    expect(provider.isEnabled('a2'), isFalse);
    expect(provider.isEnabled('jira'), isTrue);
    expect(provider.error, isNull);
  });

  test('load() is idempotent — second call no-ops without force', () async {
    var hits = 0;
    final mock = MockClient((req) async {
      hits += 1;
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      return http.Response('[]', 200);
    });
    final provider = AppsProvider(client: _client(mock));

    await provider.load();
    await provider.load();
    await provider.load();

    // 2 hits per load (catalog + enabled); 1 load total => 2 hits.
    expect(hits, 2);
  });

  test('load() captures error on 500', () async {
    final mock = MockClient((req) async => http.Response('boom', 500));
    final provider = AppsProvider(client: _client(mock));

    await provider.load();

    expect(provider.error, isNotNull);
    expect(provider.groups, isEmpty);
  });

  test('install() optimistically marks enabled and posts to backend', () async {
    String? capturedPath;
    String? capturedQuery;
    final mock = MockClient((req) async {
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response('[]', 200);
      }
      if (req.url.path == '/v1/apps/enable') {
        capturedPath = req.url.path;
        capturedQuery = req.url.query;
        return http.Response('{"status":"ok"}', 200);
      }
      return http.Response('not found', 404);
    });
    final provider = AppsProvider(client: _client(mock));
    await provider.load();
    expect(provider.isEnabled('a1'), isFalse);

    final ok = await provider.install('a1');

    expect(ok, isTrue);
    expect(capturedPath, '/v1/apps/enable');
    expect(capturedQuery, contains('app_id=a1'));
    expect(provider.isEnabled('a1'), isTrue);
  });

  test('install() rolls back local state on backend error', () async {
    final mock = MockClient((req) async {
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response('[]', 200);
      }
      if (req.url.path == '/v1/apps/enable') {
        return http.Response('boom', 500);
      }
      return http.Response('not found', 404);
    });
    final provider = AppsProvider(client: _client(mock));
    await provider.load();

    final ok = await provider.install('a1');

    expect(ok, isFalse);
    expect(provider.isEnabled('a1'), isFalse);
    expect(provider.error, isNotNull);
  });

  test('uninstall() flips state off and posts disable', () async {
    String? capturedPath;
    final mock = MockClient((req) async {
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response(jsonEncode(['a1']), 200);
      }
      if (req.url.path == '/v1/apps/disable') {
        capturedPath = req.url.path;
        return http.Response('{"status":"ok"}', 200);
      }
      return http.Response('not found', 404);
    });
    final provider = AppsProvider(client: _client(mock));
    await provider.load();
    expect(provider.isEnabled('a1'), isTrue);

    final ok = await provider.uninstall('a1');

    expect(ok, isTrue);
    expect(capturedPath, '/v1/apps/disable');
    expect(provider.isEnabled('a1'), isFalse);
  });

  test('install() no-ops if already installed', () async {
    var hitEnable = 0;
    final mock = MockClient((req) async {
      if (req.url.path == '/v2/apps') {
        return http.Response(jsonEncode(_sampleCatalog()), 200);
      }
      if (req.url.path == '/v1/apps/enabled') {
        return http.Response(jsonEncode(['a1']), 200);
      }
      if (req.url.path == '/v1/apps/enable') {
        hitEnable += 1;
        return http.Response('{"status":"ok"}', 200);
      }
      return http.Response('not found', 404);
    });
    final provider = AppsProvider(client: _client(mock));
    await provider.load();

    final ok = await provider.install('a1');

    expect(ok, isFalse);
    expect(hitEnable, 0);
  });
}
