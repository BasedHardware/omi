import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/pages/conversations/widgets/folder_tabs.dart';
import 'package:omi/pages/conversations/widgets/goals_widget.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import '../support/typed_conversation_screen.dart';

Future<void> pumpPage(WidgetTester tester, ConversationProvider provider) async {
  tester.view.physicalSize = const Size(800, 1400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final screen = await buildTypedConversationScreen(provider);
  SharedPreferencesUtil().showGoalTrackerEnabled = true;
  final goals = GoalsProvider(
      goalsFetcher: () async => [
            Goal.fromJson({'id': 'goal', 'title': 'Read a book'})
          ]);
  addTearDown(goals.dispose);
  await goals.init();
  await tester.pumpWidget(ChangeNotifierProvider.value(value: goals, child: screen));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 250));
}

ServerConversation completed(String id, {DateTime? createdAt, DateTime? finishedAt}) => ServerConversation(
      id: id,
      createdAt: createdAt ?? DateTime.now(),
      finishedAt: finishedAt,
      structured: Structured('Finished recording', 'Overview', emoji: '🧠'),
      status: ConversationStatus.completed,
    );

void main() {
  setUp(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);

  testWidgets('Process Now appears below Goals and list controls, above existing conversations', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    await provider.addConversation(completed('older'));
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();

    final processing = find.byType(ProcessingConversationWidget);
    expect(processing, findsOneWidget);
    expect(tester.getBottomLeft(find.byType(GoalsWidget)).dy, lessThan(tester.getTopLeft(processing).dy));
    expect(tester.getBottomLeft(find.text('Conversations')).dy, lessThan(tester.getTopLeft(processing).dy));
    expect(tester.getBottomLeft(find.byType(FolderTabs)).dy, lessThanOrEqualTo(tester.getTopLeft(processing).dy));
    expect(tester.getBottomLeft(processing).dy, lessThan(tester.getTopLeft(find.byType(ConversationListItem)).dy));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('processing-only account has a list heading and no contradictory empty state', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();

    expect(find.text('Conversations'), findsOneWidget);
    expect(find.byType(ProcessingConversationWidget), findsOneWidget);
    expect(find.byType(EmptyConversationsWidget), findsNothing);
    expect(find.byType(SliverFillRemaining), findsNothing);

    provider.removeProcessingConversation(OptimisticProcessingPlaceholder.id);
    provider.addProcessingConversation(completed('real')..status = ConversationStatus.processing);
    await tester.pump();
    expect(find.byType(ProcessingConversationWidget), findsOneWidget);
    expect(
        tester.widget<ProcessingConversationWidget>(find.byType(ProcessingConversationWidget)).conversation.id, 'real');

    provider.removeProcessingConversation('real');
    await provider.addConversation(completed('real'));
    await tester.pump();
    expect(find.byType(ProcessingConversationWidget), findsNothing);
    expect(find.byType(ConversationListItem), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('latest Process Now replaces the displayed older processing row', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    provider.addProcessingConversation(
      completed('older', createdAt: DateTime.now().subtract(const Duration(minutes: 10)))
        ..status = ConversationStatus.processing,
    );
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();
    final processing = find.byType(ProcessingConversationWidget);
    expect(processing, findsOneWidget);
    expect(tester.widget<ProcessingConversationWidget>(processing).conversation.id, '0');

    provider.removeProcessingConversation('0');
    provider.addProcessingConversation(
      completed('new', createdAt: DateTime.now().subtract(const Duration(hours: 1)), finishedAt: DateTime.now())
        ..status = ConversationStatus.processing,
    );
    await tester.pump();
    expect(tester.widget<ProcessingConversationWidget>(processing).conversation.id, 'new');
    provider.removeProcessingConversation('new');
    await provider.addConversation(completed('new'));
    await tester.pump();
    expect(tester.widget<ProcessingConversationWidget>(processing).conversation.id, 'older');
    expect(find.byType(ConversationListItem), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('optimistic processing remains visible with an active filter and no results', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    provider.selectedFolderId = 'folder';
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();
    expect(find.byType(ProcessingConversationWidget), findsOneWidget);
    expect(find.byType(EmptyConversationsWidget), findsNothing);
    expect(find.byType(SliverFillRemaining), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('pending conversation stays on the Conversations list, never a recaps mode', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();
    // Daily Recaps is its own page now; this tab must never switch into a
    // recap mode, and the pending capture stays in the Conversations list.
    expect(find.text('Daily Recaps'), findsNothing);
    expect(find.byType(ProcessingConversationWidget), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
