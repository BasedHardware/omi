import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';

/// Records the single task-mutation path instead of hitting the network.
class _RecordingActionItemsProvider extends ActionItemsProvider {
  _RecordingActionItemsProvider(this._items)
      : super(
          getActionItems: ({
            int limit = 100,
            int offset = 0,
            bool? completed,
            String? conversationId,
            DateTime? startDate,
            DateTime? endDate,
          }) async =>
              const wire.GeneratedActionItemsResponse(actionItems: []),
        );

  final List<ActionItemWithMetadata> _items;
  final List<(String, bool)> updates = [];

  @override
  List<ActionItemWithMetadata> get actionItems => _items;

  @override
  bool get isLoading => false;

  @override
  Future<void> ensureLoaded({bool showShimmer = false}) async {}

  @override
  Future<void> updateActionItemState(ActionItemWithMetadata item, bool newState) async {
    updates.add((item.id, newState));
    notifyListeners();
  }
}

/// Records what the question card asked the chat to send.
class _RecordingMessageProvider extends MessageProvider {
  final List<String> sent = [];

  @override
  Future sendMessageStreamToServer(String text, {ChatPageContext? context}) async {
    sent.add(text);
  }
}

class _StubMemoriesProvider extends MemoriesProvider {
  _StubMemoriesProvider(this._memories);

  final List<Memory> _memories;

  @override
  List<Memory> get memories => _memories;

  @override
  bool get loading => false;

  @override
  Future<void> loadMemories({int limit = 100}) async {}
}

class _StubGoalsProvider extends GoalsProvider {
  @override
  bool get isLoading => false;
}

