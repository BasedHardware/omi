import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/gen/action_items_folders_wire.g.dart' as wire;
import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/chat_message_plan.dart';
import 'package:omi/pages/chat/widgets/content_blocks/chat_content_block_list.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/widgets/components/chat_evidence_card.dart';
import 'package:omi/widgets/components/memory_review_card.dart';

/// The fixtures of server_message_content_blocks_test and chat_content_block_parity_test, decoded
/// through the wire path so the structured fallback text is synthesized as in production.
ServerMessage _message({
  String text = '',
  String type = 'text',
  List<Map<String, dynamic>> blocks = const [],
  List<Map<String, dynamic>> memories = const [],
  Map<String, dynamic>? evidence,
}) {
  return ServerMessage.fromJson({
    'id': 'message-1',
    'created_at': '2026-09-02T12:00:00Z',
    'text': text,
    'sender': 'ai',
    'type': type,
    'content_blocks': blocks,
    'memories': memories,
    if (evidence != null) 'evidence': evidence,
  });
}

const _goal = {'id': 'b-goal', 'type': 'goalLink', 'goalId': 'goal-1', 'summary': 'Make Omi Great Again'};
const _task = {'id': 'b-task', 'type': 'taskCard', 'taskId': 'task-1'};
const _review = {
  'type': 'memoryReviewCard',
  'id': 'summary-1:memories',
  'summaryId': 'summary-1',
  'date': '2026-09-01',
  'items': [
    {'memoryId': 'mem-1', 'content': 'Prefers async standups', 'category': 'work'},
  ],
};
const _citation = {
  'id': 'conversation-1',
  'created_at': '2026-09-01T10:00:00Z',
  'structured': {'title': 'Standup', 'emoji': '🗓'},
};
Map<String, dynamic> _evidence(List<String> kinds) => {
      'schema_version': 1,
      'request_id': 'request-1',
      'references': [
        for (final (index, kind) in kinds.indexed)
          {
            'id': 'ref-$index',
            'kind': kind,
            'state': 'available',
            'conversation_id': 'conversation-1',
            'frame_id': 'frame-1',
          },
      ],
    };

class _Tasks extends ActionItemsProvider {
  _Tasks()
      : super(
          getActionItems: ({
            int limit = 100,
            int offset = 0,
            bool? completed,
            String? conversationId,
            DateTime? startDate,
            DateTime? endDate,
            DateTime? dueStartDate,
            DateTime? dueEndDate,
          }) async =>
              const wire.GeneratedActionItemsResponse(actionItems: []),
        );

  @override
  List<ActionItemWithMetadata> get actionItems => const [];

