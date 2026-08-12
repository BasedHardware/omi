import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/conversation_sync_utils.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Regression coverage for #10980: call sites that look a conversation up by day
/// derived the key from the timestamp's raw UTC `year/month/day` instead of
/// [conversationLocalDayKey] over `startedAt ?? createdAt` — the key the groups
/// actually use. For any viewer off UTC the two disagree near local midnight, so
/// tapping a conversation link in chat did nothing and opening one from a memory
/// selected a day with no group.
///
/// Both cases now go through the provider, which is what these tests drive. The
/// hour sweep keeps them honest in whatever timezone the suite runs in: a single
/// pinned hour only trips the bug at some UTC offsets.
ServerConversation _conversationAt(DateTime startedAt) => ServerConversation(
  id: 'c1',
  startedAt: startedAt,
  // Later than startedAt, so the last hour of the sweep still spans UTC midnight.
  createdAt: startedAt.add(const Duration(minutes: 45)),
  structured: Structured('Title', 'Overview'),
  status: ConversationStatus.completed,
);

ConversationProvider _providerWith(List<ServerConversation> conversations) {
  final provider = ConversationProvider(
    conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
    isSignedIn: () => true,
  );
  provider.conversations = conversations;
  return provider;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('getConversationDateAndIndexById resolves the grouped conversation at every hour of the day', () {
    for (var hour = 0; hour < 24; hour++) {
      final startedAt = DateTime.utc(2026, 7, 18, hour, 30);
      final convo = _conversationAt(startedAt);

      final provider = _providerWith([convo]);
      addTearDown(provider.dispose);
      provider.groupConversationsByDate();

      final located = provider.getConversationDateAndIndexById(convo.id);
      final reason = 'startedAt ${startedAt.toIso8601String()}';

      expect(located, isNotNull, reason: reason);
      // The key must be the group key, i.e. what the list item would pass on tap.
      expect(located!.$1, provider.groupedConversations.keys.single, reason: reason);
      expect(provider.groupedConversations[located.$1]![located.$2].id, convo.id, reason: reason);
    }
  });

  test('getConversationDateAndIndexById returns null for an unknown or ungrouped conversation', () {
    final convo = _conversationAt(DateTime.utc(2026, 7, 18, 12, 0));
    final provider = _providerWith([convo]);
    addTearDown(provider.dispose);
    provider.groupConversationsByDate();

    expect(provider.getConversationDateAndIndexById('nope'), isNull);

    provider.groupedConversations = {};
    expect(provider.getConversationDateAndIndexById(convo.id), isNull);
  });

  test('the synced-conversation pointer carries the same key grouping uses', () {
    for (var hour = 0; hour < 24; hour++) {
      final startedAt = DateTime.utc(2026, 7, 18, hour, 30);
      final convo = _conversationAt(startedAt);
      final reason = 'startedAt ${startedAt.toIso8601String()}';

      final grouped = _providerWith([convo]);
      addTearDown(grouped.dispose);
      grouped.groupConversationsByDate();

      final pointer = ConversationSyncUtils.createPointer(convo, SyncedConversationType.newConversation);

      // The sync page hands this key to ConversationDetailProvider on tap; it
      // must address the group the conversation is actually in.
      expect(pointer.key, grouped.groupedConversations.keys.single, reason: reason);
      expect(grouped.groupedConversations[pointer.key]!.single.id, convo.id, reason: reason);
    }
  });

  test('ensureConversationInGroup files the conversation under the same key grouping uses', () {
    for (var hour = 0; hour < 24; hour++) {
      final startedAt = DateTime.utc(2026, 7, 18, hour, 30);
      final convo = _conversationAt(startedAt);
      final reason = 'startedAt ${startedAt.toIso8601String()}';

      // Nothing loaded yet — the memory tap path inserts the conversation itself.
      final empty = _providerWith([]);
      addTearDown(empty.dispose);
      final insertedKey = empty.ensureConversationInGroup(convo);
      expect(empty.groupedConversations[insertedKey]!.single.id, convo.id, reason: reason);

      // The key it chose must match what grouping would have produced.
      final grouped = _providerWith([convo]);
      addTearDown(grouped.dispose);
      grouped.groupConversationsByDate();
      expect(insertedKey, grouped.groupedConversations.keys.single, reason: reason);

      // Already grouped — same key, no duplicate row.
      expect(grouped.ensureConversationInGroup(convo), insertedKey, reason: reason);
      expect(grouped.groupedConversations[insertedKey]!.length, 1, reason: reason);
    }
  });
}
