import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('signed-out failure does not retry or request daily summaries', () async {
    var signedIn = true;
    var fetchCalls = 0;
    var dailySummaryCalls = 0;
    final response = Completer<({List<ServerConversation> items, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () {
        fetchCalls++;
        return response.future;
      },
      dailySummariesChecker: () async {
        dailySummaryCalls++;
        return false;
      },
      isSignedIn: () => signedIn,
    );
    addTearDown(provider.dispose);

    final initialFetch = provider.getInitialConversations();
    signedIn = false;
    response.complete((items: <ServerConversation>[], ok: false));
    await initialFetch;

    expect(fetchCalls, 1);
    expect(dailySummaryCalls, 0);
    expect(provider.isAwaitingInitialFetchRetry, isFalse);
  });

  test('clearUserData invalidates an in-flight failure before it can retry', () async {
    final response = Completer<({List<ServerConversation> items, bool ok})>();
    var dailySummaryCalls = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () => response.future,
      dailySummariesChecker: () async {
        dailySummaryCalls++;
        return false;
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final initialFetch = provider.getInitialConversations();
    provider.clearUserData();
    response.complete((items: <ServerConversation>[], ok: false));
    await initialFetch;

    expect(dailySummaryCalls, 0);
    expect(provider.conversationsLoadFailed, isFalse);
    expect(provider.isAwaitingInitialFetchRetry, isFalse);
  });

  test('signed-in transient failure keeps the existing retry behavior', () async {
    var dailySummaryCalls = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: false),
      dailySummariesChecker: () async {
        dailySummaryCalls++;
        return false;
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    await provider.getInitialConversations();

    expect(dailySummaryCalls, 0);
    expect(provider.conversationsLoadFailed, isTrue);
    expect(provider.isAwaitingInitialFetchRetry, isTrue);
  });

  test('successful initial fetch still checks daily summaries', () async {
    var dailySummaryCalls = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      dailySummariesChecker: () async {
        dailySummaryCalls++;
        return true;
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    await provider.getInitialConversations();

    expect(dailySummaryCalls, 1);
    expect(provider.hasDailySummaries, isTrue);
    expect(provider.isAwaitingInitialFetchRetry, isFalse);
  });

  test('clearUserData invalidates an in-flight search result', () async {
    final response = Completer<(List<ServerConversation>, int, int)>();
    final provider = ConversationProvider(
      conversationSearchFetcher: (query, {page, limit, required includeDiscarded, speakerId}) => response.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final search = provider.searchConversations('old account');
    provider.clearUserData();
    response.complete(([_conversation('old-search-result')], 1, 1));
    await search;

    expect(provider.searchedConversations, isEmpty);
    expect(provider.groupedConversations, isEmpty);
  });

  test('clearUserData invalidates an in-flight search pagination result', () async {
    final response = Completer<(List<ServerConversation>, int, int)>();
    final provider = ConversationProvider(
      conversationSearchFetcher: (query, {page, limit, required includeDiscarded, speakerId}) => response.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.previousQuery = 'old account';
    provider.currentSearchPage = 1;
    provider.totalSearchPages = 2;

    final searchMore = provider.searchMoreConversations();
    provider.clearUserData();
    response.complete(([_conversation('old-page-result')], 2, 2));
    await searchMore;

    expect(provider.searchedConversations, isEmpty);
    expect(provider.groupedConversations, isEmpty);
  });
}

ServerConversation _conversation(String id) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026),
      structured: Structured('Old account', 'Must not reappear'),
    );
