import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/pages/conversations/conversations_page.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('refresh clears the processing card for a conversation the server completed', () async {
    // Regression: the websocket ConversationEvent that clears the card was
    // missed, and the server has since completed the conversation. A refresh
    // must drop the stale "Processing" card instead of leaving it pinned forever.
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.completed)], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.completed), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
    expect(provider.conversations.map((c) => c.id), contains('c1'));
  });

  test('refresh clears the processing card when lifecycle rolls back to in progress', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.in_progress), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
  });

  test('refresh clears the processing card when lifecycle failed', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.failed), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
  });

  test('locked lifecycle detail is terminal and clears the processing card', () async {
    // The list endpoint returns a redacted completed row for locked
    // conversations while the detail endpoint returns 402. The HTTP adapter
    // maps that 402 to an authoritative null result (ok: true), which must
    // not leave the Processing card pinned forever.
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.completed)], ok: true),
      conversationLifecycleFetcher: (_) async => (item: null, ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
    expect(provider.conversations.map((conversation) => conversation.id), ['c1']);
  });

  test('refresh keeps processing cards the server still reports as processing', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.processing)], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.processing), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations.map((c) => c.id), ['c1']);
  });

  test('refresh keeps cards the server reports as merging', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.merging), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations.single.status, ConversationStatus.merging);
  });

  test('refresh keeps a local placeholder card the server does not know about', () async {
    // forceProcessingCurrentConversation adds a local-only placeholder (id '0')
    // before the server conversation exists; a concurrent refresh must not drop it.
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('other', status: ConversationStatus.completed)], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('0', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations.map((c) => c.id), ['0']);
  });

  test('failed refresh leaves the processing card untouched', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: false),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations.map((c) => c.id), ['c1']);
  });

  test('failed lifecycle lookup leaves an absent processing card untouched', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async => (item: null, ok: false),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations.map((c) => c.id), ['c1']);
  });

  test('timed-out tracked page lookup preserves the local processing card', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.completed)], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    final refresh = provider.forceRefreshConversations();
    await Future<void>.delayed(const Duration(seconds: 3));
    await refresh;

    expect(provider.processingConversations.single.status, ConversationStatus.processing);
    lifecycle.complete((item: _conversation('c1', status: ConversationStatus.completed), ok: true));
  });

  test('lifecycle probes stop dequeuing after the deadline', () async {
    final pending = <Completer<({ServerConversation? item, bool ok})>>[];
    var calls = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) {
        calls++;
        final completer = Completer<({ServerConversation? item, bool ok})>();
        pending.add(completer);
        return completer.future;
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    for (var i = 0; i < 8; i++) {
      provider.addProcessingConversation(_conversation('c$i', status: ConversationStatus.processing));
    }

    final refresh = provider.forceRefreshConversations();
    await Future<void>.delayed(const Duration(seconds: 3));
    await refresh;

    expect(calls, 4);
    for (final completer in pending) {
      completer.complete((item: null, ok: false));
    }
  });

  test('authoritative missing lifecycle clears an absent real processing card', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async => (item: null, ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
  });

  test('processingIdsAtStart prevents stale lifecycle data from reviving a completed row', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.completed)], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    final refresh = provider.forceRefreshConversations();
    await Future<void>.delayed(Duration.zero);
    // Remove the row as the websocket handler does, but mutate the public list
    // directly here so this regression isolates the processingIdsAtStart guard
    // from the separate removal-tombstone guard.
    provider.processingConversations.removeWhere((conversation) => conversation.id == 'c1');
    lifecycle.complete((item: _conversation('c1', status: ConversationStatus.processing), ok: true));
    await refresh;

    expect(provider.processingConversations, isEmpty);
  });

  test('websocket processing revision blocks a newly discovered stale page row', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('new', status: ConversationStatus.processing)], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('off-page', status: ConversationStatus.processing));

    final refresh = provider.forceRefreshConversations();
    await Future<void>.delayed(Duration.zero);
    // The page row has not been admitted yet, so the websocket removal is a
    // list no-op but still advances the state revision observed by refresh.
    provider.removeProcessingConversation('new');
    lifecycle.complete((item: _conversation('off-page', status: ConversationStatus.completed), ok: true));
    await refresh;

    expect(provider.processingConversations, isEmpty);
  });

  test('unrelated websocket transition does not suppress a newly discovered row', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('new', status: ConversationStatus.processing)], ok: true),
      conversationLifecycleFetcher: (id) {
        if (id == 'unrelated') {
          return Future.value((item: _conversation('unrelated', status: ConversationStatus.completed), ok: true));
        }
        return lifecycle.future;
      },
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('unrelated', status: ConversationStatus.processing));

    final refresh = provider.forceRefreshConversations();
    await Future<void>.delayed(Duration.zero);
    // This unrelated completion must not suppress the newly discovered page
    // row, which has no websocket mutation of its own.
    provider.removeProcessingConversation('unrelated');
    lifecycle.complete((item: _conversation('new', status: ConversationStatus.processing), ok: true));
    await refresh;

    expect(provider.processingConversations.map((conversation) => conversation.id), ['new']);
  });

  test('websocket completion during list fetch blocks a stale processing page row', () async {
    final page = Completer<({List<ServerConversation> items, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () => page.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final refresh = provider.forceRefreshConversations();
    await Future<void>.delayed(Duration.zero);
    provider.removeProcessingConversation('new');
    page.complete((items: [_conversation('new', status: ConversationStatus.processing)], ok: true));
    await refresh;

    expect(provider.processingConversations, isEmpty);
  });

  test('websocket processing start during list fetch keeps the newer live row', () async {
    final page = Completer<({List<ServerConversation> items, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () => page.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final refresh = provider.forceRefreshConversations();
    await Future<void>.delayed(Duration.zero);
    provider.addProcessingConversation(_conversation('new', status: ConversationStatus.processing, title: 'Live'));
    page.complete((items: [_conversation('new', status: ConversationStatus.processing, title: 'Stale')], ok: true));
    await refresh;

    expect(provider.processingConversations.single.structured.title, 'Live');
  });

  test('replayed processing start replaces the existing row instead of duplicating it', () async {
    final provider = ConversationProvider(isSignedIn: () => true);
    addTearDown(provider.dispose);

    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, title: 'Old'));
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, title: 'Live'));

    expect(provider.processingConversations, hasLength(1));
    expect(provider.processingConversations.single.structured.title, 'Live');
  });

  test('full fetch preserves a websocket-completed row omitted by the stale page', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    final fetch = provider.fetchConversations();
    await Future<void>.delayed(Duration.zero);
    // This is the websocket completion path: remove the processing card and
    // publish the completed conversation while the stale fetch is waiting.
    provider.removeProcessingConversation('c1');
    await provider.addConversation(_conversation('c1', status: ConversationStatus.completed, title: 'Completed'));
    lifecycle.complete((item: _conversation('c1', status: ConversationStatus.completed), ok: true));
    await fetch;

    expect(provider.conversations.map((conversation) => conversation.id), ['c1']);
    expect(provider.conversations.single.structured.title, 'Completed');
  });

  test('full fetch prefers websocket completion when stale page still has processing row', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.processing, title: 'Stale')], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    final fetch = provider.fetchConversations();
    await Future<void>.delayed(Duration.zero);
    provider.removeProcessingConversation('c1');
    await provider.addConversation(_conversation('c1', status: ConversationStatus.completed, title: 'Completed'));
    lifecycle.complete((item: _conversation('c1', status: ConversationStatus.completed), ok: true));
    await fetch;

    expect(provider.conversations.single.structured.title, 'Completed');
  });

  test('full fetch prefers changed websocket object over stale completed page row', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.completed, title: 'Stale')], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.conversations = [_conversation('c1', status: ConversationStatus.completed, title: 'Before')];
    provider.addProcessingConversation(_conversation('off-page', status: ConversationStatus.processing));

    final fetch = provider.fetchConversations();
    await Future<void>.delayed(Duration.zero);
    provider.updateConversation(_conversation('c1', status: ConversationStatus.completed, title: 'Live'));
    lifecycle.complete((item: null, ok: false));
    await fetch;

    expect(provider.conversations.single.structured.title, 'Live');
  });

  test('successful lifecycle completion publishes detail when page still says processing', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.processing, title: 'Stale')], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.completed, title: 'Completed'), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.fetchConversations();

    expect(provider.processingConversations, isEmpty);
    expect(provider.conversations.single.structured.title, 'Completed');
  });

  test('background refresh publishes lifecycle completion when page still says processing', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.processing, title: 'Stale')], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.completed, title: 'Completed'), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
    expect(provider.conversations.single.structured.title, 'Completed');
  });

  test('background refresh replaces stale same-id completed object with lifecycle detail', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.processing, title: 'Page')], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.completed, title: 'Detail'), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.conversations = [_conversation('c1', status: ConversationStatus.completed, title: 'Old')];
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.conversations.single.structured.title, 'Detail');
  });

  test('background refresh does not publish stale lifecycle completion over newer processing start', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.processing, title: 'Page')], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, title: 'Old'));

    final refresh = provider.forceRefreshConversations();
    await Future<void>.delayed(Duration.zero);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, title: 'New'));
    lifecycle.complete((item: _conversation('c1', status: ConversationStatus.completed), ok: true));
    await refresh;

    expect(provider.processingConversations.single.structured.title, 'New');
    expect(provider.conversations, isEmpty);
  });

  test('full fetch does not publish stale page completion over newer processing start', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.completed, title: 'Page')], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, title: 'Old'));

    final fetch = provider.fetchConversations();
    await Future<void>.delayed(Duration.zero);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, title: 'New'));
    lifecycle.complete((item: _conversation('c1', status: ConversationStatus.completed), ok: true));
    await fetch;

    expect(provider.processingConversations.single.structured.title, 'New');
    expect(provider.conversations, isEmpty);
  });

  test('cache fallback does not resurrect a row still marked processing', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('c1', status: ConversationStatus.completed, title: 'Page')], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    final cached = _conversation('c1', status: ConversationStatus.completed, title: 'Cached');
    SharedPreferencesUtil().cachedConversations = [cached];
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, title: 'Old'));

    final fetch = provider.fetchConversations();
    await Future<void>.delayed(Duration.zero);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, title: 'New'));
    lifecycle.complete((item: _conversation('c1', status: ConversationStatus.completed), ok: true));
    await fetch;

    expect(provider.conversations, isEmpty);
  });

  test('failed fetch cache fallback does not resurrect a row still marked processing', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: false),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    SharedPreferencesUtil().cachedConversations = [
      _conversation('c1', status: ConversationStatus.completed, title: 'Cached'),
    ];
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    final fetched = await provider.fetchConversations();

    expect(fetched, isFalse);
    expect(provider.conversations, isEmpty);
  });

  test('live completion overlay does not disable the next server page', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final firstPage = List<ServerConversation>.generate(
      50,
      (index) => _conversation('page-$index', status: ConversationStatus.completed),
    );
    var requestedOffset = -1;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: firstPage, ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    provider.conversationPageFetcherOverride = () async {
      requestedOffset = provider.conversationServerOffset;
      return (items: <ServerConversation>[], ok: true);
    };
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('off-page', status: ConversationStatus.processing));

    final fetch = provider.fetchConversations();
    await Future<void>.delayed(Duration.zero);
    await provider.addConversation(_conversation('live', status: ConversationStatus.completed, title: 'Live'));
    lifecycle.complete((item: _conversation('off-page', status: ConversationStatus.processing), ok: true));
    await fetch;

    expect(provider.conversations, hasLength(51));
    expect(provider.hasMoreConversations, isTrue);
    expect(provider.conversationServerOffset, 50);
    await provider.getMoreConversationsFromServer();
    expect(requestedOffset, 50);
  });

  test('failed load-more preserves cursor for a retry and deduplicates boundary rows', () async {
    var calls = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (
        items: List<ServerConversation>.generate(
          50,
          (index) => _conversation('page-$index', status: ConversationStatus.completed),
        ),
        ok: true
      ),
      isSignedIn: () => true,
    );
    provider.conversationPageFetcherOverride = () async {
      calls++;
      if (calls == 1) return (items: <ServerConversation>[], ok: false);
      return (
        items: [
          _conversation('page-49', status: ConversationStatus.completed),
          _conversation('page-50', status: ConversationStatus.completed),
        ],
        ok: true
      );
    };
    addTearDown(provider.dispose);

    await provider.fetchConversations();
    await provider.getMoreConversationsFromServer();
    expect(provider.conversationServerOffset, 50);
    await provider.getMoreConversationsFromServer();

    expect(calls, 2);
    expect(provider.conversationServerOffset, 52);
    expect(provider.conversations.where((conversation) => conversation.id == 'page-49'), hasLength(1));
    expect(provider.conversations.where((conversation) => conversation.id == 'page-50'), hasLength(1));
  });

  test('background refresh does not rewind a loaded page cursor', () async {
    var requestedOffsets = <int>[];
    final provider = ConversationProvider(
      conversationListFetcher: () async => (
        items: List<ServerConversation>.generate(
          50,
          (index) => _conversation('page-$index', status: ConversationStatus.completed),
        ),
        ok: true
      ),
      isSignedIn: () => true,
    );
    provider.conversationPageFetcherOverride = () async {
      requestedOffsets.add(provider.conversationServerOffset);
      return (
        items: List<ServerConversation>.generate(
          50,
          (index) => _conversation('next-$index', status: ConversationStatus.completed),
        ),
        ok: true
      );
    };
    addTearDown(provider.dispose);

    await provider.fetchConversations();
    await provider.getMoreConversationsFromServer();
    await provider.forceRefreshConversations();
    await provider.getMoreConversationsFromServer();

    expect(requestedOffsets, [50, 100]);
  });

  test('successful delete rebases cursor for a loaded row, not an unloaded row', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (
        items: List<ServerConversation>.generate(
          50,
          (index) => _conversation('page-$index', status: ConversationStatus.completed),
        ),
        ok: true
      ),
      isSignedIn: () => true,
    );
    provider.conversationDeleteFetcherOverride = (_) async => true;
    addTearDown(provider.dispose);

    await provider.fetchConversations();
    expect(provider.conversationServerOffset, 50);
    provider.deleteConversationOnServer('page-10');
    await Future<void>.delayed(Duration.zero);
    expect(provider.conversationServerOffset, 49);
    provider.deleteConversationOnServer('never-loaded');
    await Future<void>.delayed(Duration.zero);
    expect(provider.conversationServerOffset, 49);
  });

  test('failed delete does not rebase the server cursor', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (
        items: List<ServerConversation>.generate(
          50,
          (index) => _conversation('page-$index', status: ConversationStatus.completed),
        ),
        ok: true
      ),
      isSignedIn: () => true,
    );
    provider.conversationDeleteFetcherOverride = (_) async => false;
    addTearDown(provider.dispose);

    await provider.fetchConversations();
    provider.deleteConversationOnServer('page-10');
    await Future<void>.delayed(Duration.zero);

    expect(provider.conversationServerOffset, 50);
  });

  test('delete completion from a prior session cannot mutate the new session', () async {
    final delete = Completer<bool>();
    final provider = ConversationProvider(isSignedIn: () => true);
    provider.conversationDeleteFetcherOverride = (_) => delete.future;
    addTearDown(provider.dispose);

    final oldConversation = _conversation('c1', status: ConversationStatus.completed, title: 'Old account');
    provider.memoriesToDelete[oldConversation.id] = oldConversation;
    provider.deleteConversationOnServer(oldConversation.id);

    provider.clearUserData();
    final newConversation = _conversation('c1', status: ConversationStatus.completed, title: 'New account');
    provider.memoriesToDelete[newConversation.id] = newConversation;
    provider.conversations = [newConversation];

    delete.complete(true);
    await Future<void>.delayed(Duration.zero);

    expect(provider.memoriesToDelete[newConversation.id], same(newConversation));
    expect(provider.conversations.single, same(newConversation));
  });

  test('delete failure from a prior session cannot mutate the new session', () async {
    final delete = Completer<bool>();
    final provider = ConversationProvider(isSignedIn: () => true);
    provider.conversationDeleteFetcherOverride = (_) => delete.future;
    addTearDown(provider.dispose);

    final oldConversation = _conversation('c1', status: ConversationStatus.completed, title: 'Old account');
    provider.memoriesToDelete[oldConversation.id] = oldConversation;
    provider.deleteConversationOnServer(oldConversation.id);

    provider.clearUserData();
    final newConversation = _conversation('c1', status: ConversationStatus.completed, title: 'New account');
    provider.memoriesToDelete[newConversation.id] = newConversation;
    provider.conversations = [newConversation];

    delete.completeError(StateError('old session delete failed'));
    await Future<void>.delayed(Duration.zero);

    expect(provider.memoriesToDelete[newConversation.id], same(newConversation));
    expect(provider.conversations.single, same(newConversation));
  });

  test('pending delete tombstone hides a row until DELETE settles', () async {
    final delete = Completer<bool>();
    final conversation = _conversation('page-10', status: ConversationStatus.completed);
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: [conversation], ok: true),
      isSignedIn: () => true,
    );
    provider.conversationDeleteFetcherOverride = (_) => delete.future;
    addTearDown(provider.dispose);

    provider.conversations = [conversation];
    provider.memoriesToDelete[conversation.id] = conversation;
    provider.deleteConversationOnServer(conversation.id);

    await provider.fetchConversations();
    expect(provider.conversations, isEmpty);
    expect(provider.memoriesToDelete, contains(conversation.id));

    delete.complete(true);
    await Future<void>.delayed(Duration.zero);
    expect(provider.memoriesToDelete, isEmpty);
    expect(provider.conversations, isEmpty);
  });

  test('background refresh does not reinsert a row while DELETE is pending', () async {
    final delete = Completer<bool>();
    final conversation = _conversation('c1', status: ConversationStatus.completed);
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: [conversation], ok: true),
      isSignedIn: () => true,
    );
    provider.conversationDeleteFetcherOverride = (_) => delete.future;
    addTearDown(provider.dispose);

    provider.conversations = [conversation];
    provider.deleteConversationLocally(conversation, conversationLocalDayKey(conversation.createdAt));
    provider.deleteConversationOnServer(conversation.id);

    await provider.forceRefreshConversations();
    expect(provider.conversations, isEmpty);
    expect(provider.memoriesToDelete, contains(conversation.id));

    delete.complete(true);
    await Future<void>.delayed(Duration.zero);
    expect(provider.memoriesToDelete, isEmpty);
    expect(provider.conversations, isEmpty);
  });

  test('stale full fetch is discarded after a confirmed delete', () async {
    final page = Completer<({List<ServerConversation> items, bool ok})>();
    final conversation = _conversation('c1', status: ConversationStatus.completed);
    final provider = ConversationProvider(
      conversationListFetcher: () => page.future,
      isSignedIn: () => true,
    );
    final delete = Completer<bool>();
    provider.conversationDeleteFetcherOverride = (_) => delete.future;
    addTearDown(provider.dispose);
    provider.conversations = [conversation];
    provider.memoriesToDelete[conversation.id] = conversation;
    final fetch = provider.fetchConversations();
    provider.deleteConversationOnServer(conversation.id);
    delete.complete(true);
    await Future<void>.delayed(Duration.zero);
    expect(provider.isLoadingConversations, isFalse);
    page.complete((items: [conversation], ok: true));
    await fetch;
    expect(provider.conversations, isEmpty);
    expect(provider.isLoadingConversations, isFalse);
  });

  test('stale background fetch is discarded after a confirmed delete', () async {
    final page = Completer<({List<ServerConversation> items, bool ok})>();
    final conversation = _conversation('c1', status: ConversationStatus.completed);
    final provider = ConversationProvider(
      conversationListFetcher: () => page.future,
      isSignedIn: () => true,
    );
    final delete = Completer<bool>();
    provider.conversationDeleteFetcherOverride = (_) => delete.future;
    addTearDown(provider.dispose);
    provider.conversations = [conversation];
    provider.memoriesToDelete[conversation.id] = conversation;
    final refresh = provider.forceRefreshConversations();
    provider.deleteConversationOnServer(conversation.id);
    delete.complete(true);
    await Future<void>.delayed(Duration.zero);
    expect(provider.isLoadingConversations, isFalse);
    page.complete((items: [conversation], ok: true));
    await refresh;
    expect(provider.conversations, isEmpty);
  });

  test('older overlapping full fetch cannot overwrite newer fetch', () async {
    final first = Completer<({List<ServerConversation> items, bool ok})>();
    final second = Completer<({List<ServerConversation> items, bool ok})>();
    var calls = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () => ++calls == 1 ? first.future : second.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);

    final older = provider.fetchConversations();
    final newer = provider.fetchConversations();
    second.complete((items: [_conversation('new', status: ConversationStatus.completed)], ok: true));
    await newer;
    expect(provider.conversations.map((item) => item.id), ['new']);
    first.complete((items: [_conversation('old', status: ConversationStatus.completed)], ok: true));
    await older;
    expect(provider.conversations.map((item) => item.id), ['new']);
    expect(provider.isLoadingConversations, isFalse);
  });

  test('full fetch owns loading over an in-flight load-more request', () async {
    final page = Completer<({List<ServerConversation> items, bool ok})>();
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final firstPage = List<ServerConversation>.generate(
      50,
      (index) => _conversation('page-$index', status: ConversationStatus.completed),
    );
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: firstPage, ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    provider.conversationPageFetcherOverride = () => page.future;
    addTearDown(provider.dispose);
    await provider.fetchConversations();
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    final more = provider.getMoreConversationsFromServer();
    final refresh = provider.fetchConversations();
    page.complete((items: [_conversation('page-50', status: ConversationStatus.completed)], ok: true));
    await more;
    expect(provider.isLoadingConversations, isTrue);
    lifecycle.complete((item: _conversation('c1', status: ConversationStatus.processing), ok: true));
    await refresh;
    expect(provider.isLoadingConversations, isFalse);
  });

  test('load-more filter key changes when short or discarded filters change', () {
    final base = conversationLoadMoreFilterKey(
      query: '',
      folderId: null,
      speakerId: null,
      startDate: null,
      endDate: null,
      starredOnly: false,
      discarded: false,
      shortOnly: false,
      shortThreshold: 0,
    );
    expect(
      conversationLoadMoreFilterKey(
        query: '',
        folderId: null,
        speakerId: null,
        startDate: null,
        endDate: null,
        starredOnly: false,
        discarded: true,
        shortOnly: false,
        shortThreshold: 0,
      ),
      isNot(base),
    );
    expect(
      conversationLoadMoreFilterKey(
        query: '',
        folderId: null,
        speakerId: null,
        startDate: null,
        endDate: null,
        starredOnly: false,
        discarded: false,
        shortOnly: true,
        shortThreshold: 30,
      ),
      isNot(base),
    );
  });

  test('failed page request releases the UI latch for the same offset retry', () {
    expect(
      shouldReleaseConversationLoadMoreLatch(
        currentRequestKey: 'offset:50',
        requestKey: 'offset:50',
        succeeded: false,
      ),
      isTrue,
    );
    expect(
      shouldReleaseConversationLoadMoreLatch(
        currentRequestKey: 'offset:50',
        requestKey: 'offset:50',
        succeeded: true,
      ),
      isFalse,
    );
    expect(
      shouldReleaseConversationLoadMoreLatch(
        currentRequestKey: 'offset:100',
        requestKey: 'offset:50',
        succeeded: false,
      ),
      isFalse,
    );
  });

  test('loading stays active until lifecycle reconciliation assigns the page', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('off-page', status: ConversationStatus.processing));

    final fetch = provider.fetchConversations();
    await Future<void>.delayed(Duration.zero);
    expect(provider.isLoadingConversations, isTrue);
    lifecycle.complete((item: _conversation('off-page', status: ConversationStatus.completed), ok: true));
    await fetch;
    expect(provider.isLoadingConversations, isFalse);
  });

  test('processing cards obey the active folder filter', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.processing, folderId: 'other'), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.selectedFolderId = 'selected';
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, folderId: 'other'));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
  });

  test('processing cards obey the active date filter', () async {
    final selectedDate = DateTime(2026, 1, 2);
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async => (
        item: _conversation('c1', status: ConversationStatus.processing, createdAt: DateTime.utc(2026, 1, 1)),
        ok: true
      ),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.selectedStartDate = selectedDate;
    provider.selectedEndDate = selectedDate;
    provider.addProcessingConversation(
      _conversation('c1', status: ConversationStatus.processing, createdAt: DateTime.utc(2026, 1, 1)),
    );

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
  });

  test('processing cards obey the starred filter', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.processing, starred: false), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.showStarredOnly = true;
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, starred: false));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
  });

  test('processing cards obey the discarded filter', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) async =>
          (item: _conversation('c1', status: ConversationStatus.processing, discarded: true), ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.showDiscardedConversations = false;
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing, discarded: true));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
  });

  test('full fetch does not publish processing rows into the completed list while lifecycle lookup waits', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async =>
          (items: [_conversation('processing', status: ConversationStatus.processing)], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.conversations = [_conversation('existing', status: ConversationStatus.completed)];
    provider.addProcessingConversation(_conversation('off-page', status: ConversationStatus.processing));

    final fetch = provider.fetchConversations();
    await Future<void>.delayed(Duration.zero);

    expect(provider.conversations.map((conversation) => conversation.id), ['existing']);
    lifecycle.complete((item: _conversation('off-page', status: ConversationStatus.completed), ok: true));
    await fetch;

    expect(
      provider.conversations.where((conversation) => conversation.status != ConversationStatus.completed),
      isEmpty,
    );
  });
}

ServerConversation _conversation(
  String id, {
  required ConversationStatus status,
  DateTime? createdAt,
  bool discarded = false,
  bool starred = false,
  String? folderId,
  String title = 'Title',
}) =>
    ServerConversation(
      id: id,
      createdAt: createdAt ?? DateTime.utc(2026),
      structured: Structured(title, 'Overview'),
      status: status,
      discarded: discarded,
      starred: starred,
      folderId: folderId,
    );
