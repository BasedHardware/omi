import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('an empty successful search remains distinct from a failed request', () async {
    final provider = ConversationProvider(
      conversationSearchResultFetcher: (query,
              {page, limit, required includeDiscarded, startDate, endDate, speakerId}) async =>
          const ConversationSearchResult(
        items: [],
        currentPage: 1,
        totalPages: 1,
        outcome: ConversationSearchResultOutcome.success,
      ),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final result = await provider.searchConversations('missing');

    expect(result.isSuccess, isTrue);
    expect(result.items, isEmpty);
    expect(provider.lastSearchResult?.isSuccess, isTrue);
    expect(provider.isFetchingConversations, isFalse);
  });

  test('a failed request does not replace the rendered result with an empty list', () async {
    final existing = _conversation('existing');
    var shouldFail = false;
    final provider = ConversationProvider(
      conversationSearchResultFetcher:
          (query, {page, limit, required includeDiscarded, startDate, endDate, speakerId}) async => shouldFail
              ? const ConversationSearchResult.failure(statusCode: 503)
              : ConversationSearchResult(
                  items: [existing],
                  currentPage: 1,
                  totalPages: 1,
                  outcome: ConversationSearchResultOutcome.success,
                ),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    await provider.searchConversations('existing');
    shouldFail = true;
    final result = await provider.searchConversations('temporary failure');

    expect(result.outcome, ConversationSearchResultOutcome.failure);
    expect(result.statusCode, 503);
    expect(provider.searchedConversations.single.id, 'existing');
    expect(provider.isFetchingConversations, isFalse);
  });

  test('a superseded request cannot overwrite a newer search', () async {
    final first = Completer<ConversationSearchResult>();
    final second = Completer<ConversationSearchResult>();
    var calls = 0;
    final provider = ConversationProvider(
      conversationSearchResultFetcher: (query,
              {page, limit, required includeDiscarded, startDate, endDate, speakerId}) =>
          ++calls == 1 ? first.future : second.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final oldSearch = provider.searchConversations('old');
    final newSearch = provider.searchConversations('new');
    second.complete(
      ConversationSearchResult(
        items: [_conversation('new-result')],
        currentPage: 1,
        totalPages: 1,
        outcome: ConversationSearchResultOutcome.success,
      ),
    );
    await newSearch;
    first.complete(
      ConversationSearchResult(
        items: [_conversation('old-result')],
        currentPage: 1,
        totalPages: 1,
        outcome: ConversationSearchResultOutcome.success,
      ),
    );
    final oldResult = await oldSearch;

    expect(oldResult.isSuccess, isFalse);
    expect(provider.searchedConversations.single.id, 'new-result');
  });

  test('clearing search supersedes an in-flight query without repopulating it', () async {
    final oldRequest = Completer<ConversationSearchResult>();
    final provider = ConversationProvider(
      conversationSearchResultFetcher:
          (query, {page, limit, required includeDiscarded, startDate, endDate, speakerId}) => oldRequest.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final oldSearch = provider.searchConversations('old');
    final cleared = await provider.searchConversations('');
    oldRequest.complete(
      ConversationSearchResult(
        items: [_conversation('old-result')],
        currentPage: 1,
        totalPages: 1,
        outcome: ConversationSearchResultOutcome.success,
      ),
    );
    await oldSearch;

    expect(cleared.isSuccess, isTrue);
    expect(provider.searchedConversations, isEmpty);
    expect(provider.lastSearchResult?.isSuccess, isTrue);
  });

  test('a late pagination page cannot append after the query changes', () async {
    final oldPage = Completer<ConversationSearchResult>();
    final provider = ConversationProvider(
      conversationSearchResultFetcher: (query,
          {page, limit, required includeDiscarded, startDate, endDate, speakerId}) {
        if (query == 'old' && page == null) {
          return Future.value(
            ConversationSearchResult(
              items: [_conversation('old-first')],
              currentPage: 1,
              totalPages: 2,
              outcome: ConversationSearchResultOutcome.success,
            ),
          );
        }
        if (query == 'old') return oldPage.future;
        return Future.value(
          ConversationSearchResult(
            items: [_conversation('new-first')],
            currentPage: 1,
            totalPages: 1,
            outcome: ConversationSearchResultOutcome.success,
          ),
        );
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    await provider.searchConversations('old');
    final oldPagination = provider.searchMoreConversations();
    await provider.searchConversations('new');
    oldPage.complete(
      ConversationSearchResult(
        items: [_conversation('old-second')],
        currentPage: 2,
        totalPages: 2,
        outcome: ConversationSearchResultOutcome.success,
      ),
    );
    await oldPagination;

    expect(provider.searchedConversations.map((item) => item.id), ['new-first']);
  });
}

ServerConversation _conversation(String id) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026),
      structured: Structured(id, 'Test result'),
    );
