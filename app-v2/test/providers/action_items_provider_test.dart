import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:nooto_v2/providers/action_items_provider.dart';
import 'package:nooto_v2/services/api_client.dart';

ApiClient _client(MockClient mock) => ApiClient(
      httpClient: mock,
      getIdToken: ({bool forceRefresh = false}) async => 'tok',
      signOut: () async {},
      baseUrl: 'https://example.test/',
    );

Map<String, dynamic> _itemJson(String id, String desc, {bool completed = false}) => {
      'id': id,
      'description': desc,
      'completed': completed,
      'created_at': '2026-04-30T12:00:00Z',
    };

void main() {
  group('ActionItemsProvider.fetchAll', () {
    test('hydrates items on 200', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/v1/action-items');
        expect(req.url.queryParameters['completed'], 'false');
        return http.Response(
          jsonEncode({
            'action_items': [
              _itemJson('a', 'first'),
              _itemJson('b', 'second'),
            ],
            'has_more': false,
          }),
          200,
        );
      });
      final p = ActionItemsProvider(client: _client(mock));

      await p.fetchAll();

      expect(p.ready, isTrue);
      expect(p.items.length, 2);
      expect(p.items.first.id, 'a');
      expect(p.items.first.description, 'first');
    });

    test('empty list still flips ready', () async {
      final mock = MockClient((req) async => http.Response(
            jsonEncode({'action_items': [], 'has_more': false}),
            200,
          ));
      final p = ActionItemsProvider(client: _client(mock));

      await p.fetchAll();

      expect(p.ready, isTrue);
      expect(p.items, isEmpty);
    });

    test('500 leaves items empty but still ready', () async {
      final mock = MockClient((req) async => http.Response('boom', 500));
      final p = ActionItemsProvider(client: _client(mock));

      await p.fetchAll();

      expect(p.ready, isTrue);
      expect(p.items, isEmpty);
    });

    test('concurrent fetchAll is a no-op while loading', () async {
      var requestCount = 0;
      final mock = MockClient((req) async {
        requestCount += 1;
        await Future.delayed(const Duration(milliseconds: 30));
        return http.Response(
          jsonEncode({'action_items': [], 'has_more': false}),
          200,
        );
      });
      final p = ActionItemsProvider(client: _client(mock));

      await Future.wait([p.fetchAll(), p.fetchAll(), p.fetchAll()]);

      expect(requestCount, 1);
    });
  });

  group('ActionItemsProvider.incompleteTop3', () {
    test('returns at most 3 incomplete items, newest first', () async {
      final mock = MockClient((req) async => http.Response(
            jsonEncode({
              'action_items': [
                {'id': '1', 'description': 'oldest', 'completed': false, 'created_at': '2026-01-01T00:00:00Z'},
                {'id': '2', 'description': 'middle', 'completed': false, 'created_at': '2026-03-01T00:00:00Z'},
                {'id': '3', 'description': 'newest', 'completed': false, 'created_at': '2026-04-01T00:00:00Z'},
                {'id': '4', 'description': 'fourth', 'completed': false, 'created_at': '2025-12-01T00:00:00Z'},
                {'id': '5', 'description': 'done already', 'completed': true, 'created_at': '2026-04-15T00:00:00Z'},
              ],
              'has_more': false,
            }),
            200,
          ));
      final p = ActionItemsProvider(client: _client(mock));

      await p.fetchAll();
      final top = p.incompleteTop3;

      expect(top.length, 3);
      expect(top.map((i) => i.id).toList(), ['3', '2', '1']);
    });
  });

  group('ActionItemsProvider.complete', () {
    test('optimistically marks completed and confirms on 200', () async {
      var patchCalled = false;
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'action_items': [_itemJson('x', 'thing')],
              'has_more': false,
            }),
            200,
          );
        }
        patchCalled = true;
        expect(req.method, 'PATCH');
        expect(req.url.path, '/v1/action-items/x/completed');
        return http.Response(jsonEncode({'id': 'x', 'description': 'thing', 'completed': true}), 200);
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      final ok = await p.complete('x');

      expect(ok, isTrue);
      expect(patchCalled, isTrue);
      expect(p.items.first.completed, isTrue);
    });

    test('rolls back on server failure', () async {
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'action_items': [_itemJson('y', 'rollback me')],
              'has_more': false,
            }),
            200,
          );
        }
        return http.Response('boom', 500);
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      final ok = await p.complete('y');

      expect(ok, isFalse);
      expect(p.items.first.completed, isFalse);
    });

    test('returns false for unknown id without server call', () async {
      var requestCount = 0;
      final mock = MockClient((req) async {
        requestCount += 1;
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({'action_items': [], 'has_more': false}),
            200,
          );
        }
        fail('PATCH should not run for unknown id');
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      final ok = await p.complete('does-not-exist');

      expect(ok, isFalse);
      expect(requestCount, 1);
    });
  });
}
