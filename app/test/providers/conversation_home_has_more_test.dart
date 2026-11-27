import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation row(int i) {
  final start = DateTime.utc(2026, 11, 18).subtract(Duration(minutes: i * 3));
  return ServerConversation(
      id: 'c$i',
      createdAt: start,
      startedAt: start,
      finishedAt: start.add(const Duration(minutes: 2)),
      structured: Structured('Fixture $i', 'Summary'));
}

/// One served page: its rows plus the pagination headers the server sends.
typedef Page = ({List<ServerConversation> rows, Map<String, String> headers});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
    await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
  });

  test('page headers parse, and an absent answer falls back to a full page', () {
    final parsed = ConversationPageHeaders.parse({'x-omi-has-more': 'true', 'x-omi-next-cursor': 'abc'});
    expect(parsed.hasMore, isTrue);
    expect(parsed.nextCursor, 'abc');
    const older = ConversationPageHeaders();
    expect(older.more(storageCount: 50, pageSize: 50, truncated: false), isTrue);
    expect(older.more(storageCount: 49, pageSize: 50, truncated: false), isFalse);
    // A page cut short by hidden rows is not the end when the server says so.
    expect(parsed.more(storageCount: 10, pageSize: 50, truncated: false), isTrue);
    expect(
        const ConversationPageHeaders(hasMore: false).more(storageCount: 50, pageSize: 50, truncated: false), isFalse);
    // A budget-cut page: the server's answer decides (it says more only when the page advanced).
    expect(parsed.more(storageCount: 20, pageSize: 50, truncated: true), isTrue);
    expect(const ConversationPageHeaders(hasMore: false).more(storageCount: 0, pageSize: 50, truncated: true), isFalse);
    // An older server: a cut page is never taken for a full one.
    expect(older.more(storageCount: 50, pageSize: 50, truncated: true), isFalse);
  });

  test('a short page the server marks has-more keeps paging, resuming at its cursor', () async {
    // 30 visible rows, then a long hidden run the server could not cross in one page, then more rows.
    final pages = <Page>[
      (
        rows: [for (var i = 0; i < 30; i++) row(i)],
        headers: {'x-omi-conversation-page-size': '542', 'x-omi-has-more': 'true', 'x-omi-next-cursor': 'k1'}
      ),
      (
        rows: [for (var i = 30; i < 40; i++) row(i)],
        headers: {'x-omi-conversation-page-size': '20', 'x-omi-has-more': 'false'}
      ),
    ];
    final requests = <Uri>[];
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          final page = pages[requests.length];
          requests.add(Uri.parse(request.url));
          return http.Response(jsonEncode([for (final c in page.rows) c.toJson()]), 200, headers: page.headers);
        });
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
    addTearDown(provider.dispose);

    expect(await provider.fetchConversations(), isTrue);
    expect(provider.hasMoreConversations, isTrue, reason: 'thirty rows is short, but the server has more');
    expect(await provider.getMoreConversationsFromServer(), isTrue);
    expect(requests.last.queryParameters['offset'], '542');
    expect(requests.last.queryParameters['cursor'], 'k1');
    expect(provider.conversations, hasLength(40));
    expect(provider.hasMoreConversations, isFalse);
  });

  test('an empty truncated page keeps its offset for an explicit retry', () async {
    final requests = <Uri>[];
    var page = 0;
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          requests.add(Uri.parse(request.url));
          page++;
          if (page == 1) {
            return http.Response(jsonEncode([for (var i = 0; i < 50; i++) row(i).toJson()]), 200,
                headers: {'x-omi-conversation-page-size': '50', 'x-omi-has-more': 'true'});
          }
          if (page == 2) {
            return http.Response('[]', 200, headers: {
              'x-omi-conversation-page-size': '0',
              'x-omi-has-more': 'true',
              'x-omi-list-truncated': 'true',
            });
          }
          return http.Response(jsonEncode([row(50).toJson()]), 200,
              headers: {'x-omi-conversation-page-size': '1', 'x-omi-has-more': 'false'});
        });
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
    addTearDown(provider.dispose);

    expect(await provider.fetchConversations(), isTrue);
    expect(provider.conversationServerOffset, 50);
    expect(await provider.getMoreConversationsFromServer(), isFalse);
    expect(provider.loadMoreFailed, isTrue);
    expect(provider.hasMoreConversations, isTrue);
    expect(provider.conversationServerOffset, 50);
    expect(requests.map((request) => request.queryParameters['offset']), ['0', '50']);

    // The failure footer retries only after an explicit action, at the unchanged offset.
    expect(await provider.getMoreConversationsFromServer(), isTrue);
    expect(provider.loadMoreFailed, isFalse);
    expect(requests.last.queryParameters['offset'], '50');
    expect(provider.conversationServerOffset, 51);
    expect(provider.hasMoreConversations, isFalse);
  });

  test('an older server without the headers keeps the full-page rule and sends no cursor', () async {
    final requests = <Uri>[];
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          requests.add(Uri.parse(request.url));
          return http.Response(jsonEncode([for (var i = 0; i < 50; i++) row(i).toJson()]), 200);
        });
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
    addTearDown(provider.dispose);
    expect(await provider.fetchConversations(), isTrue);
    expect(provider.hasMoreConversations, isTrue);
    await provider.getMoreConversationsFromServer();
    expect(requests.last.queryParameters.containsKey('cursor'), isFalse);
    expect(requests.last.queryParameters['offset'], '50');
  });
  test('a refresh advances by the storage count, not the body length', () async {
    final requests = <Uri>[];
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          requests.add(Uri.parse(request.url));
          // Thirty visible rows that consumed 542 storage rows (a hidden run).
          return http.Response(jsonEncode([for (var i = 0; i < 30; i++) row(i).toJson()]), 200,
              headers: {'x-omi-conversation-page-size': '542'});
        });
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
    addTearDown(provider.dispose);
    await provider.forceRefreshConversations();
    expect(provider.hasMoreConversations, isTrue);
    await provider.getMoreConversationsFromServer();
    expect(requests.last.queryParameters['offset'], '542');
  });

  test('a refresh page shortened by hidden rows does not drop older loaded rows', () async {
    var served = 0;
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          served++;
          final rows = served == 1 ? [for (var i = 0; i < 50; i++) row(i)] : [for (var i = 0; i < 30; i++) row(i)];
          final size = served == 1 ? '50' : '542';
          return http.Response(jsonEncode([for (final c in rows) c.toJson()]), 200,
              headers: {'x-omi-conversation-page-size': size});
        });
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
    addTearDown(provider.dispose);
    expect(await provider.fetchConversations(), isTrue);
    expect(provider.conversations, hasLength(50));
    await provider.forceRefreshConversations();
    // The refresh consumed a full page of storage rows, so it covers only down to
    // its oldest visible row; rows older than that stay.
    expect(provider.conversations, hasLength(50));
  });

  test('refresh coverage follows created_at, the order pages are read in', () async {
    // A row created now for a recording that started long ago: newest by created_at, oldest by start.
    final stale = ServerConversation(
        id: 'stale',
        createdAt: DateTime.utc(2026, 11, 18, 1),
        startedAt: DateTime.utc(2026, 11, 1),
        finishedAt: DateTime.utc(2026, 11, 1, 0, 2),
        structured: Structured('Stale', 'Summary'));
    var served = 0;
    final api = ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (request) async {
          served++;
          final rows =
              served == 1 ? [stale, for (var i = 0; i < 49; i++) row(i)] : [for (var i = 0; i < 30; i++) row(i)];
          return http.Response(jsonEncode([for (final c in rows) c.toJson()]), 200,
              headers: {'x-omi-conversation-page-size': served == 1 ? '50' : '542', 'x-omi-has-more': 'true'});
        });
    final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
    addTearDown(provider.dispose);
    expect(await provider.fetchConversations(), isTrue);
    expect(provider.conversations.map((c) => c.id), contains('stale'));
    await provider.forceRefreshConversations();
    final ids = provider.conversations.map((c) => c.id).toList();
    expect(ids, isNot(contains('stale')), reason: 'created inside the refreshed range and absent from it: gone');
    expect(ids, containsAll(['c30', 'c48']), reason: 'older by created_at than the page: kept');
  });
}
