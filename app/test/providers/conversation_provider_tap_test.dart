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
}
