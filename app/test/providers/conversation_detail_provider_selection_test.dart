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
}
