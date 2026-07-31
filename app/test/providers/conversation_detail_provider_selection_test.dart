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

  test('conversation getter resolves when startedAt and createdAt fall on different days', () {
    // Regression for "Bad state: No conversation available": conversations are
    // grouped by their effective date (startedAt ?? createdAt), and tapping a
    // list item selects that group's date. When startedAt lands on an earlier
    // calendar day than createdAt (session spanning midnight / timezone edge),
    // the detail provider must still resolve the conversation instead of
    // throwing from the non-null `conversation` getter.
    final convo = ServerConversation(
      id: 'c1',
      startedAt: DateTime.utc(2026, 7, 18, 23, 30),
      createdAt: DateTime.utc(2026, 7, 19, 0, 15),
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

    expect(detailProvider.conversationOrNull, isNotNull);
    expect(detailProvider.conversation.id, 'c1');
    expect(detailProvider.conversation.structured.title, 'Title');
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
