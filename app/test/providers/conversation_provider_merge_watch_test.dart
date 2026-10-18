import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

/// A merge settles on the server; its push can arrive late or never (notifications off, a build
/// without push). The list must settle by itself instead of staying on "Merging…" until a refresh.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  ServerConversation conversation(String id, ConversationStatus status, {String title = 'Title'}) => ServerConversation(
        id: id,
        createdAt: DateTime.utc(2026, 9, 26, 10),
        structured: Structured(title, 'Overview'),
        status: status,
      );

  /// A provider whose server answers from [server] (id → lifecycle), counting list refreshes.
  ({ConversationProvider provider, List<int> refreshes}) merging(
    Map<String, ({ServerConversation? item, bool ok})> server,
  ) {
    final refreshes = <int>[0];
    final provider = ConversationProvider(
      conversationListFetcher: () async {
        refreshes[0]++;
        return (items: <ServerConversation>[], ok: true);
      },
      conversationLifecycleFetcher: (id) async => server[id]!,
      isSignedIn: () => true,
    )
      ..mergeProbeInterval = const Duration(milliseconds: 10)
      ..conversations = [
        conversation('a', ConversationStatus.merging),
        conversation('b', ConversationStatus.merging),
      ]
      ..mergingConversationIds = {'a', 'b'};
    return (provider: provider, refreshes: refreshes);
  }

  Future<void> ticks([int count = 4]) => Future<void>.delayed(Duration(milliseconds: 12 * count));

  test('without the push, the rows settle once the server finishes the merge', () async {
    final server = <String, ({ServerConversation? item, bool ok})>{
      'a': (item: conversation('a', ConversationStatus.merging), ok: true),
      'b': (item: conversation('b', ConversationStatus.merging), ok: true),
    };
    final (:provider, :refreshes) = merging(server);
    addTearDown(provider.dispose);
    provider.watchMerge(['a', 'b']);

    await ticks();
    expect(provider.mergingConversationIds, {'a', 'b'}, reason: 'still merging on the server');

    // The merge lands: "a" holds the merged conversation, "b" is gone.
    server['a'] = (item: conversation('a', ConversationStatus.completed, title: 'Merged'), ok: true);
    server['b'] = (item: null, ok: true);
    await ticks();
    expect(provider.mergingConversationIds, isEmpty);
    expect(provider.conversations.map((c) => c.id), ['a']);
    expect(provider.conversations.single.structured.title, 'Merged');
    expect(refreshes[0], 0, reason: 'settled from what it read, no refresh needed');
  });

  test('a network hiccup is not mistaken for a finished merge', () async {
    final server = <String, ({ServerConversation? item, bool ok})>{
      'a': (item: null, ok: false),
      'b': (item: null, ok: false),
    };
    final (:provider, refreshes: _) = merging(server);
    addTearDown(provider.dispose);
    provider.watchMerge(['a', 'b']);
    await ticks();
    expect(provider.mergingConversationIds, {'a', 'b'});
    expect(provider.conversations, hasLength(2));
  });

  test('the push settling it first ends the probing', () async {
    var probes = 0;
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      conversationLifecycleFetcher: (id) async {
        probes++;
        return (item: conversation(id, ConversationStatus.merging), ok: true);
      },
      isSignedIn: () => true,
    )
      ..mergeProbeInterval = const Duration(milliseconds: 10)
      ..mergingConversationIds = {'a', 'b'};
    addTearDown(provider.dispose);
    provider.watchMerge(['a', 'b']);
    await ticks(2);
    provider.mergingConversationIds.clear(); // as onMergeCompleted does
    await ticks(2);
    final after = probes;
    await ticks(4);
    expect(probes, after, reason: 'no probes once the merge is settled');
  });

  test('a result it cannot read (locked) hands the rows back to a list refresh', () async {
    final server = <String, ({ServerConversation? item, bool ok})>{
      'a': (item: null, ok: true), // 402 locked, like 404, is a settled answer with nothing to show
      'b': (item: null, ok: true),
    };
    final (:provider, :refreshes) = merging(server);
    addTearDown(provider.dispose);
    provider.watchMerge(['a', 'b']);
    await ticks();
    expect(provider.mergingConversationIds, isEmpty);
    expect(refreshes[0], greaterThanOrEqualTo(1));
  });

  test('a merge that never settles is handed back to the list after the limit', () async {
    final server = <String, ({ServerConversation? item, bool ok})>{
      'a': (item: conversation('a', ConversationStatus.merging), ok: true),
      'b': (item: conversation('b', ConversationStatus.merging), ok: true),
    };
    final (:provider, :refreshes) = merging(server);
    addTearDown(provider.dispose);
    provider.mergeProbeLimit = const Duration(milliseconds: 30);
    provider.watchMerge(['a', 'b']);
    await ticks(8);
    expect(provider.mergingConversationIds, isEmpty, reason: 'never left on Merging…');
    expect(refreshes[0], greaterThanOrEqualTo(1));
  });
}
