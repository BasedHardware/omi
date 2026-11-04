import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/conversation_sync_utils.dart';

ServerConversation row(String id, {bool discarded = false, String? mergedInto, DateTime? at}) => ServerConversation(
    id: id,
    createdAt: at ?? DateTime.utc(2026, 10, 27),
    structured: Structured('title', ''),
    discarded: discarded,
    syncMergedInto: mergedInto);

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('merged marker survives decoding and cache/transcript projections', () {
    final donor = row('donor', mergedInto: 'live');
    expect(ServerConversation.fromJson(donor.toJson()).syncMergedInto, 'live');
    expect(donor.keepingTranscriptOf(row('donor')).syncMergedInto, 'live');
  });

  test('sync completion observes hidden donors before excluding their result pointers', () async {
    final seen = <String>[];
    final pointers = await ConversationSyncUtils.processConversationIds(
      newConversationIds: ['donor'],
      updatedConversationIds: ['old-redirect', 'live'],
      fetchConversation: (id) async => id == 'donor' ? row(id, discarded: true, mergedInto: 'live') : row('live'),
      onConversation: (id, value) => seen.add('$id:${value.id}'),
    );
    expect(seen, ['donor:donor', 'old-redirect:live', 'live:live']);
    expect(pointers.map((p) => p.conversation.id), ['live']);
  });

  test('a later hidden sync result supersedes the earlier visible result for the same ID', () async {
    var reads = 0;
    final pointers = await ConversationSyncUtils.processConversationIds(
      newConversationIds: ['donor'],
      updatedConversationIds: ['donor'],
      fetchConversation: (id) async => row(id, discarded: ++reads == 2),
    );
    expect(pointers, isEmpty);
  });

  test('a discarded update immediately disappears from Home groups', () async {
    final provider = ConversationProvider(isSignedIn: () => true);
    addTearDown(provider.dispose);
    await provider.addConversation(row('donor'));
    provider.updateConversationInSortedList(row('donor', discarded: true));
    expect(provider.groupedConversations.values.expand((g) => g), isEmpty);
  });

  test('merged donors disappear from every projection and stale sync upserts cannot restore them', () async {
    final provider = ConversationProvider(isSignedIn: () => true);
    addTearDown(provider.dispose);
    provider.showDiscardedConversations = true;
    await provider.addConversation(row('donor'));
    provider.searchedConversations = [row('donor')];
    provider.upsertConversation(row('donor', mergedInto: 'live'));
    provider.upsertConversation(row('donor'));
    expect(provider.conversations, isEmpty);
    expect(provider.searchedConversations, isEmpty);
    expect(provider.groupedConversations.values.expand((g) => g), isEmpty);
  });

  test('a redirect into the running episode removes the donor without adding a second live row', () async {
    final provider = ConversationProvider(isSignedIn: () => true);
    addTearDown(provider.dispose);
    await provider.addConversation(row('donor'));
    provider.searchedConversations = [row('donor')];
    provider.replaceBridgedConversation('donor', row('live')..status = ConversationStatus.in_progress);
    expect(provider.conversations, isEmpty);
    expect(provider.searchedConversations, isEmpty);
    expect(provider.groupedConversations.values.expand((g) => g), isEmpty);
  });

  test('incremental refresh drops a merged-away donor omitted from the server list', () async {
    final provider = ConversationProvider(
        isSignedIn: () => true, conversationListFetcher: () async => (items: [row('live')], ok: true));
    addTearDown(provider.dispose);
    await provider.addConversation(row('donor'));
    await provider.forceRefreshConversations();
    expect(provider.conversations.map((c) => c.id), ['live']);
    expect(provider.groupedConversations.values.expand((g) => g).map((c) => c.id), ['live']);
  });

  test('failed refresh retains rows and a live update wins over an older page', () async {
    var ok = false;
    final gate = Completer<void>();
    final provider = ConversationProvider(
        isSignedIn: () => true,
        conversationListFetcher: () async {
          if (ok) await gate.future;
          return (items: <ServerConversation>[], ok: ok);
        });
    addTearDown(provider.dispose);
    await provider.addConversation(row('kept'));
    await provider.forceRefreshConversations();
    expect(provider.conversations, hasLength(1));
    ok = true;
    final refreshing = provider.forceRefreshConversations();
    provider.upsertConversation(row('kept'));
    gate.complete();
    await refreshing;
    expect(provider.conversations.map((c) => c.id), ['kept']);
  });

  test('a full refresh page cannot delete older loaded pages', () async {
    final time = DateTime.utc(2026, 10, 27);
    final provider = ConversationProvider(
        isSignedIn: () => true,
        conversationListFetcher: () async =>
            (items: List.generate(50, (i) => row('recent$i', at: time.add(Duration(seconds: i)))), ok: true));
    addTearDown(provider.dispose);
    await provider.addConversation(row('older', at: time.subtract(const Duration(days: 1))));
    await provider.addConversation(row('omitted', at: time.add(const Duration(minutes: 1))));
    await provider.forceRefreshConversations();
    expect(provider.conversations.map((c) => c.id), contains('older'));
    expect(provider.conversations.map((c) => c.id), isNot(contains('omitted')));
  });
}
