import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/conversation_merge_journal.dart';

ServerConversation row(String id) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 10, 1),
      structured: Structured(id, 'summary'),
      status: ConversationStatus.completed,
    );

void main() {
  setUp(() async {
    Env.overrideApiBaseUrl('http://127.0.0.1:1/');
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  tearDown(Env.clearApiBaseUrlOverrideForTesting);

  test('completed merge removes originals from cache, search and a reopened offline provider', () async {
    final originals = [row('a'), row('b')];
    SharedPreferencesUtil().cachedConversations = originals;
    final provider = ConversationProvider(
      conversationLifecycleFetcher: (_) async => (item: row('new-target'), ok: true),
      isSignedIn: () => true,
    )
      ..conversations = originals.toList()
      ..searchedConversations = originals.toList();
    addTearDown(provider.dispose);

    await provider.onMergeCompleted('new-target', ['a', 'b']);
    expect(provider.conversations.map((c) => c.id), ['new-target']);
    expect(provider.searchedConversations.any((c) => c.id == 'a' || c.id == 'b'), false);
    expect((await SharedPreferencesUtil().loadCachedConversations()).map((c) => c.id), ['new-target']);

    final reopened = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: false),
      isSignedIn: () => true,
    );
    addTearDown(reopened.dispose);
    await reopened.fetchConversations();
    expect(reopened.conversations.map((c) => c.id), ['new-target']);
  });

  test('a page already in flight cannot restore merged-away sources', () async {
    final page = Completer<({List<ServerConversation> items, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () => page.future,
      conversationLifecycleFetcher: (_) async => (item: row('new-target'), ok: true),
      isSignedIn: () => true,
    )..conversations = [row('a'), row('b')];
    addTearDown(provider.dispose);
    final refresh = provider.fetchConversations();
    await provider.onMergeCompleted('new-target', ['a', 'b']);
    page.complete((items: [row('a'), row('b')], ok: true));
    await refresh;
    expect(provider.conversations.map((c) => c.id), ['new-target']);
  });

  for (final refreshDuringCompletion in [false, true]) {
    test('simultaneous completions preserve both targets after offline reopen, refresh=$refreshDuringCompletion',
        () async {
      SharedPreferencesUtil().uid = 'concurrent-merge-owner';
      final originals = [
        for (final id in ['a', 'b', 'c', 'd']) row(id)
      ];
      SharedPreferencesUtil().cachedConversations = originals;
      final entered = Completer<void>();
      final release = Completer<void>();
      var reads = 0;
      final provider = ConversationProvider(
        isSignedIn: () => true,
        conversationListFetcher: () async => (items: originals, ok: true),
        conversationCacheLoader: () async {
          final snapshot = SharedPreferencesUtil().cachedConversations;
          if (++reads == 1) {
            entered.complete();
            await release.future;
          }
          return snapshot;
        },
      )..conversations = originals.toList();
      provider.watchMerge(['a', 'b'], targetId: 'target-ab');
      provider.watchMerge(['c', 'd'], targetId: 'target-cd');
      addTearDown(provider.dispose);
      final first = provider.onMergeCompleted('target-ab', ['a', 'b'], merged: row('target-ab'));
      await entered.future;
      if (refreshDuringCompletion) await provider.fetchConversations(restoreMergeWatches: false);
      final second = provider.onMergeCompleted('target-cd', ['c', 'd'], merged: row('target-cd'));
      release.complete();
      await Future.wait([first, second]);
      expect(provider.conversations.map((c) => c.id), unorderedEquals(['target-ab', 'target-cd']));
      expect((await SharedPreferencesUtil().loadCachedConversations()).map((c) => c.id),
          unorderedEquals(['target-ab', 'target-cd']));
      expect(ConversationMergeJournal('concurrent-merge-owner', Env.apiBaseUrl!).load(), isEmpty);

      final reopened = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: false),
        isSignedIn: () => true,
      );
      addTearDown(reopened.dispose);
      await reopened.fetchConversations();
      expect(reopened.conversations.map((c) => c.id), unorderedEquals(['target-ab', 'target-cd']));
      expect(reopened.mergingConversationIds, isEmpty);
    });
  }

  test('failed cache reconciliation retains its journal and does not poison later completion or retry', () async {
    SharedPreferencesUtil().uid = 'retry-owner';
    final originals = [
      for (final id in ['a', 'b', 'c', 'd']) row(id)
    ];
    SharedPreferencesUtil().cachedConversations = originals;
    var reads = 0;
    final provider = ConversationProvider(
      isSignedIn: () => true,
      conversationCacheLoader: () async {
        if (++reads == 1) throw StateError('synthetic cache read failure');
        return SharedPreferencesUtil().cachedConversations;
      },
    )..conversations = originals.toList();
    addTearDown(provider.dispose);
    provider.watchMerge(['a', 'b'], targetId: 'target-ab');
    provider.watchMerge(['c', 'd'], targetId: 'target-cd');
    await expectLater(provider.onMergeCompleted('target-ab', ['a', 'b'], merged: row('target-ab')), throwsStateError);
    await provider.onMergeCompleted('target-cd', ['c', 'd'], merged: row('target-cd'));
    expect(ConversationMergeJournal('retry-owner', Env.apiBaseUrl!).load().map((m) => m.target), ['target-ab']);
    await provider.onMergeCompleted('target-ab', ['a', 'b'], merged: row('target-ab'));
    expect((await SharedPreferencesUtil().loadCachedConversations()).map((c) => c.id),
        unorderedEquals(['target-ab', 'target-cd']));
    expect(ConversationMergeJournal('retry-owner', Env.apiBaseUrl!).load(), isEmpty);
  });

  for (final changeAccount in [false, true]) {
    test('queued completions cannot mutate replacement ${changeAccount ? 'account' : 'backend'}', () async {
      final entered = Completer<void>();
      final release = Completer<void>();
      final provider = ConversationProvider(
        isSignedIn: () => true,
        conversationCacheLoader: () async {
          entered.complete();
          await release.future;
          return [
            for (final id in ['a', 'b', 'c', 'd']) row(id)
          ];
        },
      );
      addTearDown(provider.dispose);
      final first = provider.onMergeCompleted('target-ab', ['a', 'b'], merged: row('target-ab'));
      await entered.future;
      final second = provider.onMergeCompleted('target-cd', ['c', 'd'], merged: row('target-cd'));
      if (changeAccount) {
        provider.clearUserData();
        SharedPreferencesUtil().uid = 'replacement-owner';
      } else {
        Env.overrideApiBaseUrl('http://127.0.0.1:2/');
      }
      provider.conversations = [row('replacement')];
      SharedPreferencesUtil().cachedConversations = [row('replacement')];
      release.complete();
      await Future.wait([first, second]);
      expect(provider.conversations.map((c) => c.id), ['replacement']);
      expect((await SharedPreferencesUtil().loadCachedConversations()).map((c) => c.id), ['replacement']);
    });
  }

  test('failed target read retains original rows and merging markers', () async {
    final provider = ConversationProvider(
      conversationLifecycleFetcher: (_) async => (item: null, ok: false),
      isSignedIn: () => true,
    )
      ..conversations = [row('a'), row('b')]
      ..mergingConversationIds = {'a', 'b'};
    addTearDown(provider.dispose);
    await provider.onMergeCompleted('new-target', ['a', 'b']);
    expect(provider.conversations.map((c) => c.id), ['a', 'b']);
    expect(provider.mergingConversationIds, {'a', 'b'});
  });

  test('a late resolved completion cannot restore a target already incorporated by a later merge', () async {
    final entered = Completer<void>();
    final response = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      isSignedIn: () => true,
      conversationLifecycleFetcher: (_) {
        entered.complete();
        return response.future;
      },
    );
    addTearDown(provider.dispose);
    final oldCompletion = provider.onMergeCompleted('target-ab', ['a', 'b']);
    await entered.future;
    await provider.onMergeCompleted('final-target', ['target-ab', 'c'], merged: row('final-target'));
    response.complete((item: row('target-ab'), ok: true));
    await oldCompletion;
    expect(provider.conversations.map((c) => c.id), ['final-target']);
    expect((await SharedPreferencesUtil().loadCachedConversations()).map((c) => c.id), ['final-target']);
  });

  test('late completion cannot change a replacement account', () async {
    final target = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationLifecycleFetcher: (_) => target.future,
      isSignedIn: () => true,
    )..mergingConversationIds = {'a', 'b'};
    addTearDown(provider.dispose);
    final completion = provider.onMergeCompleted('new-target', ['a', 'b']);
    provider.clearUserData();
    provider.conversations = [row('replacement-account')];
    target.complete((item: row('new-target'), ok: true));
    await completion;
    expect(provider.conversations.map((c) => c.id), ['replacement-account']);
    expect(await SharedPreferencesUtil().loadCachedConversations(), isEmpty);
  });
}
