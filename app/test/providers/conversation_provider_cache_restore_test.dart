import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/off_ui_isolate.dart';

ServerConversation _row(String id,
        {String title = 'Cached', ConversationStatus status = ConversationStatus.completed}) =>
    ServerConversation(
        id: id,
        createdAt: DateTime.utc(2026, 10, 20),
        structured: Structured(title, 'Synthetic summary'),
        status: status);

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-owner'});
    await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
  });

  test('default provider restores a large stored cache through a completed worker', () async {
    await SharedPreferencesUtil().saveStringList(
        'cachedConversations', [for (var i = 0; i < 2000; i++) jsonEncode(_row('fixture-$i').toJson())]);
    offUiIsolateWorkerCompletions = 0;
    offUiIsolateFallbacks = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    expect(await provider.fetchConversations(), isTrue);
    expect(provider.conversations, hasLength(2000));
    expect(offUiIsolateWorkerCompletions, greaterThan(0));
    expect(offUiIsolateFallbacks, 0);
  });

  for (final serverOk in [true, false]) {
    test('async cache fallback for server ok=$serverOk preserves concurrent live rows and filters', () async {
      final entered = Completer<void>();
      final cache = Completer<List<ServerConversation>>();
      final provider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: serverOk),
        conversationCacheLoader: () {
          entered.complete();
          return cache.future;
        },
        isSignedIn: () => true,
      );
      addTearDown(provider.dispose);
      final pending = provider.fetchConversations();
      await entered.future;
      await provider.addConversation(_row('same', title: 'Live'));
      provider.memoriesToDelete['deleted'] = _row('deleted');
      provider.addProcessingConversation(_row('processing', status: ConversationStatus.processing));
      cache.complete([_row('same'), _row('cached-only'), _row('deleted'), _row('processing')]);
      expect(await pending, serverOk);
      expect(provider.conversations.map((row) => row.id), ['same', 'cached-only']);
      expect(provider.conversations.first.structured.title, 'Live');
      expect(provider.isLoadingConversations, isFalse);
    });
  }

  test('sign-out and owner switch reject cache completions', () async {
    for (final changeOwner in [false, true]) {
      final entered = Completer<void>();
      final cache = Completer<List<ServerConversation>>();
      var signedIn = true;
      final provider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        conversationCacheLoader: () {
          entered.complete();
          return cache.future;
        },
        isSignedIn: () => signedIn,
      );
      final pending = provider.fetchConversations();
      await entered.future;
      if (changeOwner) {
        SharedPreferencesUtil().uid = 'another-fixture-owner';
      } else {
        signedIn = false;
      }
      cache.complete([_row('old-account')]);
      expect(await pending, isFalse);
      expect(provider.conversations, isEmpty);
      provider.dispose();
    }
  });

  test('clear invalidates a cache restore', () async {
    final entered = Completer<void>();
    final cache = Completer<List<ServerConversation>>();
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationCacheLoader: () {
        entered.complete();
        return cache.future;
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    final pending = provider.fetchConversations();
    await entered.future;
    provider.clearUserData();
    cache.complete([_row('old-account')]);
    expect(await pending, isFalse);
    expect(provider.conversations, isEmpty);
    expect(provider.groupedConversations, isEmpty);
  });

  test('stale restore cannot overwrite or clear loading for a newer fetch', () async {
    final entered = Completer<void>();
    final cache = Completer<List<ServerConversation>>();
    final newerPage = Completer<({List<ServerConversation> items, bool ok})>();
    var calls = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () =>
          ++calls == 1 ? Future.value((items: <ServerConversation>[], ok: true)) : newerPage.future,
      conversationCacheLoader: () {
        entered.complete();
        return cache.future;
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    final older = provider.fetchConversations();
    await entered.future;
    final newer = provider.fetchConversations();
    cache.complete([_row('stale')]);
    expect(await older, isFalse);
    expect(provider.isLoadingConversations, isTrue);
    newerPage.complete((items: [_row('fresh')], ok: true));
    expect(await newer, isTrue);
    expect(provider.conversations.map((row) => row.id), ['fresh']);
  });

  test('dispose during decode cannot notify or restore afterwards', () async {
    final entered = Completer<void>();
    final cache = Completer<List<ServerConversation>>();
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationCacheLoader: () {
        entered.complete();
        return cache.future;
      },
      isSignedIn: () => true,
    );
    final pending = provider.fetchConversations();
    await entered.future;
    provider.dispose();
    cache.complete([_row('late')]);
    expect(await pending, isFalse);
    expect(provider.conversations, isEmpty);
  });

  test('local phone rows remain newer than a matching cached object', () async {
    final entered = Completer<void>();
    final cache = Completer<List<ServerConversation>>();
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationCacheLoader: () {
        entered.complete();
        return cache.future;
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.upsertConversation(_row('ondevice-local', title: 'Local latest'));
    final pending = provider.fetchConversations();
    await entered.future;
    cache.complete([_row('ondevice-local', title: 'Stale cache'), _row('history')]);
    expect(await pending, isTrue);
    expect(provider.conversations.firstWhere((row) => row.id == 'ondevice-local').structured.title, 'Local latest');
  });

  for (final serverOk in [true, false]) {
    test('full fetch releases an invalidated non-shimmer search: server=$serverOk', () async {
      final search = Completer<ConversationSearchResult>();
      final provider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: serverOk),
        conversationCacheLoader: () async => [],
        conversationSearchResultFetcher:
            (query, {page, limit, required includeDiscarded, startDate, endDate, speakerId}) => search.future,
        isSignedIn: () => true,
      );
      addTearDown(provider.dispose);
      final searching = provider.searchConversations('old');
      expect(provider.isFetchingConversations, isTrue);
      expect(await provider.fetchConversations(), serverOk);
      expect(provider.isFetchingConversations, isFalse);
      expect(provider.isLoadingConversations, isFalse);
      search.complete(ConversationSearchResult(
        items: [_row('stale-search')],
        currentPage: 1,
        totalPages: 1,
        outcome: ConversationSearchResultOutcome.success,
      ));
      await searching;
      expect(provider.searchedConversations, isEmpty);
    });

    for (final searchFinishesFirst in [true, false]) {
      test('cache restore preserves a newer search: server=$serverOk searchFirst=$searchFinishesFirst', () async {
        final entered = Completer<void>();
        final cache = Completer<List<ServerConversation>>();
        final search = Completer<ConversationSearchResult>();
        final provider = ConversationProvider(
          conversationListFetcher: () async => (items: <ServerConversation>[], ok: serverOk),
          conversationCacheLoader: () {
            entered.complete();
            return cache.future;
          },
          conversationSearchResultFetcher:
              (query, {page, limit, required includeDiscarded, startDate, endDate, speakerId}) => search.future,
          isSignedIn: () => true,
        );
        addTearDown(provider.dispose);
        final pending = provider.fetchConversations();
        await entered.future;
        final searching = provider.searchConversations('needle', showShimmer: true);
        void completeSearch() => search.complete(ConversationSearchResult(
              items: [_row('ranked-hit')],
              currentPage: 1,
              totalPages: 1,
              outcome: ConversationSearchResultOutcome.success,
            ));
        if (searchFinishesFirst) {
          completeSearch();
          await searching;
          // The base fetch still owns its loading state until decode completes.
          expect(provider.isLoadingConversations, isTrue);
        }
        cache.complete([_row('unrelated-history')]);
        expect(await pending, serverOk);
        expect(provider.conversations.single.id, 'unrelated-history');
        expect(provider.searchedConversations.map((row) => row.id), searchFinishesFirst ? ['ranked-hit'] : isEmpty);
        expect(provider.groupedConversations.values.expand((rows) => rows).map((row) => row.id),
            searchFinishesFirst ? ['ranked-hit'] : isEmpty);
        expect(provider.isLoadingConversations, !searchFinishesFirst);
        if (!searchFinishesFirst) {
          completeSearch();
          await searching;
        }
        expect(provider.isLoadingConversations, isFalse);
        await provider.searchConversations('');
        expect(provider.groupedConversations.values.expand((rows) => rows).single.id, 'unrelated-history');
      });
    }
  }

  test('a full-fetch search reset cannot retain a speaker and hide its fetched rows', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: [_row('server-history')], ok: true),
      conversationCacheLoader: () async => [],
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.selectedSpeakerId = 'previous-speaker';
    provider.previousQuery = 'previous-query';
    expect(await provider.fetchConversations(), isTrue);
    expect(provider.groupedConversations.values.expand((rows) => rows).single.id, 'server-history');
    expect(provider.hasActiveSearch, isFalse);
    expect(provider.selectedSpeakerId, isNull);
  });
}
