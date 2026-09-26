import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';

class _SiriUndoHost extends SiriIndexApi {
  List<SiriConversation> restored = [];

  @override
  Future<void> upsertConversations(String uid, List<SiriConversation> rows) async {
    restored = rows;
  }

  @override
  Future<void> deleteEntities(String uid, String type, List<String> ids) async {}
}

/// D5: a conversation delete is held back long enough for its Undo toast to be real.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  late List<String> deleted;

  ConversationProvider makeProvider(List<ServerConversation> items) {
    deleted = [];
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: items, ok: true),
      isSignedIn: () => true,
    );
    provider.conversationDeleteFetcherOverride = (id) async {
      deleted.add(id);
      return true;
    };
    provider.conversations = [...items];
    provider.groupConversationsByDate();
    addTearDown(provider.dispose);
    return provider;
  }

  test('the pending window outlasts the Undo toast', () {
    expect(ConversationProvider.pendingDeleteWindow > OmiFeedbackTiming.undo, isTrue);
  });

  test('a local delete hides the row and holds the server delete back', () {
    final a = _conversation('a');
    final provider = makeProvider([a, _conversation('b')]);

    provider.deleteConversationLocally(a);

    expect(provider.conversations.map((c) => c.id), ['b']);
    expect(provider.groupedConversations.values.expand((l) => l).map((c) => c.id), ['b']);
    expect(provider.isDeletePending('a'), isTrue);
    expect(deleted, isEmpty);
  });

  test('undo restores the row and never deletes on the server', () async {
    final a = _conversation('a');
    final provider = makeProvider([a]);

    provider.deleteConversationLocally(a);
    provider.undoDeletedConversation(a);
    await Future<void>.delayed(Duration.zero);

    expect(provider.conversations.map((c) => c.id), ['a']);
    expect(provider.groupedConversations.values.expand((l) => l).map((c) => c.id), ['a']);
    expect(provider.isDeletePending('a'), isFalse);
    provider.commitPendingDelete('a');
    expect(deleted, isEmpty);
  });

  test('undo restores the conversation to Siri after the optimistic index delete', () async {
    final host = _SiriUndoHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
    final a = _conversation('a');
    final provider = makeProvider([a]);

    provider.deleteConversationLocally(a);
    await Future<void>.delayed(Duration.zero);
    provider.undoDeletedConversation(a);
    await Future<void>.delayed(Duration.zero);

    expect(host.restored.map((row) => row.id), ['a']);
  });

  test('committing sends the delete once and makes undo a no-op', () async {
    final a = _conversation('a');
    final provider = makeProvider([a]);

    provider.deleteConversationLocally(a);
    provider.commitPendingDelete('a');
    provider.commitPendingDelete('a');
    await Future<void>.delayed(Duration.zero);
    provider.undoDeletedConversation(a);

    expect(deleted, ['a']);
    expect(provider.conversations, isEmpty);
  });

  test('a regroup during the window does not bring the row back', () {
    final a = _conversation('a');
    final provider = makeProvider([a]);

    provider.deleteConversationLocally(a);
    provider.conversations = [a];
    provider.groupConversationsByDate();

    expect(provider.groupedConversations.values.expand((l) => l), isEmpty);
  });
}

ServerConversation _conversation(String id) => ServerConversation(
      id: id,
      createdAt: DateTime(2026, 9, 20, 10),
      structured: Structured('Title $id', 'Overview'),
      status: ConversationStatus.completed,
    );
