import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/onboarding/conversation_created_widget.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/conversation_sync_utils.dart';

/// Regression for #10980: conversations are bucketed by
/// `conversationLocalDayKey(startedAt ?? createdAt)` — the viewer's *local*
/// calendar day. Call sites that navigate to a conversation used to rebuild that
/// key from the raw UTC `year/month/day` of `createdAt`, which is a different day
/// from the group key for every viewer whose local day disagrees with UTC. The
/// lookup then missed (chat conversation links did nothing) or the detail page
/// opened on a key nothing is grouped under.
///
/// Each test sweeps all 24 hours instead of pinning one timestamp: a single fixed
/// hour only trips the bug at some UTC offsets, which is how these reached main
/// green.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('findGroupedConversationById locates the conversation at every hour of the day', () {
    // The chat conversation-link path (ai_message.dart): it holds only the
    // conversation id and a UTC `createdAt`, never `startedAt`, so it cannot
    // derive the group key at all — it must look the conversation up by id.
    for (var hour = 0; hour < 24; hour++) {
      final convo = _conversationAt('c1', DateTime.utc(2026, 7, 18, hour, 30));
      final provider = _providerWith([convo]);

      final located = provider.findGroupedConversationById('c1');

      expect(located, isNotNull, reason: 'startedAt hour $hour UTC');
      final (date, idx) = located!;
      expect(date, provider.groupedConversations.keys.single);
      expect(provider.groupedConversations[date]![idx].id, 'c1');
    }
  });

  test('findGroupedConversationById reports a miss for an unknown id', () {
    final provider = _providerWith([_conversationAt('c1', DateTime.utc(2026, 7, 18, 9))]);

    expect(provider.findGroupedConversationById('nope'), isNull);
  });

  test('ensureConversationGrouped files a conversation under its own group key', () {
    // The memory -> conversation path (memory_item.dart): it inserted the
    // conversation under one key and then selected another, so the detail page
    // opened on an empty group.
    for (var hour = 0; hour < 24; hour++) {
      final convo = _conversationAt('c1', DateTime.utc(2026, 7, 18, hour, 30));
      final provider = _providerWith([]);

      final date = provider.ensureConversationGrouped(convo);

      expect(provider.groupedConversations[date]?.map((c) => c.id), ['c1'], reason: 'startedAt hour $hour UTC');
      // The key it files under must be the one the list itself would group by.
      provider.conversations = [convo];
      provider.groupConversationsByDate();
      expect(date, provider.groupedConversations.keys.single);
      expect(provider.findGroupedConversationById('c1')?.$1, date);
    }
  });

  test('ensureConversationGrouped does not duplicate an already grouped conversation', () {
    final convo = _conversationAt('c1', DateTime.utc(2026, 7, 18, 9));
    final provider = _providerWith([convo]);

    final date = provider.ensureConversationGrouped(convo);

    expect(provider.groupedConversations[date]!.where((c) => c.id == 'c1').length, 1);
  });

  test('a synced-conversation pointer keys on the local day group', () {
    // The sync-result path (conversation_sync_utils.dart): the pointer's key is
    // handed to `updateConversation` when the user taps a just-synced
    // conversation, so a raw-UTC key opened a day nothing is grouped under.
    for (var hour = 0; hour < 24; hour++) {
      final convo = _conversationAt('c1', DateTime.utc(2026, 7, 18, hour, 30));
      final provider = _providerWith([convo]);

      final pointer = ConversationSyncUtils.createPointer(convo, SyncedConversationType.newConversation);

      expect(pointer.key, provider.groupedConversations.keys.single, reason: 'startedAt hour $hour UTC');
    }
  });

  testWidgets('updateConvoDetailProvider selects the group key of the new conversation', (tester) async {
    // The onboarding hand-off (conversation_created_widget.dart): it selected a
    // day derived from raw UTC components, so the detail page it pushed had no
    // matching group.
    for (var hour = 0; hour < 24; hour++) {
      final convo = _conversationAt('c1', DateTime.utc(2026, 7, 18, hour, 30));
      final conversationProvider = _providerWith([]);
      final detailProvider = ConversationDetailProvider();
      addTearDown(detailProvider.dispose);
      detailProvider.conversationProvider = conversationProvider;

      late BuildContext capturedContext;
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationProvider>.value(value: conversationProvider),
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: detailProvider),
          ],
          child: Builder(
            builder: (context) {
              capturedContext = context;
              return const SizedBox.shrink();
            },
          ),
        ),
      );

      await updateConvoDetailProvider(capturedContext, convo);
      await tester.pumpAndSettle();

      expect(detailProvider.selectedDate, conversationProvider.groupedConversations.keys.single,
          reason: 'startedAt hour $hour UTC');
      expect(detailProvider.conversationOrNull?.id, 'c1');
    }
  });
}

ConversationProvider _providerWith(List<ServerConversation> conversations) {
  final provider = ConversationProvider(
    conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
    isSignedIn: () => true,
  );
  addTearDown(provider.dispose);
  provider.conversations = List.of(conversations);
  provider.groupConversationsByDate();
  return provider;
}

ServerConversation _conversationAt(String id, DateTime startedAt) {
  return ServerConversation(
    id: id,
    startedAt: startedAt,
    // Later than startedAt, so the last hour of the day still spans UTC midnight.
    createdAt: startedAt.add(const Duration(minutes: 45)),
    structured: Structured('Title', 'Overview'),
    status: ConversationStatus.completed,
  );
}
