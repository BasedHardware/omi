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

  test('websocket completion during lifecycle lookup is not re-added by stale response', () async {
    final lifecycle = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (_) => lifecycle.future,
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    final refresh = provider.forceRefreshConversations();
    await Future<void>.delayed(Duration.zero);
    provider.removeProcessingConversation('c1');
    lifecycle.complete((item: _conversation('c1', status: ConversationStatus.processing), ok: true));
    await refresh;

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

ServerConversation _conversation(String id, {required ConversationStatus status}) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026),
      structured: Structured('Title', 'Overview'),
      status: status,
    );
