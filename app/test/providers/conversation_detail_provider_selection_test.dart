import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('conversation getter resolves at every hour of the day, whatever the viewer timezone', () {
    // Regression for "Bad state: No conversation available": conversations are
    // grouped by the *local* calendar day of their effective date
    // (`conversationLocalDayKey` over startedAt ?? createdAt), and tapping a
    // list item selects that group's key. The getter used to validate the raw
    // UTC year/month/day instead, so it rejected a conversation that is present
    // in the selected group whenever the local day and the UTC day disagree —
    // an evening conversation for a UTC+ viewer, a post-UTC-midnight one for a
    // UTC- viewer — blanking the detail page (#10976).
    //
    // Sweeping every hour rather than pinning one timestamp keeps this honest
    // in whatever timezone the suite runs in; a single fixed hour only trips
    // the bug at some UTC offsets, which is how it reached main green.
    for (var hour = 0; hour < 24; hour++) {
      final startedAt = DateTime.utc(2026, 7, 18, hour, 30);
      final convo = ServerConversation(
        id: 'c1',
        startedAt: startedAt,
        // Later than startedAt, so the last hour still spans UTC midnight.
        createdAt: startedAt.add(const Duration(minutes: 45)),
        structured: Structured('Title', 'Overview'),
        status: ConversationStatus.completed,
      );

      final conversationProvider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        isSignedIn: () => true,
      );
      addTearDown(conversationProvider.dispose);
      conversationProvider.conversations = [convo];
      conversationProvider.groupConversationsByDate();

      // The date key the list item passes on tap is the group key.
      final groupDate = conversationProvider.groupedConversations.keys.single;

      final detailProvider = ConversationDetailProvider();
      addTearDown(detailProvider.dispose);
      detailProvider.conversationProvider = conversationProvider;

      detailProvider.updateConversation(convo.id, groupDate);

      expect(detailProvider.conversationOrNull, isNotNull, reason: 'startedAt ${startedAt.toIso8601String()}');
      expect(detailProvider.conversation.id, 'c1');
      expect(detailProvider.conversation.structured.title, 'Title');
    }
  });

  test('selected conversation is never replaced by another one in the day group', () {
    // The detail page drives delete, visibility and rename off this getter, so
    // resolving to a different conversation destroys or publicly shares the
    // wrong one. When the selected conversation leaves the group (deleted on
    // another device, merged away, or filtered out by the discarded/short
    // toggles) the getter must report a miss rather than substitute a sibling.
    final selected = _conversationAt('selected', DateTime.utc(2026, 7, 18, 9));
    final sibling = _conversationAt('sibling', DateTime.utc(2026, 7, 18, 11));

    final conversationProvider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(conversationProvider.dispose);
    conversationProvider.conversations = [selected, sibling];
    conversationProvider.groupConversationsByDate();

    final groupDate = conversationProvider.groupedConversations.keys.single;

    final detailProvider = ConversationDetailProvider();
    addTearDown(detailProvider.dispose);
    detailProvider.conversationProvider = conversationProvider;
    detailProvider.updateConversation(selected.id, groupDate);

    expect(detailProvider.conversation.id, 'selected');

    conversationProvider.conversations = [sibling];
    conversationProvider.groupConversationsByDate();

    // Previously this resolved to the surviving sibling and rebound the tracked
    // id to it, so a delete or visibility change hit the wrong conversation.
    expect(detailProvider.conversationOrNull?.id, 'selected');
    expect(detailProvider.conversationOrNull?.id, 'selected');
  });

  test('selected conversation survives a transient empty day group', () {
    // A refresh can momentarily empty the group; the page must keep showing the
    // conversation it was opened with instead of blanking or retargeting.
    final selected = _conversationAt('selected', DateTime.utc(2026, 7, 18, 9));

    final conversationProvider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(conversationProvider.dispose);
    conversationProvider.conversations = [selected];
    conversationProvider.groupConversationsByDate();

    final groupDate = conversationProvider.groupedConversations.keys.single;

    final detailProvider = ConversationDetailProvider();
    addTearDown(detailProvider.dispose);
    detailProvider.conversationProvider = conversationProvider;
    detailProvider.updateConversation(selected.id, groupDate);

    conversationProvider.conversations = [];
    conversationProvider.groupConversationsByDate();

    expect(detailProvider.conversationOrNull?.id, 'selected');
  });
}

ServerConversation _conversationAt(String id, DateTime startedAt) {
  return ServerConversation(
    id: id,
    startedAt: startedAt,
    createdAt: startedAt,
    structured: Structured(id, 'Overview'),
    status: ConversationStatus.completed,
  );
}