  @override
  Future<void> ensureLoaded({bool showShimmer = false}) async {}
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'plan-user'});
    await SharedPreferencesUtil.init();
  });

  group('ChatMessagePlan.of', () {
    test('a body that is only the blocks fallback is replaced by the blocks', () {
      final message = _message(blocks: [_goal, _task, _task]);
      final plan = ChatMessagePlan.of(message, displayOptions: false);
      expect(plan.layout, ChatMessageLayout.blocks);
      expect(plan.parts, [ChatMessagePartKind.blocksReplaceBody]);
      expect(plan.blockEntries.map((entry) => entry.component?.runtimeType.toString()), [
        'GoalLinkContentBlock',
        'TaskCardContentBlock',
        'TaskCardContentBlock',
      ]);
    });

    test('prose the model wrote keeps its body and appends the cards after the action bar', () {
      final message = _message(text: 'Start with the hackathon.', blocks: [_task]);
      final plan = ChatMessagePlan.of(message, displayOptions: false);
      expect(plan.layout, ChatMessageLayout.normal);
      expect(plan.parts, [ChatMessagePartKind.body, ChatMessagePartKind.actionBar, ChatMessagePartKind.blocks]);
      expect(plan.blockEntries.single.text, isNull, reason: 'a normal body is not repeated as block prose');
    });

    test('the first message offers the starters and keeps its body', () {
      final message = _message(blocks: [_goal, _task]);
      final plan = ChatMessagePlan.of(message, displayOptions: true);
      expect(plan.layout, ChatMessageLayout.initialOptions);
      expect(plan.parts, [ChatMessagePartKind.body, ChatMessagePartKind.initialOptions, ChatMessagePartKind.blocks]);
      expect(ChatMessagePlan.of(message, displayOptions: false).has(ChatMessagePartKind.initialOptions), isFalse);
    });

    test('memory citations keep the normal body and strip conversation evidence they already list', () {
      final message = _message(
        text: 'You met twice.',
        memories: [_citation],
        evidence: _evidence(['conversation_summary', 'conversation_segment']),
      );
      final plan = ChatMessagePlan.of(message, displayOptions: false);
      expect(plan.layout, ChatMessageLayout.citations);
      expect(plan.parts, [ChatMessagePartKind.body, ChatMessagePartKind.actionBar, ChatMessagePartKind.citations]);
      expect(plan.evidence, isNull);

      final mixed = _message(text: 'You met twice.', memories: [_citation], evidence: _evidence(['keyframe']));
      expect(ChatMessagePlan.of(mixed, displayOptions: false).evidence!.references.single.kind.wireValue, 'keyframe');
    });

    test('a day summary keeps its own layout and its review card, which waits for the stream', () {
      final message = _message(text: 'A busy day.', type: 'day_summary', blocks: [_review]);
      expect(ChatMessagePlan.of(message, displayOptions: false).parts,
          [ChatMessagePartKind.daySummary, ChatMessagePartKind.reviewCard]);
      expect(ChatMessagePlan.of(message, displayOptions: false, showTypingIndicator: true).parts,
          [ChatMessagePartKind.daySummary]);
    });

    test('a follow-up block is composer chrome, never message content', () {
      final message = _message(text: 'Here it is.', blocks: [
        {'type': 'followUp', 'id': 'f-1', 'text': 'Want the rest?'},
      ]);
      final plan = ChatMessagePlan.of(message, displayOptions: false);
      expect(plan.parts, [ChatMessagePartKind.body, ChatMessagePartKind.actionBar]);
    });

    test('a streaming reply shows its steps and a chart placeholder, then the chart and actions', () {
      final message = _message()..thinkings = ['Making a chart'];
      final streaming = ChatMessagePlan.of(message, displayOptions: false, showTypingIndicator: true);
      expect(streaming.parts, [ChatMessagePartKind.activity, ChatMessagePartKind.chartPlaceholder]);
      expect(streaming.working, isTrue);
      message
        ..text = 'Done.'
        ..chartData = ChartData('bar', 'Steps', [
          ChartDataset('Steps', [ChartDataPoint('Mon', 3)])
        ]);
      expect(ChatMessagePlan.of(message, displayOptions: false).parts, [
        ChatMessagePartKind.activity,
        ChatMessagePartKind.body,
        ChatMessagePartKind.chart,
        ChatMessagePartKind.actionBar,
      ]);
    });

    test('a part its layout does not render, or one out of order, throws', () {
      final message = _message(text: 'A busy day.', type: 'day_summary');
      expect(
        () => ChatMessagePlan.fromParts(message, ChatMessageLayout.daySummary, [ChatMessagePartKind.initialOptions]),
        throwsArgumentError,
      );
      expect(
        () => ChatMessagePlan.fromParts(
            message, ChatMessageLayout.normal, [ChatMessagePartKind.actionBar, ChatMessagePartKind.body]),
        throwsArgumentError,
      );
      expect(
        ChatMessagePlan.fromParts(message, ChatMessageLayout.daySummary, [ChatMessagePartKind.daySummary]).parts,
        [ChatMessagePartKind.daySummary],
      );
    });
  });

  group('buildMessageWidget draws the plan', () {
    Future<void> pump(WidgetTester tester, ServerMessage message, {required bool displayOptions}) async {
      final conversations = ConversationProvider(isSignedIn: () => false);
      addTearDown(conversations.dispose);
      final memories = MemoriesProvider(
        fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
            const GetMemoriesResult([], true),
        fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
            const GetLedgerHistoryResult([], supported: true),
      );
      addTearDown(memories.dispose);
      await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<ActionItemsProvider>(create: (_) => _Tasks()),
          ChangeNotifierProvider<GoalsProvider>(create: (_) => GoalsProvider()),
          ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
          ChangeNotifierProvider.value(value: conversations),
          ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(
            body: SingleChildScrollView(
              child: Builder(
                builder: (context) => buildMessageWidget(
                  message,
                  (_) {},
                  false,
                  displayOptions,
                  null,
                  (_) {},
                  (int value, {String? reason}) {},
                ),
              ),
            ),
          ),
        ),
      ));
      await tester.pump();
    }

    final fixtures = <String, (ServerMessage, bool)>{
      'blocks replace the body': (_message(blocks: [_goal, _task, _task]), false),
      'prose with cards': (_message(text: 'Start with the hackathon.', blocks: [_task]), false),
      'first message': (_message(blocks: [_goal, _task]), true),
      'citations': (
        _message(text: 'You met twice.', memories: [_citation], evidence: _evidence(['conversation_summary'])),
        false
      ),
      'citations with screen evidence': (
        _message(text: 'You met twice.', memories: [_citation], evidence: _evidence(['screen'])),
        false
      ),
      'day summary with review': (_message(text: 'A busy day.', type: 'day_summary', blocks: [_review]), false),
      'follow-up only': (
        _message(text: 'Here it is.', blocks: [
          {'type': 'followUp', 'id': 'f-1', 'text': 'Want the rest?'},
        ]),
        false
      ),
    };

    for (final MapEntry(key: name, value: (message, displayOptions)) in fixtures.entries) {
      testWidgets(name, (tester) async {
        final plan = ChatMessagePlan.of(message, displayOptions: displayOptions);
        await pump(tester, message, displayOptions: displayOptions);
        final layoutWidget = switch (plan.layout) {
          ChatMessageLayout.blocks => ChatContentBlockList,
          ChatMessageLayout.citations => MemoriesMessageWidget,
          ChatMessageLayout.daySummary => DaySummaryWidget,
          ChatMessageLayout.initialOptions => InitialMessageWidget,
          ChatMessageLayout.normal => NormalMessageWidget,
        };
        expect(find.byType(layoutWidget), findsOneWidget);
        final blocks = plan.has(ChatMessagePartKind.blocks) || plan.has(ChatMessagePartKind.blocksReplaceBody);
        expect(find.byType(ChatContentBlockList), blocks ? findsOneWidget : findsNothing);
        expect(find.byType(MemoryReviewCard), plan.has(ChatMessagePartKind.reviewCard) ? findsOneWidget : findsNothing);
        expect(find.byType(ChatEvidenceReferenceList),
            plan.has(ChatMessagePartKind.evidence) ? findsOneWidget : findsNothing);
        expect(
            find.byType(MessageActionBar),
            plan.has(ChatMessagePartKind.actionBar) || plan.has(ChatMessagePartKind.daySummary)
                ? findsOneWidget
                : findsNothing);
        expect(find.text('Want the rest?'), findsNothing);
      });
    }
  });
}
