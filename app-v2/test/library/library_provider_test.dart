import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:nooto_v2/library/library_provider.dart';
import 'package:nooto_v2/library/memory_model.dart';
import 'package:nooto_v2/services/api_client.dart';

ApiClient _client(MockClient mock) => ApiClient(
      httpClient: mock,
      getIdToken: ({bool forceRefresh = false}) async => 'tok',
      signOut: () async {},
      baseUrl: 'https://example.test/',
    );

Map<String, dynamic> _memory({
  String id = 'm1',
  String content = 'Sample memory',
  String? category = 'interesting',
  bool manuallyAdded = false,
  bool isLocked = false,
  String? conversationId = 'conv-1',
  String createdAt = '2026-04-30T10:00:00Z',
  String updatedAt = '2026-04-30T10:00:00Z',
}) {
  final m = <String, dynamic>{
    'id': id,
    'content': content,
    'manually_added': manuallyAdded,
    'is_locked': isLocked,
    'conversation_id': conversationId,
    'created_at': createdAt,
    'updated_at': updatedAt,
  };
  if (category != null) m['category'] = category;
  return m;
}

void main() {
  group('MemoryBucket.fromCategory', () {
    test('maps each known raw category to the right bucket', () {
      expect(MemoryBucket.fromCategory('interesting'), MemoryBucket.interesting);
      expect(MemoryBucket.fromCategory('habits'), MemoryBucket.habits);
      expect(MemoryBucket.fromCategory('manual'), MemoryBucket.yourNotes);
      // Iterate the exposed const set so the test can't drift from the switch.
      for (final raw in lifeContextCategories) {
        expect(
          MemoryBucket.fromCategory(raw),
          MemoryBucket.lifeContext,
          reason: '$raw should map to LIFE CONTEXT',
        );
      }
    });

    test('REGRESSION: unknown/null/empty category falls back to YOUR NOTES', () {
      // Memories must NEVER be silently dropped when the backend ships a
      // new category we don't know about.
      expect(MemoryBucket.fromCategory(null), MemoryBucket.yourNotes);
      expect(MemoryBucket.fromCategory(''), MemoryBucket.yourNotes);
      expect(MemoryBucket.fromCategory('unknown_xyz'), MemoryBucket.yourNotes);
      expect(MemoryBucket.fromCategory('future_category'), MemoryBucket.yourNotes);
    });
  });

  group('LibraryProvider.load', () {
    test('hydrates groups in 4 buckets, drops empty buckets, sorts by updatedAt desc', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/v3/memories');
        return http.Response(
          jsonEncode([
            _memory(id: 'a', content: 'Loves chess', category: 'interesting',
                updatedAt: '2026-04-29T10:00:00Z'),
            _memory(id: 'b', content: 'Works at TogoDynamics', category: 'work',
                updatedAt: '2026-04-30T10:00:00Z'),
            _memory(id: 'c', content: 'Drinks coffee daily', category: 'habits',
                updatedAt: '2026-04-28T10:00:00Z'),
            _memory(id: 'd', content: 'Manual note', category: 'manual',
                manuallyAdded: true, updatedAt: '2026-04-27T10:00:00Z'),
            _memory(id: 'e', content: 'Reads sci-fi', category: 'hobbies',
                updatedAt: '2026-04-25T10:00:00Z'),
          ]),
          200,
        );
      });
      final provider = LibraryProvider(client: _client(mock));

      await provider.load();

      expect(provider.hasFetched, isTrue);
      expect(provider.error, isNull);
      final groups = provider.groups;
      expect(groups, hasLength(4));
      expect(groups[0].bucket, MemoryBucket.interesting);
      expect(groups[0].items, hasLength(1));
      expect(groups[1].bucket, MemoryBucket.lifeContext);
      // Two LIFE CONTEXT entries, sorted by updatedAt desc (b before e)
      expect(groups[1].items.map((m) => m.id), ['b', 'e']);
      expect(groups[2].bucket, MemoryBucket.habits);
      expect(groups[3].bucket, MemoryBucket.yourNotes);
    });

    test('REGRESSION: memory with unknown category appears in YOUR NOTES, not dropped', () async {
      final mock = MockClient((req) async => http.Response(
            jsonEncode([
              _memory(id: 'mystery', content: 'Backend shipped a new category', category: 'culinary'),
            ]),
            200,
          ));
      final provider = LibraryProvider(client: _client(mock));

      await provider.load();

      final groups = provider.groups;
      expect(groups, hasLength(1));
      expect(groups.first.bucket, MemoryBucket.yourNotes);
      expect(groups.first.items.first.id, 'mystery');
    });

    test('REGRESSION: memory with null category appears in YOUR NOTES, not dropped', () async {
      final mock = MockClient((req) async => http.Response(
            jsonEncode([
              _memory(id: 'no-cat', content: 'Has no category', category: null),
            ]),
            200,
          ));
      final provider = LibraryProvider(client: _client(mock));

      await provider.load();

      expect(provider.groups, hasLength(1));
      expect(provider.groups.first.bucket, MemoryBucket.yourNotes);
    });

    test('idempotent — second load() no-ops without force', () async {
      var hits = 0;
      final mock = MockClient((req) async {
        hits += 1;
        return http.Response(jsonEncode([_memory()]), 200);
      });
      final provider = LibraryProvider(client: _client(mock));

      await provider.load();
      await provider.load();
      await provider.load();

      expect(hits, 1);
    });

    test('load(force: true) re-fetches', () async {
      var hits = 0;
      final mock = MockClient((req) async {
        hits += 1;
        return http.Response(jsonEncode([_memory()]), 200);
      });
      final provider = LibraryProvider(client: _client(mock));

      await provider.load();
      await provider.load(force: true);

      expect(hits, 2);
    });

    test('captures error on 500, leaves groups empty, hasFetched stays false', () async {
      final mock = MockClient((req) async => http.Response('boom', 500));
      final provider = LibraryProvider(client: _client(mock));

      await provider.load();

      expect(provider.error, isNotNull);
      expect(provider.isEmpty, isTrue);
      expect(provider.hasFetched, isFalse);
    });
  });

  group('LibraryProvider.delete', () {
    test('optimistically removes locally and posts DELETE', () async {
      String? capturedPath;
      String? capturedMethod;
      final mock = MockClient((req) async {
        if (req.method == 'GET' && req.url.path == '/v3/memories') {
          return http.Response(
            jsonEncode([_memory(id: 'm1'), _memory(id: 'm2')]),
            200,
          );
        }
        if (req.method == 'DELETE') {
          capturedPath = req.url.path;
          capturedMethod = req.method;
          return http.Response('{"status":"ok"}', 200);
        }
        return http.Response('not found', 404);
      });
      final provider = LibraryProvider(client: _client(mock));
      await provider.load();
      expect(provider.groups.expand((g) => g.items).length, 2);

      final ok = await provider.delete('m1');

      expect(ok, isTrue);
      expect(capturedMethod, 'DELETE');
      expect(capturedPath, '/v3/memories/m1');
      expect(provider.groups.expand((g) => g.items).map((m) => m.id), ['m2']);
    });

    test('rolls back local state on non-2xx and surfaces error', () async {
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(jsonEncode([_memory(id: 'm1')]), 200);
        }
        if (req.method == 'DELETE') {
          return http.Response('boom', 500);
        }
        return http.Response('not found', 404);
      });
      final provider = LibraryProvider(client: _client(mock));
      await provider.load();

      final ok = await provider.delete('m1');

      expect(ok, isFalse);
      expect(provider.error, isNotNull);
      // Memory came back.
      expect(provider.groups.expand((g) => g.items).map((m) => m.id), ['m1']);
    });

    test('no-ops when id is absent', () async {
      var hitDelete = 0;
      final mock = MockClient((req) async {
        if (req.method == 'GET') {
          return http.Response(jsonEncode([_memory(id: 'm1')]), 200);
        }
        if (req.method == 'DELETE') {
          hitDelete += 1;
          return http.Response('{"status":"ok"}', 200);
        }
        return http.Response('not found', 404);
      });
      final provider = LibraryProvider(client: _client(mock));
      await provider.load();

      final ok = await provider.delete('does-not-exist');

      expect(ok, isFalse);
      expect(hitDelete, 0);
    });
  });
}
