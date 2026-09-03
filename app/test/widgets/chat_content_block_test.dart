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
  }) async {
    final conversationProvider = ConversationProvider(isSignedIn: () => false);
    addTearDown(conversationProvider.dispose);
    final memoriesProvider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult(memories, true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
      editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: true),
    );
    addTearDown(memoriesProvider.dispose);
    await memoriesProvider.loadMemories();

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
              child: AIMessage(
                message: message,
                sendMessage: sendMessage ?? (_) {},
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

  testWidgets('a plain answer with no blocks gains neither a chip nor a card', (tester) async {
    await pumpMessage(tester, message: _aiMessage(text: 'You met Priya on Tuesday.', type: MessageType.text));

    expect(find.byKey(const Key('chat_followup_chip')), findsNothing);
    expect(find.byType(MemoryReviewCard), findsNothing);
  });
}
