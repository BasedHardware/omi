import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/widgets/components/memory_review_card.dart';

ServerMessage _aiMessage({
  required String text,
  required MessageType type,
  List<Map<String, dynamic>> contentBlocks = const [],
}) {
  return ServerMessage(
    'ai-1',
    DateTime.parse('2026-09-01T23:00:00Z'),
    text,
    MessageSender.ai,
    type,
    null,
    false,
    const [],
    const [],
    const [],
    contentBlocks: contentBlocks,
  );
}

/// Built through the wire decoder, so the content-block fallback that fills an
/// empty `text` actually runs. The direct constructor above bypasses it.
ServerMessage _decodedAiMessage({
  required String text,
  required String type,
  List<Map<String, dynamic>> contentBlocks = const [],
}) {
  return ServerMessage.fromJson({
    'id': 'ai-1',
    'created_at': '2026-09-01T23:00:00Z',
    'text': text,
    'sender': 'ai',
    'type': type,
    'content_blocks': contentBlocks,
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'chat-block-user'});
    await SharedPreferencesUtil.init();
  });

  Future<void> pumpMessage(
    WidgetTester tester, {
    required ServerMessage message,
    void Function(String)? sendMessage,
    List<Memory> memories = const [],
    bool preloadMemories = true,
    VoidCallback? onFetchMemories,
    bool displayOptions = false,
    double? messageWidth,
  }) async {
    final conversationProvider = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversationProvider.dispose);
    final memoriesProvider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        onFetchMemories?.call();
        return GetMemoriesResult(memories, true);
      },
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
      editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: true),
    );
    addTearDown(memoriesProvider.dispose);
    if (preloadMemories) await memoriesProvider.loadMemories();

    final messageWidget = AIMessage(
      message: message,
      sendMessage: sendMessage ?? (_) {},
      displayOptions: displayOptions,
      updateConversation: (_) {},
      setMessageNps: (int value, {String? reason}) {},
    );
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider.value(value: conversationProvider),
          ChangeNotifierProvider.value(value: memoriesProvider),
          ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
        ],
        child: MaterialApp(
          theme: ThemeData.dark(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: SingleChildScrollView(
              child: messageWidth == null ? messageWidget : SizedBox(width: messageWidth, child: messageWidget),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  testWidgets('a follow-up block renders one chip that sends its own words', (tester) async {
    final sent = <String>[];
    await pumpMessage(
      tester,
      message: _aiMessage(
        text: 'You met Priya on Tuesday.',
        type: MessageType.text,
        contentBlocks: const [
          {'type': 'followUp', 'id': 'ai-1:followup', 'text': 'Want the rest of what she said?'},
        ],
      ),
      sendMessage: sent.add,
    );

    final chip = find.byKey(const Key('chat_followup_chip'));
    expect(chip, findsOneWidget);
    expect(find.text('Want the rest of what she said?'), findsOneWidget);

    await tester.tap(chip);
    await tester.pump();

    expect(sent, ['Want the rest of what she said?']);
  });

  testWidgets('keeps prose text blocks beside cards in a structured fallback', (tester) async {
    await pumpMessage(
      tester,
      message: _decodedAiMessage(
        text: '',
        type: 'text',
        contentBlocks: const [
          {'type': 'text', 'id': 'block-text', 'text': 'The deadline is Friday.'},
          {
            'type': 'conversationLink',
            'id': 'block-conversation',
            'conversationId': 'conversation-1',
            'summary': 'Weekly planning',
          },
        ],
      ),
    );

    expect(find.byKey(const ValueKey('chat-block-text-block-text')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-conversationLink-block-conversation')), findsOneWidget);
  });

  testWidgets('keeps synthesized lines beside cards in a structured fallback', (tester) async {
    await pumpMessage(
      tester,
      message: _decodedAiMessage(
        text: '',
        type: 'text',
        contentBlocks: const [
          {'type': 'thinking', 'id': 'block-thinking', 'text': 'Checking the latest notes.'},
          {
            'type': 'toolCall',
            'id': 'block-tool',
            'name': 'search_knowledge',
            'output': 'Found 3 matching notes.',
          },
          {
            'type': 'citation',
            'id': 'block-citation',
            'ordinal': 0,
            'kind': 'conversation',
            'sourceId': 'conversation-1',
            'title': 'Weekly planning',
          },
          {'type': 'futureBlock', 'id': 'block-unknown', 'title': 'A future card'},
          {
            'type': 'conversationLink',
            'id': 'block-conversation',
            'conversationId': 'conversation-1',
            'summary': 'Weekly planning',
          },
        ],
      ),
    );

    expect(find.byKey(const ValueKey('chat-block-fallback-block-thinking')), findsOneWidget);
    expect(find.byKey(const ValueKey('chat-block-fallback-block-tool')), findsOneWidget);
    expect(find.byKey(const ValueKey('chat-block-fallback-block-citation')), findsOneWidget);
    expect(find.byKey(const ValueKey('chat-block-fallback-block-unknown')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-conversationLink-block-conversation')), findsOneWidget);
  });

  testWidgets('keeps a malformed raw block fallback beside a valid card', (tester) async {
    await pumpMessage(
      tester,
      message: _decodedAiMessage(
        text: '',
        type: 'text',
        contentBlocks: const [
          // Missing id and wrong field types make this block intentionally
          // undecodable; its canonical raw fallback must still be visible.
          {
            'type': 'toolCall',
            'name': 42,
            'output': {'unexpected': true}
          },
          {
            'type': 'conversationLink',
            'id': 'block-conversation',
            'conversationId': 'conversation-1',
            'summary': 'Weekly planning',
          },
        ],
      ),
    );

    expect(find.byKey(const ValueKey('chat-block-fallback-0')), findsOneWidget);
    expect(find.byKey(const Key('chat-block-conversationLink-block-conversation')), findsOneWidget);
  });

  testWidgets('structured fallback markdown fills the available message width', (tester) async {
    await pumpMessage(
      tester,
      messageWidth: 320,
      message: _decodedAiMessage(
        text: '',
        type: 'text',
        contentBlocks: const [
          {'type': 'thinking', 'id': 'block-thinking', 'text': 'Checking the latest notes.'},
          {
            'type': 'conversationLink',
            'id': 'block-conversation',
            'conversationId': 'conversation-1',
            'summary': 'Weekly planning',
          },
        ],
      ),
    );

    expect(tester.getSize(find.byKey(const ValueKey('chat-block-fallback-block-thinking'))).width, 320);
  });

  testWidgets('does not duplicate fallback prose in a day summary', (tester) async {
    final message = _decodedAiMessage(
      text: '',
      type: 'day_summary',
      contentBlocks: const [
        {'type': 'text', 'id': 'block-text', 'text': 'The deadline is Friday.'},
        {
          'type': 'conversationLink',
          'id': 'block-conversation',
          'conversationId': 'conversation-1',
          'summary': 'Weekly planning',
        },
      ],
    );
    expect(message.text, contains('The deadline is Friday.'));
    await pumpMessage(
      tester,
      message: message,
    );

    expect(find.byKey(const ValueKey('chat-block-text-block-text')), findsNothing);
  });

  testWidgets('does not duplicate fallback prose in initial options', (tester) async {
    final message = _decodedAiMessage(
      text: '',
      type: 'text',
      contentBlocks: const [
        {'type': 'text', 'id': 'block-text', 'text': 'The deadline is Friday.'},
        {
          'type': 'conversationLink',
          'id': 'block-conversation',
          'conversationId': 'conversation-1',
          'summary': 'Weekly planning',
        },
      ],
    );
    expect(message.text, contains('The deadline is Friday.'));
    await pumpMessage(
      tester,
      displayOptions: true,
      message: message,
    );

    expect(find.byKey(const ValueKey('chat-block-text-block-text')), findsNothing);
  });

  testWidgets('cold memory links hydrate before the Memories page is opened', (tester) async {
    var fetches = 0;
    final memory = Memory(
      id: 'memory-cold',
      uid: 'chat-block-user',
      content: 'A cold-chat memory',
      category: MemoryCategory.manual,
      createdAt: DateTime(2026, 9, 1),
      updatedAt: DateTime(2026, 9, 1),
      visibility: MemoryVisibility.private,
    );
    await pumpMessage(
      tester,
      preloadMemories: false,
      onFetchMemories: () => fetches++,
      memories: [memory],
      message: _decodedAiMessage(
        text: '',
        type: 'text',
        contentBlocks: const [
          {'type': 'memoryLink', 'id': 'block-memory', 'memoryId': 'memory-cold', 'summary': 'A cold-chat memory'},
        ],
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(fetches, 1);
    expect(find.byKey(const Key('chat-block-memoryLink-block-memory-open')), findsOneWidget);
  });

  testWidgets('unknown agent terminal states do not render as completed', (tester) async {
    await pumpMessage(
      tester,
      message: _decodedAiMessage(
        text: '',
        type: 'text',
        contentBlocks: const [
          {
            'type': 'agentCompletion',
            'id': 'block-agent',
            'runId': 'run-1',
            'sessionId': 'session-1',
            'title': 'Run the report',
            'output': 'The run was orphaned.',
            'status': 'orphaned',
          },
        ],
      ),
    );

    expect(find.text('Failed'), findsOneWidget);
    expect(find.byIcon(Icons.error_outline), findsOneWidget);
    expect(find.byIcon(Icons.check_circle_outline), findsNothing);
  });

  testWidgets('cancelled and timed-out agent states use their localized labels', (tester) async {
    await pumpMessage(
      tester,
      message: _decodedAiMessage(
        text: '',
        type: 'text',
        contentBlocks: const [
          {
            'type': 'agentCompletion',
            'id': 'block-cancelled',
            'title': 'Cancelled run',
            'output': 'The run was stopped.',
            'status': 'stopped',
          },
          {
            'type': 'agentCompletion',
            'id': 'block-timeout',
            'title': 'Timed out run',
            'output': 'The run timed out.',
            'status': 'timed_out',
          },
        ],
      ),
    );

    expect(find.text('Cancelled'), findsOneWidget);
    expect(find.text('Timed out'), findsOneWidget);
    expect(find.byIcon(Icons.cancel_outlined), findsOneWidget);
    expect(find.byIcon(Icons.error_outline), findsOneWidget);
  });

  testWidgets('a day summary carrying a memoryReviewCard renders the review rows', (tester) async {
    await pumpMessage(
      tester,
      message: _aiMessage(
        text: 'A busy day.',
        type: MessageType.daySummary,
        contentBlocks: const [
          {
            'type': 'memoryReviewCard',
            'id': 'summary-1:memories',
            'summaryId': 'summary-1',
            'date': '2026-09-01',
            'items': [
              {'memoryId': 'mem-1', 'content': 'Prefers async standups', 'category': 'work'},
            ],
          },
        ],
      ),
      memories: [
        Memory(
          id: 'mem-1',
          uid: 'chat-block-user',
          content: 'Prefers async standups',
          category: MemoryCategory.system,
          createdAt: DateTime.utc(2026, 9, 1),
          updatedAt: DateTime.utc(2026, 9, 1),
          visibility: MemoryVisibility.private,
        ),
      ],
    );

    expect(find.byType(MemoryReviewCard), findsOneWidget);
    expect(find.text('Things I learned today'), findsOneWidget);
    expect(find.byKey(const Key('memory_review_accept_mem-1')), findsOneWidget);
    expect(find.byKey(const Key('memory_review_reject_mem-1')), findsOneWidget);
    expect(find.byKey(const Key('memory_review_fix_mem-1')), findsOneWidget);
  });

  testWidgets('an answer that is only a follow-up asks it once, as the chip', (tester) async {
    // With no prose of its own the message text falls back to its content
    // blocks. The chip renders the question natively, so a prose copy would put
    // the same words on screen twice.
    await pumpMessage(
      tester,
      message: _decodedAiMessage(
        text: '',
        type: 'text',
        contentBlocks: const [
          {'type': 'followUp', 'id': 'ai-1:followup', 'text': 'Want the rest of what she said?'},
        ],
      ),
    );

    expect(find.byKey(const Key('chat_followup_chip')), findsOneWidget);
    expect(find.text('Want the rest of what she said?'), findsOneWidget);
  });

  testWidgets('a memoryReviewCard heading is not also rendered as prose', (tester) async {
    await pumpMessage(
      tester,
      message: _decodedAiMessage(
        text: '',
        type: 'day_summary',
        contentBlocks: const [
          {
            'type': 'memoryReviewCard',
            'id': 'summary-2:memories',
            'items': [
              {'memoryId': 'mem-dup', 'content': 'Prefers async standups', 'category': 'work'},
            ],
          },
        ],
      ),
      memories: [
        Memory(
          id: 'mem-dup',
          uid: 'chat-block-user',
          content: 'Prefers async standups',
          category: MemoryCategory.system,
          createdAt: DateTime.utc(2026, 9, 1),
          updatedAt: DateTime.utc(2026, 9, 1),
          visibility: MemoryVisibility.private,
        ),
      ],
    );

    expect(find.byType(MemoryReviewCard), findsOneWidget);
    expect(find.text('Things I learned today'), findsOneWidget);
  });

  testWidgets('a memoryReviewCard with no usable items leaves no heading behind', (tester) async {
    await pumpMessage(
      tester,
      message: _decodedAiMessage(
        text: '',
        type: 'day_summary',
        contentBlocks: const [
          {'type': 'memoryReviewCard', 'id': 'summary-3:memories', 'items': []},
        ],
      ),
    );

    expect(find.byType(MemoryReviewCard), findsNothing);
    expect(find.text('Things I learned today'), findsNothing);
  });

  testWidgets('a plain answer with no blocks gains neither a chip nor a card', (tester) async {
    await pumpMessage(
      tester,
      message: _aiMessage(text: 'You met Priya on Tuesday.', type: MessageType.text),
    );

    expect(find.byKey(const Key('chat_followup_chip')), findsNothing);
    expect(find.byType(MemoryReviewCard), findsNothing);
  });
}
