import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/env/env.dart';

class _Env implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.test/';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Map<String, dynamic> _node(String id, [String? label]) => {'id': id, 'label': label ?? id};
Map<String, dynamic> _page(
        {List<Map<String, dynamic>> nodes = const [], List<Map<String, dynamic>> catalog = const [], String? cursor}) =>
    {
      'nodes': nodes,
      'edges': [],
      'catalog_nodes': catalog,
      'has_more': cursor != null,
      'next_cursor': cursor,
    };
http.Response _ok(Map<String, dynamic> value) => http.Response(jsonEncode(value), 200);

void main() {
  setUpAll(() => Env.init(_Env()));

  test('empty compatibility graph does not hide canonical catalog memories', () async {
    final urls = <String>[];
    final result = await KnowledgeGraphApi.getKnowledgeGraph(apiCaller: (url) async {
      urls.add(url);
      return _ok(url.contains('/canonical')
          ? _page(catalog: [_node('memory:1', 'I enjoy hiking')], cursor: 'next')
          : {'nodes': [], 'edges': []});
    });
    expect(result['nodes'], isEmpty);
    expect(result['edges'], isEmpty);
    expect((result['catalog_nodes'] as List).single['label'], 'I enjoy hiking');
    expect(result['has_more'], true);
    expect(urls.length, 2);
    expect(urls.any((url) => url.contains('rebuild')), false);
  });

  test('a working compatibility graph remains usable, including shared projections', () async {
    final result = await KnowledgeGraphApi.getKnowledgeGraph(
        apiCaller: (url) async => _ok(
              url.contains('/canonical')
                  ? _page(nodes: [_node('a', 'Corrected')])
                  : {
                      'nodes': [_node('a', 'Old'), _node('shared')],
                      'edges': []
                    },
            ));
    expect((result['nodes'] as List).map((n) => n['label']), ['Old', 'shared']);
  });

  for (final status in [null, 401, 403, 504]) {
    test('failed compatibility read $status does not issue a canonical recovery request', () async {
      final urls = <String>[];
      await expectLater(
        KnowledgeGraphApi.getKnowledgeGraph(apiCaller: (url) async {
          urls.add(url);
          return status == null ? null : http.Response('{}', status);
        }),
        status == 401 || status == 403 ? throwsA(isA<KnowledgeGraphSessionChanged>()) : throwsException,
      );
      expect(urls, ['https://api.test/v1/knowledge-graph']);
    });
  }

  test('Load More uses only the signed cursor read and safely encodes it', () async {
    final urls = <String>[];
    final result = await KnowledgeGraphApi.getKnowledgeGraph(
        cursor: 'signed+/=?',
        apiCaller: (url) async {
          urls.add(url);
          expect(Uri.parse(url).queryParameters['cursor'], 'signed+/=?');
          return _ok(_page(nodes: [_node('later')]));
        });
    expect(urls.length, 1);
    expect(result['has_more'], false);
  });

  test('unavailable canonical read and empty legacy view expose a retryable error', () async {
    await expectLater(
        KnowledgeGraphApi.getKnowledgeGraph(
            apiCaller: (url) async => url.contains('/canonical')
                ? http.Response('{"detail":"private diagnostics"}', 503)
                : _ok({'nodes': [], 'edges': []})),
        throwsA(isA<Exception>().having((e) => e.toString(), 'message', isNot(contains('private diagnostics')))));
  });

  test('a single real legacy entity stays visible without canonical recovery', () async {
    final result = await KnowledgeGraphApi.getKnowledgeGraph(
        apiCaller: (url) async => url.contains('/canonical')
            ? http.Response('{}', 503)
            : _ok({
                'nodes': [_node('legacy')],
                'edges': []
              }));
    expect((result['nodes'] as List).single['id'], 'legacy');
  });

  for (final code in [401, 403, 429, 500, 503]) {
    test('canonical $code is not silently converted to legacy success', () async {
      await expectLater(
          KnowledgeGraphApi.getKnowledgeGraph(
              apiCaller: (url) async => url.contains('/canonical')
                  ? http.Response('{}', code)
                  : _ok({
                      'nodes': [_node('user-node')],
                      'edges': []
                    })),
          throwsException);
    });
  }

  test('a session change discards the in-flight response', () async {
    var current = true;
    var requests = 0;
    await expectLater(
        KnowledgeGraphApi.getKnowledgeGraph(
            isCurrent: () => current,
            apiCaller: (url) async {
              requests++;
              current = false;
              return _ok({
                'nodes': [_node('other-account')],
                'edges': []
              });
            }),
        throwsA(isA<KnowledgeGraphSessionChanged>()));
    expect(requests, 1);
  });

  test('missing or repeated next cursor cannot trap Load More in a loop', () async {
    for (final cursor in [null, 'same']) {
      await expectLater(
          KnowledgeGraphApi.getKnowledgeGraph(
              cursor: 'same',
              apiCaller: (_) async => _ok({
                    ..._page(),
                    'has_more': true,
                    'next_cursor': cursor,
                  })),
          throwsFormatException);
    }
  });

  test('page merge deduplicates records and finishes pagination without creating edges', () {
    final first =
        mergeKnowledgeGraphPages({'nodes': [], 'edges': []}, _page(catalog: [_node('memory:1')], cursor: 'next'));
    final last = mergeKnowledgeGraphPages(first, _page(catalog: [_node('memory:1', 'Updated'), _node('memory:2')]));
    expect((last['catalog_nodes'] as List).length, 2);
    expect((last['catalog_nodes'] as List).first['label'], 'Updated');
    expect(last['nodes'], isEmpty);
    expect(last['edges'], isEmpty);
    expect(last['truncated'], false);
  });

  test('positively absent canonical state preserves a genuinely new empty account', () async {
    final result = await KnowledgeGraphApi.getKnowledgeGraph(
        apiCaller: (url) async => url.contains('/canonical')
            ? http.Response('{"detail":"canonical_graph_unavailable"}', 503,
                headers: {'x-omi-knowledge-graph-state': 'unestablished'})
            : _ok({'nodes': [], 'edges': []}));
    expect(result['nodes'], isEmpty);
  });

  test('expired canonical cursor requests a new revision, not a rebuild', () async {
    await expectLater(
        KnowledgeGraphApi.getKnowledgeGraph(
            cursor: 'stale', apiCaller: (_) async => http.Response('{"detail":"invalid_or_stale_cursor"}', 400)),
        throwsA(isA<KnowledgeGraphCursorExpired>()));
  });

  test('page merges reject a different authenticated session', () {
    expect(
        () => mergeKnowledgeGraphPages({
              'nodes': [],
              'edges': [],
              '_owner_generation': 'first:1'
            }, {
              ..._page(catalog: [_node('private')]),
              '_owner_generation': 'second:2'
            }),
        throwsA(isA<KnowledgeGraphSessionChanged>()));
  });

  test('custom backend overrides apply to the next graph read', () async {
    Env.overrideApiBaseUrl('https://custom.test/');
    addTearDown(Env.clearApiBaseUrlOverride);
    await KnowledgeGraphApi.getKnowledgeGraph(
        cursor: 'next',
        apiCaller: (url) async {
          expect(Uri.parse(url).host, 'custom.test');
          return _ok(_page());
        });
  });

  test('a backend change during an await discards the response', () async {
    addTearDown(Env.clearApiBaseUrlOverride);
    await expectLater(
        KnowledgeGraphApi.getKnowledgeGraph(
            cursor: 'next',
            apiCaller: (_) async {
              Env.overrideApiBaseUrl('https://different.test/');
              return _ok(_page(catalog: [_node('private')]));
            }),
        throwsA(isA<KnowledgeGraphSessionChanged>()));
  });

  test('page merges reject a different backend for the same account', () {
    expect(
        () => mergeKnowledgeGraphPages(
            {'nodes': [], 'edges': [], '_owner_generation': 'same:1', '_backend_origin': 'first'},
            {..._page(), '_owner_generation': 'same:1', '_backend_origin': 'second'}),
        throwsA(isA<KnowledgeGraphSessionChanged>()));
  });

  for (final owners in [
    [
      {'id': 'user', 'label': 'user', 'node_type': 'person'}
    ],
    [
      {'id': 'user-node', 'label': 'Me', 'node_type': 'user'}
    ],
    [
      {'id': 'owner-a', 'label': 'John', 'node_type': 'user'},
      {'id': 'user-node', 'label': 'The User', 'node_type': 'person'}
    ],
  ]) {
    test('owner-only view ${owners.map((node) => node['id']).join(',')} recovers the canonical catalog', () async {
      final result = await KnowledgeGraphApi.getKnowledgeGraph(
          apiCaller: (url) async => _ok(url.contains('/canonical')
              ? _page(catalog: [_node('memory:1', 'Saved fact')])
              : {'nodes': owners, 'edges': []}));
      expect(result['nodes'], isEmpty);
      expect((result['catalog_nodes'] as List).single['label'], 'Saved fact');
    });
  }

  for (final ownerId in ['user', 'user-node']) {
    for (final label in ['John', 'Sam Altman', 'Me', 'The User', 'I', 'user']) {
      test('a name-only entity "$label" beside $ownerId cannot trigger owner-only recovery', () async {
        var reads = 0;
        final nodes = [
          {'id': ownerId, 'label': 'user', 'node_type': 'person'},
          {'id': 'distinct-entity', 'label': label, 'node_type': label == 'I' ? 'concept' : 'person'},
        ];
        final edges = [
          {'id': 'e1', 'source_id': ownerId, 'target_id': 'distinct-entity', 'label': 'knows'},
        ];
        final result = await KnowledgeGraphApi.getKnowledgeGraph(apiCaller: (url) async {
          reads++;
          expect(url, isNot(contains('/canonical')));
          return _ok({'nodes': nodes, 'edges': edges});
        });
        expect(reads, 1);
        expect(result['nodes'], nodes);
        expect(result['edges'], edges);
      });
    }
  }
}
