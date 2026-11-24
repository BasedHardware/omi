// Home paging must survive refreshes: a newest-page re-read neither discards an older page in
// flight nor restarts paging at page two, and the periodic v3 re-read asks only for recent rows.
import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';

final newest = DateTime.utc(2026, 11, 18, 12);

ServerConversation row(int i, {String? title}) {
  final start = newest.subtract(Duration(minutes: i * 3));
  return ServerConversation(
      id: 'c$i',
      createdAt: start,
      startedAt: start,
      finishedAt: start.add(const Duration(minutes: 2)),
      structured: Structured(title ?? 'Fixture $i', 'Summary'));
}

http.Response page(Iterable<ServerConversation> rows, {String? cursor, bool more = true}) =>
    http.Response(jsonEncode([for (final c in rows) c.toJson()]), 200, headers: {
      'x-omi-conversation-page-size': '${rows.length}',
      'x-omi-has-more': '$more',
      if (cursor != null) 'x-omi-next-cursor': cursor,
    });

List<ServerConversation> rows(int from, int to) => [for (var i = from; i < to; i++) row(i)];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
    await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
  });

  ConversationProvider providerFor(Future<http.Response> Function(Uri) serve, List<Uri> requests) {
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) {
          final uri = Uri.parse(request.url);
          requests.add(uri);
          return serve(uri);
        });
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
    addTearDown(provider.dispose);
    return provider;
  }

  Future<http.Response> threePages(Uri uri) async => switch (uri.queryParameters['cursor']) {
        null => page(rows(0, 50), cursor: 'k1'),
        'k1' => page(rows(50, 100), cursor: 'k2'),
        _ => page(rows(100, 120), more: false),
      };

  test('a full re-read of the newest page keeps the deeper paging position', () async {
    final requests = <Uri>[];
    final provider = providerFor(threePages, requests);
    expect(await provider.fetchConversations(), isTrue);
    expect(await provider.getMoreConversationsFromServer(), isTrue);
    expect(provider.conversations, hasLength(100));

    // The periodic re-read (or a capture event) reads the newest page again.
    expect(await provider.fetchConversations(), isTrue);
    expect(provider.conversations, hasLength(100), reason: 'older rows stay on screen');

    expect(await provider.getMoreConversationsFromServer(), isTrue);
    expect(requests.last.queryParameters['cursor'], 'k2', reason: 'the next page, not page two again');
    expect(provider.conversations, hasLength(120));
    expect(provider.hasMoreConversations, isFalse);
  });

  test('a filter change still restarts paging from its own first page', () async {
    final requests = <Uri>[];
    final provider = providerFor(threePages, requests);
    await provider.fetchConversations();
    await provider.getMoreConversationsFromServer();
    provider.showStarredOnly = true;
    await provider.fetchConversations();
    await provider.getMoreConversationsFromServer();
    expect(requests.last.queryParameters['cursor'], 'k1');
  });

  test('a refresh waits for an older page in flight instead of throwing it away', () async {
    final requests = <Uri>[];
    final second = Completer<http.Response>();
    final provider = providerFor(
        (uri) => uri.queryParameters['cursor'] == 'k1' ? second.future : Future.value(page(rows(0, 50), cursor: 'k1')),
        requests);
    await provider.fetchConversations();

    final more = provider.getMoreConversationsFromServer();
    final refresh = provider.fetchConversations();
    await Future<void>.delayed(Duration.zero);
    expect(requests, hasLength(2), reason: 'the refresh has not been sent while the older page is in flight');

    second.complete(page(rows(50, 100), cursor: 'k2'));
    expect(await more, isTrue, reason: 'the older page is applied, not discarded');
    expect(await refresh, isTrue);
    expect(requests, hasLength(3));
    expect(provider.conversations, hasLength(100));
    await provider.getMoreConversationsFromServer();
    expect(requests.last.queryParameters['cursor'], 'k2');
  });

  test('the recent-rows refresh reads only its window and leaves paging alone', () async {
    final requests = <Uri>[];
    final since = newest.subtract(const Duration(minutes: 10));
    final provider = providerFor((uri) async {
      if (uri.queryParameters.containsKey('start_date')) {
        // Rows 0..3 fall in the window. Row 1 is gone (hidden or deleted); row 2 has a new title.
        return page([row(0), row(2, title: 'Retitled'), row(3)], more: false);
      }
      return threePages(uri);
    }, requests);
    await provider.fetchConversations();
    await provider.getMoreConversationsFromServer();
    expect(provider.conversations, hasLength(100));

    await provider.refreshRecentConversations(since);
    final bounded = requests.last.queryParameters;
    expect(DateTime.parse(bounded['start_date']!).toUtc(), since);
    expect(bounded.containsKey('cursor'), isFalse);

    final ids = provider.conversations.map((c) => c.id).toSet();
    expect(ids.contains('c1'), isFalse, reason: 'absent inside the window is gone');
    expect(ids.contains('c4'), isTrue, reason: 'rows before the window are untouched');
    expect(provider.conversations, hasLength(99));
    expect(provider.conversations.firstWhere((c) => c.id == 'c2').structured.title, 'Retitled');

    await provider.getMoreConversationsFromServer();
    expect(requests.last.queryParameters['cursor'], 'k2', reason: 'paging continues where it was');
  });

  test('with a filter active the recent-rows refresh falls back to the full read', () async {
    final requests = <Uri>[];
    final provider = providerFor(threePages, requests);
    provider.showStarredOnly = true;
    await provider.refreshRecentConversations(newest.subtract(const Duration(minutes: 10)));
    expect(requests.single.queryParameters.containsKey('start_date'), isFalse);
    expect(requests.single.queryParameters['starred'], 'true');
  });

  test('a bounded refresh on a fresh provider does not become the paging position', () async {
    final requests = <Uri>[];
    final provider = providerFor((uri) async {
      if (uri.queryParameters.containsKey('start_date')) return page(rows(0, 3), cursor: 'bounded', more: false);
      return threePages(uri);
    }, requests);
    await provider.refreshRecentConversations(newest.subtract(const Duration(minutes: 10)));
    expect(provider.hasMoreConversations, isFalse);
    await provider.fetchConversations();
    await provider.getMoreConversationsFromServer();
    expect(requests.last.queryParameters['cursor'], 'k1');
  });

  group('which rows drive the periodic re-read', () {
    ServerConversation pending(String id, DateTime lastActivity, String tile) => ServerConversation.fromJson({
          ...row(0).toJson(),
          'id': id,
          'created_at': lastActivity.subtract(const Duration(minutes: 30)).toIso8601String(),
          'started_at': lastActivity.subtract(const Duration(minutes: 30)).toIso8601String(),
          'finished_at': lastActivity.toIso8601String(),
          'kind': 'conversation',
          'home_hidden': false,
          'tile_state': tile,
        });
    final now = DateTime.utc(2026, 11, 24, 3);

    test('only a row pending for under an hour counts', () {
      final fresh = pending('fresh', now.subtract(const Duration(minutes: 5)), 'transcribing');
      final stuck = pending('stuck', now.subtract(const Duration(hours: 30)), 'writing');
      final done = pending('done', now.subtract(const Duration(minutes: 5)), 'ready');
      expect(ConversationsV3Provider.recentlyMidPipeline([fresh, stuck, done], now).map((c) => c.id), ['fresh']);
      expect(ConversationsV3Provider.recentlyMidPipeline([stuck, done], now), isEmpty);
      // The unbounded check still sees the stuck row; it no longer drives the tick.
      expect(ConversationsV3Provider.anyMidPipeline([stuck]), isTrue);
    });

    test('the window starts an hour back, earlier for an older changing row, never before a day', () {
      const margin = Duration(minutes: 2);
      expect(
          ConversationsV3Provider.recentRefreshSince(const [], now), now.subtract(const Duration(hours: 1) + margin));
      final recent = now.subtract(const Duration(minutes: 5));
      expect(
          ConversationsV3Provider.recentRefreshSince([recent], now), now.subtract(const Duration(hours: 1) + margin));
      final long = now.subtract(const Duration(hours: 3));
      expect(ConversationsV3Provider.recentRefreshSince([recent, long], now), long.subtract(margin));
      final ancient = now.subtract(const Duration(days: 9));
      expect(
          ConversationsV3Provider.recentRefreshSince([ancient], now), now.subtract(const Duration(days: 1) + margin));
    });
  });
}
