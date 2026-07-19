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
      conversationListFetcher: () async => (
        items: [_conversation('c1', status: ConversationStatus.completed)],
        ok: true,
      ),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations, isEmpty);
    expect(provider.conversations.map((c) => c.id), contains('c1'));
  });

  test('refresh keeps processing cards the server still reports as processing', () async {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (
        items: [_conversation('c1', status: ConversationStatus.processing)],
        ok: true,
      ),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.addProcessingConversation(_conversation('c1', status: ConversationStatus.processing));

    await provider.forceRefreshConversations();

    expect(provider.processingConversations.map((c) => c.id), ['c1']);
  });

  test('refresh keeps a local placeholder card the server does not know about', () async {
    // forceProcessingCurrentConversation adds a local-only placeholder (id '0')
    // before the server conversation exists; a concurrent refresh must not drop it.
    final provider = ConversationProvider(
      conversationListFetcher: () async => (
        items: [_conversation('other', status: ConversationStatus.completed)],
        ok: true,
      ),
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
}

ServerConversation _conversation(String id, {required ConversationStatus status}) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026),
      structured: Structured('Title', 'Overview'),
      status: status,
    );