void main() {
  ActionItemWithMetadata task({required String id, bool completed = false}) {
    return wire.GeneratedActionItemResponse(
      id: id,
      description: 'Send the launch email',
      completed: completed,
    );
  }

  ServerMessage messageWithBlocks({String? selectedOptionId}) {
    return ServerMessage(
      'ai-1',
      DateTime.parse('2026-09-01T12:00:00Z'),
      'Here is what I found.',
      MessageSender.ai,
      MessageType.text,
      null,
      false,
      const [],
      const [],
      const [],
      contentBlocks: [
        {'type': 'text', 'id': 'block-text', 'text': 'Here is what I found.'},
        {'type': 'taskCard', 'id': 'block-task', 'taskId': 'task-1'},
        {'type': 'goalLink', 'id': 'block-goal', 'goalId': 'goal-1', 'summary': 'Ship the release'},
        {
          'type': 'captureLink',
          'id': 'block-capture',
          'conversationId': 'conversation-1',
          'summary': 'Monday standup',
        },
        {
          'type': 'conversationLink',
          'id': 'block-conversation',
          'conversationId': 'conversation-2',
          'summary': 'Weekly planning',
          'recommendedActionItems': [
            {'description': 'Draft the launch plan'},
          ],
        },
        {'type': 'memoryLink', 'id': 'block-memory', 'memoryId': 'memory-1', 'summary': 'Prefers dark mode'},
        {
          'type': 'questionCard',
          'id': 'block-question',
          'questionId': 'question-1',
          'text': 'What should we do next?',
          'subject': {'kind': 'goal', 'id': 'goal-1'},
          'options': [
            {'optionId': 'ship', 'label': 'Ship it', 'preparedAnswer': 'Ship it today'},
            {'optionId': 'later', 'label': 'Ask me later', 'preparedAnswer': 'Remind me tomorrow', 'defer': true},
          ],
          if (selectedOptionId != null) 'selectedOptionId': selectedOptionId,
        },
      ],
    );
  }

  Future<
      (
        _RecordingActionItemsProvider,
        _RecordingMessageProvider,
      )> pumpBlocks(
    WidgetTester tester, {
    required ServerMessage message,
    List<ActionItemWithMetadata> tasks = const [],
  }) async {
    final actionItems = _RecordingActionItemsProvider(tasks);
    final messages = _RecordingMessageProvider();
    final conversations = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversations.dispose);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<ActionItemsProvider>.value(value: actionItems),
          ChangeNotifierProvider<MessageProvider>.value(value: messages),
          ChangeNotifierProvider<GoalsProvider>(create: (_) => _StubGoalsProvider()),
          ChangeNotifierProvider<MemoriesProvider>(create: (_) => _StubMemoriesProvider(const [])),
          ChangeNotifierProvider.value(value: conversations),
          ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
        ],
        child: MaterialApp(
          theme: ThemeData.dark(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: SingleChildScrollView(
              child: AIMessage(
                message: message,
                sendMessage: (text) => messages.sendMessageStreamToServer(text),
                displayOptions: false,
                updateConversation: (_) {},
                setMessageNps: (int value, {String? reason}) {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    return (actionItems, messages);
  }

  testWidgets('every interactable block renders its keyed component', (tester) async {
    await pumpBlocks(
      tester,
      message: messageWithBlocks(),
      tasks: [task(id: 'task-1')],
    );

    expect(find.byKey(const Key('chat-block-taskCard-block-task')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-taskCard-block-task-toggle')), findsOneWidget);
    // No goal is loaded, so the goal link shows its unavailable state rather
    // than a button that cannot resolve.
    expect(find.byKey(const Key('chat-block-goalLink-block-goal-unavailable')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-captureLink-block-capture')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-captureLink-block-capture-open')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-conversationLink-block-conversation')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-conversationLink-block-conversation-open')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-memoryLink-block-memory-unavailable')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-questionCard-block-question')), findsOneWidget);

    // Message text is preserved beside the components.
    expect(find.textContaining('Here is what I found.'), findsWidgets);
    // Conversation link's recommended items are listed.
    expect(find.text('Draft the launch plan'), findsOneWidget);
    // Task description comes from the resolved task, not the block.
    expect(find.text('Send the launch email'), findsOneWidget);
  });

  testWidgets('an unresolved task shows the unavailable state', (tester) async {
    await pumpBlocks(tester, message: messageWithBlocks());

    expect(find.byKey(const Key('chat-block-taskCard-block-task-unavailable')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-taskCard-block-task-toggle')), findsNothing);
  });

  testWidgets('tapping the task checkbox toggles it through the tasks provider', (tester) async {
    final (actionItems, _) = await pumpBlocks(
      tester,
      message: messageWithBlocks(),
      tasks: [task(id: 'task-1')],
    );

    final toggle = find.byKey(const Key('chat-block-taskCard-block-task-toggle'));
    await tester.ensureVisible(toggle);
    await tester.tap(toggle);
    await tester.pump();

    expect(actionItems.updates, [('task-1', true)]);
  });

  testWidgets('tapping a question option sends its prepared answer', (tester) async {
    final (_, messages) = await pumpBlocks(tester, message: messageWithBlocks());

    final option = find.byKey(const Key('chat-block-questionCard-block-question-option-ship'));
    await tester.ensureVisible(option);
    await tester.tap(option);
    await tester.pump();

    expect(messages.sent, ['Ship it today']);
  });

  testWidgets('a deferral option sends its prepared answer too', (tester) async {
    final (_, messages) = await pumpBlocks(tester, message: messageWithBlocks());

    final option = find.byKey(const Key('chat-block-questionCard-block-question-option-later'));
    await tester.ensureVisible(option);
    await tester.tap(option);
    await tester.pump();

    expect(messages.sent, ['Remind me tomorrow']);
  });

  testWidgets('an answered question keeps only the chosen option, disabled', (tester) async {
    final (_, messages) = await pumpBlocks(
      tester,
      message: messageWithBlocks(selectedOptionId: 'ship'),
    );

    expect(find.byKey(const Key('chat-block-questionCard-block-question-option-later')), findsNothing);
    final chosen = find.byKey(const Key('chat-block-questionCard-block-question-option-ship'));
    expect(chosen, findsOneWidget);
    expect(tester.widget<OutlinedButton>(chosen).onPressed, isNull);
    expect(messages.sent, isEmpty);
  });

  testWidgets('a chrome-only message renders components instead of its fallback dump', (tester) async {
    final message = ServerMessage.fromJson({
      'id': 'ai-2',
      'created_at': '2026-09-01T12:00:00Z',
      'text': '',
      'sender': 'ai',
      'type': 'text',
      'content_blocks': [
        {'type': 'goalLink', 'id': 'block-goal', 'goalId': 'goal-1', 'summary': 'Ship the release'},
        {'type': 'taskCard', 'id': 'block-task', 'taskId': 'task-1'},
      ],
    });

    await pumpBlocks(tester, message: message, tasks: [task(id: 'task-1')]);

    expect(find.byKey(const Key('chat-block-taskCard-block-task')), findsOneWidget);
    expect(find.textContaining('Goal - Ship the release'), findsNothing);
  });
}
