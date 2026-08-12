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
    provider.selectedDate = selectedDate;
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
