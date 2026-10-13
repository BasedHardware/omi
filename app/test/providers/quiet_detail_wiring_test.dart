import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('detail ignores wiring noise and propagates mutable catalog and selected detail edits', () {
    final apps = AppProvider();
    final conversations = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    final detail = ConversationDetailProvider();
    addTearDown(detail.dispose);
    addTearDown(apps.dispose);
    addTearDown(conversations.dispose);
    // Unobserved startup must not resolve a selection or emit product state.
    detail.setProviders(apps, conversations);
    var notifications = 0;
    detail.addListener(() => notifications++);
    detail.setProviders(apps, conversations);
    expect(notifications, 0);
    notifications = 0;
    for (var i = 0; i < 4; i++) {
      detail.setProviders(apps, conversations);
    }
    expect(notifications, 0);
    final app = App(
        id: 'a',
        name: 'Before',
        author: 'test',
        description: '',
        image: '',
        capabilities: {'memories'},
        status: 'approved',
        category: 'test',
        approved: true,
        ratingCount: 0,
        enabled: true,
        deleted: false,
        isPaid: false,
        isUserPaid: false);
    apps.apps = [app];
    detail.setProviders(apps, conversations);
    expect(notifications, 1);
    app.name = 'After';
    detail.setProviders(apps, conversations);
    expect(notifications, 2);
    final selected = ServerConversation(
        id: 'selected', createdAt: DateTime(2026, 10, 13), structured: Structured('Before', 'Overview'));
    conversations.conversations = [selected];
    conversations.groupConversationsByDate();
    detail.updateConversation(selected.id, conversations.groupedConversations.keys.single);
    detail.setProviders(apps, conversations);
    notifications = 0;
    selected.structured.title = 'After';
    detail.setProviders(apps, conversations);
    expect(notifications, 1);
    conversations.isLoadingConversations = true;
    detail.setProviders(apps, conversations);
    expect(notifications, 1);
    conversations.memoriesToDelete[selected.id] = selected;
    detail.setProviders(apps, conversations);
    expect(notifications, 2);
  });
}
