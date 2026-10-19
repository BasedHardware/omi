import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/date_list_item.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
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

ServerConversation completed(String id, {DateTime? createdAt, DateTime? startedAt, DateTime? finishedAt}) =>
    ServerConversation(
      id: id,
      createdAt: createdAt ?? DateTime.now(),
      startedAt: startedAt,
      finishedAt: finishedAt,
      structured: Structured('Finished recording', 'Overview', emoji: '🧠'),
      status: ConversationStatus.completed,
    );

void main() {
  setUp(() => VisibilityDetectorController.instance.updateInterval = Duration.zero);

  final pendingRow = find.byKey(const Key('home_pending_row'));

  // A conversation still processing is not a card of its own: it joins Home's one pending row under
  // Today, and slow work never says it is taking longer.
  testWidgets('processing joins the pending row under Today, above same-day conversations', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    await provider.addConversation(completed('older'));
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();

    final header = find.byType(DateListItem);
    final item = find.byType(ConversationListItem);
    expect(header, findsOneWidget);
    expect(pendingRow, findsOneWidget);
    expect(item, findsOneWidget);
    expect(find.text('Processing'), findsOneWidget);
    expect(find.textContaining('taking longer'), findsNothing);
    expect(tester.widget<DateListItem>(header).date, conversationLocalDayKey(DateTime.now()));
    expect(tester.getBottomLeft(header).dy, lessThanOrEqualTo(tester.getTopLeft(pendingRow).dy));
    expect(tester.getBottomLeft(pendingRow).dy, lessThanOrEqualTo(tester.getTopLeft(item).dy));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('processing-only account shows the row, not an empty state; it clears when done', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();

    expect(pendingRow, findsOneWidget);
    expect(find.byType(EmptyConversationsWidget), findsNothing);
    expect(find.byType(DateListItem), findsOneWidget);

    provider.removeProcessingConversation(OptimisticProcessingPlaceholder.id);
    await provider.addConversation(completed('real'));
    await tester.pump();
    expect(pendingRow, findsNothing);
    expect(find.byType(ConversationListItem), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('several processing conversations, across days, are still one row in Today', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    final now = DateTime.now();
    final yesterdayNoon = DateTime(now.year, now.month, now.day - 1, 12);
    provider.addProcessingConversation(
      completed('older', createdAt: yesterdayNoon, startedAt: yesterdayNoon)..status = ConversationStatus.processing,
    );
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();
    expect(pendingRow, findsOneWidget);
    expect(
      tester.widgetList<DateListItem>(find.byType(DateListItem)).map((header) => header.date),
      [conversationLocalDayKey(now)],
    );
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('the row shows while the first page is still loading', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    provider.setLoadingConversations(true);
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await pumpPage(tester, provider);
    await tester.pump();

    expect(pendingRow, findsOneWidget);
    expect(find.byType(EmptyConversationsWidget), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a just-captured conversation stays visible with an active filter and no results', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    provider.selectedFolderId = 'folder';
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();
    expect(pendingRow, findsOneWidget);
    expect(find.byType(EmptyConversationsWidget), findsNothing);
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
    expect(pendingRow, findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
