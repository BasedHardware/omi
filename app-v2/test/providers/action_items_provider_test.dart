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
            'action_items': [_itemJson('a', 'first'), _itemJson('b', 'second')],
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
      final mock = MockClient((req) async => http.Response(jsonEncode({'action_items': [], 'has_more': false}), 200));
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
        return http.Response(jsonEncode({'action_items': [], 'has_more': false}), 200);
      });
      final p = ActionItemsProvider(client: _client(mock));

      await Future.wait([p.fetchAll(), p.fetchAll(), p.fetchAll()]);

      expect(requestCount, 1);
    });
  });

  group('ActionItemsProvider.incompleteTop3', () {
    test('returns at most 3 incomplete items, newest first', () async {
      final mock = MockClient(
        (req) async => http.Response(
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
        ),
      );
      final p = ActionItemsProvider(client: _client(mock));

      await p.fetchAll();
      final top = p.incompleteTop3;

      expect(top.length, 3);
      expect(top.map((i) => i.id).toList(), ['3', '2', '1']);
    });
  });

  group('ExternalSource.fromJson', () {
    test('returns null when map is null', () {
      expect(ExternalSource.fromJson(null), isNull);
    });

    test('returns null when source missing or empty', () {
      expect(ExternalSource.fromJson({'external_id': 'X-1', 'url': 'https://a/x'}), isNull);
      expect(ExternalSource.fromJson({'source': '', 'external_id': 'X-1', 'url': 'https://a/x'}), isNull);
    });

    test('returns null when external_id missing or empty', () {
      expect(ExternalSource.fromJson({'source': 'jira', 'url': 'https://a/x'}), isNull);
      expect(ExternalSource.fromJson({'source': 'jira', 'external_id': '   ', 'url': 'https://a/x'}), isNull);
    });

    test('returns null when url missing or empty', () {
      expect(ExternalSource.fromJson({'source': 'jira', 'external_id': 'X-1'}), isNull);
      expect(ExternalSource.fromJson({'source': 'jira', 'external_id': 'X-1', 'url': ''}), isNull);
    });

    test('returns instance with trimmed values for valid input', () {
      final ext = ExternalSource.fromJson({
        'source': '  jira  ',
        'external_id': '  PROJ-123  ',
        'url': '  https://x/PROJ-123  ',
      });
      expect(ext, isNotNull);
      expect(ext!.source, 'jira');
      expect(ext.externalId, 'PROJ-123');
      expect(ext.url, 'https://x/PROJ-123');
    });
  });

  group('ActionItem.fromJson with externalSource', () {
    test('parses external_source when present', () {
      final item = ActionItem.fromJson({
        'id': 'a',
        'description': 'fix bug',
        'completed': false,
        'external_source': {'source': 'jira', 'external_id': 'PROJ-123', 'url': 'https://x/PROJ-123'},
      });
      expect(item.externalSource, isNotNull);
      expect(item.externalSource!.source, 'jira');
      expect(item.externalSource!.externalId, 'PROJ-123');
      expect(item.externalSource!.url, 'https://x/PROJ-123');
    });

    test('externalSource null when external_source missing', () {
      final item = ActionItem.fromJson({'id': 'a', 'description': 'transcript thing', 'completed': false});
      expect(item.externalSource, isNull);
    });

    test('externalSource null when external_source is JSON null', () {
      final item = ActionItem.fromJson({
        'id': 'a',
        'description': 'transcript thing',
        'completed': false,
        'external_source': null,
      });
      expect(item.externalSource, isNull);
    });

    test('externalSource null when partial fields collapse to invalid', () {
      final item = ActionItem.fromJson({
        'id': 'a',
        'description': 'half-broken integration',
        'completed': false,
        'external_source': {
          'source': 'jira',
          // url missing → invalid
          'external_id': 'PROJ-9',
        },
      });
      expect(item.externalSource, isNull);
    });

    test('copyWith preserves externalSource', () {
      final item = ActionItem.fromJson({
        'id': 'a',
        'description': 'fix bug',
        'completed': false,
        'external_source': {'source': 'jira', 'external_id': 'PROJ-1', 'url': 'https://x/PROJ-1'},
      });
      final copied = item.copyWith(completed: true);
      expect(copied.completed, isTrue);
      expect(copied.externalSource, isNotNull);
      expect(copied.externalSource!.externalId, 'PROJ-1');
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
          return http.Response(jsonEncode({'action_items': [], 'has_more': false}), 200);
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

  group('ExternalSource metadata', () {
    test('parses metadata map round-trip', () {
      final ext = ExternalSource.fromJson({
        'source': 'jira',
        'external_id': 'PROJ-1',
        'url': 'https://x/PROJ-1',
        'metadata': {'status': 'In Review', 'status_type': 'indeterminate', 'project_key': 'PROJ', 'priority': 'P2'},
      });
      expect(ext, isNotNull);
      expect(ext!.jiraStatus, 'In Review');
      expect(ext.jiraStatusType, 'indeterminate');
      expect(ext.jiraProjectKey, 'PROJ');
      expect(ext.jiraPriority, 'P2');
    });

    test('all metadata getters return null when metadata missing', () {
      final ext = ExternalSource.fromJson({'source': 'jira', 'external_id': 'PROJ-1', 'url': 'https://x/PROJ-1'});
      expect(ext, isNotNull);
      expect(ext!.metadata, isNull);
      expect(ext.jiraStatus, isNull);
      expect(ext.jiraStatusType, isNull);
      expect(ext.jiraProjectKey, isNull);
      expect(ext.jiraPriority, isNull);
      expect(ext.jiraStatusChangedAt, isNull);
      expect(ext.daysAtStatus, isNull);
    });

    test('metadata accepts extra unknown keys without failing', () {
      final ext = ExternalSource.fromJson({
        'source': 'jira',
        'external_id': 'PROJ-1',
        'url': 'https://x/PROJ-1',
        'metadata': {'status': 'Done', 'unknown_field': 'whatever'},
      });
      expect(ext, isNotNull);
      expect(ext!.jiraStatus, 'Done');
    });

    test('daysAtStatus computes from ISO8601 status_changed_at', () {
      final fourDaysAgo = DateTime.now().subtract(const Duration(days: 4, hours: 2));
      final ext = ExternalSource.fromJson({
        'source': 'jira',
        'external_id': 'PROJ-1',
        'url': 'https://x/PROJ-1',
        'metadata': {'status_changed_at': fourDaysAgo.toUtc().toIso8601String()},
      });
      expect(ext!.daysAtStatus, 4);
    });

    test('daysAtStatus is null when status_changed_at missing', () {
      final ext = ExternalSource.fromJson({
        'source': 'jira',
        'external_id': 'PROJ-1',
        'url': 'https://x/PROJ-1',
        'metadata': {'status': 'Done'},
      });
      expect(ext!.daysAtStatus, isNull);
    });

    test('daysAtStatus is null on unparseable date', () {
      final ext = ExternalSource.fromJson({
        'source': 'jira',
        'external_id': 'PROJ-1',
        'url': 'https://x/PROJ-1',
        'metadata': {'status_changed_at': 'not a date'},
      });
      expect(ext!.daysAtStatus, isNull);
      expect(ext.jiraStatusChangedAt, isNull);
    });

    test('copyWith preserves metadata and lets caller swap it', () {
      final ext = ExternalSource.fromJson({
        'source': 'jira',
        'external_id': 'PROJ-1',
        'url': 'https://x/PROJ-1',
        'metadata': {'status': 'To Do'},
      });
      final updated = ext!.copyWith(metadata: {'status': 'Done'});
      expect(updated.jiraStatus, 'Done');
      expect(updated.externalId, 'PROJ-1'); // other fields preserved
    });
  });

  group('ActionItemsProvider.transition', () {
    Map<String, dynamic> jiraItemJson(String id, {String status = 'To Do', String statusType = 'todo'}) => {
      'id': id,
      'description': 'jira thing',
      'completed': false,
      'created_at': '2026-04-30T12:00:00Z',
      'external_source': {
        'source': 'jira',
        'external_id': 'PROJ-1',
        'url': 'https://x/PROJ-1',
        'metadata': {'status': status, 'status_type': statusType, 'project_key': 'PROJ'},
      },
    };

    test('optimistic update + server confirm on 200', () async {
      var transitionCalled = false;
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'action_items': [jiraItemJson('a')],
              'has_more': false,
            }),
            200,
          );
        }
        if (req.url.path == '/v1/integrations/jira/transition') {
          transitionCalled = true;
          expect(req.method, 'POST');
          final body = jsonDecode(req.body);
          expect(body['action_item_id'], 'a');
          expect(body['to_status'], 'In Progress');
          return http.Response(jsonEncode(jiraItemJson('a', status: 'In Progress', statusType: 'indeterminate')), 200);
        }
        return http.Response('not found', 404);
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      final ok = await p.transition('a', toStatus: 'In Progress');

      expect(ok, isTrue);
      expect(transitionCalled, isTrue);
      expect(p.items.first.externalSource!.jiraStatus, 'In Progress');
      expect(p.items.first.externalSource!.jiraStatusType, 'indeterminate');
      expect(p.lastActionError, isNull);
    });

    test('rolls back and stamps lastActionError on 403 two_way_sync_disabled', () async {
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'action_items': [jiraItemJson('a')],
              'has_more': false,
            }),
            200,
          );
        }
        return http.Response(jsonEncode({'detail': 'two_way_sync_disabled'}), 403);
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      final ok = await p.transition('a', toStatus: 'Done');

      expect(ok, isFalse);
      expect(p.items.first.externalSource!.jiraStatus, 'To Do'); // rolled back
      expect(p.lastActionError, 'two_way_sync_disabled');
    });

    test('rolls back with generic key on 502 Jira-side error', () async {
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'action_items': [jiraItemJson('a')],
              'has_more': false,
            }),
            200,
          );
        }
        return http.Response(jsonEncode({'detail': 'jira upstream broken'}), 502);
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      final ok = await p.transition('a', toStatus: 'Done');

      expect(ok, isFalse);
      expect(p.items.first.externalSource!.jiraStatus, 'To Do');
      expect(p.lastActionError, 'jira_error');
    });

    test('returns false for unknown id and for non-jira items', () async {
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'action_items': [_itemJson('transcript-1', 'no source')],
              'has_more': false,
            }),
            200,
          );
        }
        fail('POST should not run for unknown id or non-jira');
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      expect(await p.transition('does-not-exist', toStatus: 'Done'), isFalse);
      expect(await p.transition('transcript-1', toStatus: 'Done'), isFalse);
    });
  });

  group('ActionItemsProvider.snooze', () {
    Map<String, dynamic> jiraItemJson(String id, {String? dueAt}) => {
      'id': id,
      'description': 'jira thing',
      'completed': false,
      'created_at': '2026-04-30T12:00:00Z',
      if (dueAt != null) 'due_at': dueAt,
      'external_source': {'source': 'jira', 'external_id': 'PROJ-1', 'url': 'https://x/PROJ-1'},
    };

    test('optimistic update of dueAt + server confirm', () async {
      final until = DateTime.utc(2030, 5, 15, 12);
      var snoozeCalled = false;
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'action_items': [jiraItemJson('a')],
              'has_more': false,
            }),
            200,
          );
        }
        if (req.url.path == '/v1/integrations/jira/snooze') {
          snoozeCalled = true;
          final body = jsonDecode(req.body);
          expect(body['action_item_id'], 'a');
          expect(body['snooze_until'], until.toUtc().toIso8601String());
          return http.Response(jsonEncode(jiraItemJson('a', dueAt: until.toIso8601String())), 200);
        }
        return http.Response('not found', 404);
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      final ok = await p.snooze('a', snoozeUntil: until);

      expect(ok, isTrue);
      expect(snoozeCalled, isTrue);
      expect(p.items.first.dueAt, isNotNull);
      expect(p.lastActionError, isNull);
    });

    test('rolls back on 403 two_way_sync_disabled', () async {
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'action_items': [jiraItemJson('a')],
              'has_more': false,
            }),
            200,
          );
        }
        return http.Response(jsonEncode({'detail': 'two_way_sync_disabled'}), 403);
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      final originalDue = p.items.first.dueAt;
      final ok = await p.snooze('a', snoozeUntil: DateTime.now().add(const Duration(days: 1)));

      expect(ok, isFalse);
      expect(p.items.first.dueAt, originalDue);
      expect(p.lastActionError, 'two_way_sync_disabled');
    });

    test('returns false for non-jira items', () async {
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(
            jsonEncode({
              'action_items': [_itemJson('t', 'transcript')],
              'has_more': false,
            }),
            200,
          );
        }
        fail('POST should not run for non-jira items');
      });
      final p = ActionItemsProvider(client: _client(mock));
      await p.fetchAll();

      final ok = await p.snooze('t', snoozeUntil: DateTime.now().add(const Duration(days: 1)));
      expect(ok, isFalse);
    });
  });
}
