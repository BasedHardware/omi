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

  test('marking a conversation read does not regroup the entire list', () {
    final conversation = ServerConversation(
      id: 'c1',
      createdAt: DateTime.utc(2026, 8, 10),
      structured: Structured('Title', 'Overview'),
    )..isNew = true;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    provider.conversations = [conversation];
    provider.groupConversationsByDate();
    final groupedBeforeTap = provider.groupedConversations;
    var notificationCount = 0;
    provider.addListener(() => notificationCount++);

    provider.onConversationTap(conversation.id);

    expect(conversation.isNew, isFalse);
    expect(identical(provider.groupedConversations, groupedBeforeTap), isTrue);
    expect(notificationCount, 1);
  });

  test('marking a synced replacement read updates canonical and grouped objects', () {
    final original = _conversation('c1')..isNew = true;
    final provider = _providerWith([original]);
    addTearDown(provider.dispose);
    provider.groupConversationsByDate();
    final replacement = _conversation('c1')..isNew = true;

    provider.updateConversationInSortedList(replacement);
    provider.onConversationTap(replacement.id);

    expect(provider.conversations.single, same(replacement));
    expect(provider.conversations.single.isNew, isFalse);
    expect(provider.groupedConversations.values.single.single, same(replacement));
    expect(provider.groupedConversations.values.single.single.isNew, isFalse);
  });

  test('detail enrichment re-locates the conversation after a list reorder', () async {
    final original = _conversation('c1');
    final provider = _providerWith([original]);
    addTearDown(provider.dispose);
    provider.groupConversationsByDate();
    final date = provider.groupedConversations.keys.single;
    final enrichment = _conversation('c1');
    final pending = Completer<ServerConversation?>();
    provider.conversationDetailsFetcherOverride = (_) => pending.future;

    final update = provider.updateSearchedConvoDetails(original.id);
    final other = _conversation('other', createdAt: original.createdAt.subtract(const Duration(minutes: 1)));
    provider.groupedConversations[date]!.insert(0, other);
    pending.complete(enrichment);
    await update;

    expect(provider.groupedConversations[date]![0], same(other));
    expect(
      provider.groupedConversations[date]!.firstWhere((conversation) => conversation.id == 'c1'),
      same(enrichment),
    );
  });
}

ConversationProvider _providerWith(List<ServerConversation> conversations) {
  final provider = ConversationProvider(
    conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
    isSignedIn: () => true,
  );
  provider.conversations = conversations;
  return provider;
}

ServerConversation _conversation(String id, {DateTime? createdAt}) => ServerConversation(
      id: id,
      createdAt: createdAt ?? DateTime.utc(2026, 8, 10),
      structured: Structured('Title', 'Overview'),
    );
