import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:nooto_v2/library/conversation_model.dart';
import 'package:nooto_v2/library/conversations_provider.dart';
import 'package:nooto_v2/services/api_client.dart';

ApiClient _client(MockClient mock) => ApiClient(
      httpClient: mock,
      getIdToken: ({bool forceRefresh = false}) async => 'tok',
      signOut: () async {},
      baseUrl: 'https://example.test/',
    );

Map<String, dynamic> _conv({
  String id = 'c1',
  String title = 'Sample meeting',
  String overview = 'overview text',
  String createdAt = '2026-04-30T10:00:00Z',
  bool starred = false,
  int segmentCount = 3,
  int actionItemCount = 1,
  String? category = 'work',
}) {
  return <String, dynamic>{
    'id': id,
    'created_at': createdAt,
    'starred': starred,
    'structured': {
      'title': title,
      'overview': overview,
      'category': category,
      'action_items': [for (var i = 0; i < actionItemCount; i++) {'description': 'do $i', 'completed': false}],
    },
    'transcript_segments': [
      for (var i = 0; i < segmentCount; i++) {'text': 'turn $i', 'speaker': 'SPEAKER_$i', 'is_user': i == 0},
    ],
  };
}

void main() {
  group('ConversationItem.fromJson', () {
    test('falls back to "Untitled conversation" when title is empty', () {
      final c = ConversationItem.fromJson({'id': 'x', 'structured': {'title': '', 'overview': ''}});
      expect(c.title, 'Untitled conversation');
    });

    test('parses createdAt to local DateTime, null on missing', () {
      final c = ConversationItem.fromJson({'id': 'x', 'structured': {}});
      expect(c.createdAt, isNull);
      final c2 = ConversationItem.fromJson(_conv(createdAt: '2026-04-30T10:00:00Z'));
      expect(c2.createdAt, isNotNull);
    });

    test('counts segments and action items', () {
      final c = ConversationItem.fromJson(_conv(segmentCount: 5, actionItemCount: 2));
      expect(c.segmentCount, 5);
      expect(c.actionItemCount, 2);
    });
  });

  group('conversationDateBucket', () {
    final now = DateTime(2026, 4, 30, 12);
    test('today/yesterday/this week/this month/month name', () {
      expect(conversationDateBucket(now, now: now), 'Today');
      expect(conversationDateBucket(now.subtract(const Duration(days: 1)), now: now), 'Yesterday');
      expect(conversationDateBucket(now.subtract(const Duration(days: 4)), now: now), 'This Week');
      expect(conversationDateBucket(now.subtract(const Duration(days: 14)), now: now), 'This Month');
      // 60 days back, same year -> month name
      final back60 = now.subtract(const Duration(days: 60));
      expect(conversationDateBucket(back60, now: now), isNot('This Month'));
    });

    test('null date -> Earlier', () {
      expect(conversationDateBucket(null, now: now), 'Earlier');
    });
  });

  group('ConversationsProvider.load', () {
    test('hydrates flat list sorted desc, groups by date bucket', () async {
      final mock = MockClient((req) async {
        expect(req.url.path, '/v1/conversations');
        return http.Response(
          jsonEncode([
            _conv(id: 'a', createdAt: '2026-04-30T10:00:00Z', title: 'Today A'),
            _conv(id: 'b', createdAt: '2026-04-29T10:00:00Z', title: 'Yesterday B'),
            _conv(id: 'c', createdAt: '2026-04-30T18:00:00Z', title: 'Today C (newer)'),
          ]),
          200,
        );
      });
      final p = ConversationsProvider(client: _client(mock));

      await p.load();

      expect(p.hasFetched, isTrue);
      expect(p.error, isNull);
      // Top-level sort: c (today 18:00) before a (today 10:00) before b (yesterday)
      expect(p.items.map((c) => c.id).toList(), ['c', 'a', 'b']);
    });

    test('idempotent — second call no-ops without force', () async {
      var hits = 0;
      final mock = MockClient((req) async {
        hits += 1;
        return http.Response(jsonEncode([_conv()]), 200);
      });
      final p = ConversationsProvider(client: _client(mock));
      await p.load();
      await p.load();
      await p.load();
      expect(hits, 1);
    });

    test('load(force: true) re-fetches', () async {
      var hits = 0;
      final mock = MockClient((req) async {
        hits += 1;
        return http.Response(jsonEncode([_conv()]), 200);
      });
      final p = ConversationsProvider(client: _client(mock));
      await p.load();
      await p.load(force: true);
      expect(hits, 2);
    });

    test('captures error on 500, isEmpty stays true, hasFetched false', () async {
      final mock = MockClient((req) async => http.Response('boom', 500));
      final p = ConversationsProvider(client: _client(mock));
      await p.load();
      expect(p.error, isNotNull);
      expect(p.isEmpty, isTrue);
      expect(p.hasFetched, isFalse);
    });
  });

  group('ConversationsProvider.delete', () {
    test('optimistic remove + DELETE /v1/conversations/:id', () async {
      String? capturedPath;
      String? capturedMethod;
      final mock = MockClient((req) async {
        if (req.method == 'GET' && req.url.path == '/v1/conversations') {
          return http.Response(jsonEncode([_conv(id: 'c1'), _conv(id: 'c2')]), 200);
        }
        if (req.method == 'DELETE') {
          capturedPath = req.url.path;
          capturedMethod = req.method;
          return http.Response('', 204);
        }
        return http.Response('not found', 404);
      });
      final p = ConversationsProvider(client: _client(mock));
      await p.load();
      expect(p.items.length, 2);

      final ok = await p.delete('c1');

      expect(ok, isTrue);
      expect(capturedMethod, 'DELETE');
      expect(capturedPath, '/v1/conversations/c1');
      expect(p.items.map((c) => c.id), ['c2']);
    });

    test('rolls back on non-2xx and surfaces error', () async {
      final mock = MockClient((req) async {
        if (req.method == 'GET') return http.Response(jsonEncode([_conv(id: 'c1')]), 200);
        if (req.method == 'DELETE') return http.Response('boom', 500);
        return http.Response('not found', 404);
      });
      final p = ConversationsProvider(client: _client(mock));
      await p.load();

      final ok = await p.delete('c1');

      expect(ok, isFalse);
      expect(p.error, isNotNull);
      expect(p.items.map((c) => c.id), ['c1']);
    });
  });

  group('ConversationsProvider.byId', () {
    test('returns the cached item or null', () async {
      final mock = MockClient((req) async => http.Response(jsonEncode([_conv(id: 'wanted')]), 200));
      final p = ConversationsProvider(client: _client(mock));
      await p.load();
      expect(p.byId('wanted')?.id, 'wanted');
      expect(p.byId('missing'), isNull);
    });
  });
}
