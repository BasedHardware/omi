import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/date_list_item.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
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

  testWidgets('Process Now rows under the Today header, above the same-day conversations', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    await provider.addConversation(completed('older'));
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();

    final header = find.byType(DateListItem);
    final processing = find.byType(ProcessingConversationWidget);
    final item = find.byType(ConversationListItem);
    expect(header, findsOneWidget);
    expect(processing, findsOneWidget);
    expect(item, findsOneWidget);
    expect(tester.widget<DateListItem>(header).date, conversationLocalDayKey(DateTime.now()));
    expect(tester.getBottomLeft(header).dy, lessThanOrEqualTo(tester.getTopLeft(processing).dy));
    expect(tester.getBottomLeft(processing).dy, lessThanOrEqualTo(tester.getTopLeft(item).dy));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('processing-only account has no contradictory empty state', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    final placeholder = OptimisticProcessingPlaceholder.conversation();
    provider.addProcessingConversation(placeholder);
    await tester.pump();

    expect(find.byType(ProcessingConversationWidget), findsOneWidget);
    expect(find.byType(EmptyConversationsWidget), findsNothing);
    expect(find.byType(SliverFillRemaining), findsNothing);
    final headers = find.byType(DateListItem);
    expect(headers, findsOneWidget);
    expect(tester.widget<DateListItem>(headers).date,
        conversationLocalDayKey(placeholder.startedAt ?? placeholder.createdAt));

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
    final now = DateTime.now();
    final yesterdayNoon = DateTime(now.year, now.month, now.day - 1, 12);
    provider.addProcessingConversation(
      completed('older', createdAt: yesterdayNoon)..status = ConversationStatus.processing,
    );
    provider.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await tester.pump();
    final processing = find.byType(ProcessingConversationWidget);
    expect(processing, findsOneWidget);
    expect(tester.widget<ProcessingConversationWidget>(processing).conversation.id, '0');
    expect(
      tester.widgetList<DateListItem>(find.byType(DateListItem)).map((header) => header.date),
      [conversationLocalDayKey(now)],
    );

    provider.removeProcessingConversation('0');
    provider.addProcessingConversation(
      completed('new', createdAt: DateTime(now.year, now.month, now.day - 1, 11), finishedAt: now)
        ..status = ConversationStatus.processing,
    );
    await tester.pump();
    expect(tester.widget<ProcessingConversationWidget>(processing).conversation.id, 'new');
    expect(
      tester.widgetList<DateListItem>(find.byType(DateListItem)).map((header) => header.date),
      [conversationLocalDayKey(yesterdayNoon)],
    );

    provider.removeProcessingConversation('new');
    await provider.addConversation(completed('new'));
    await tester.pump();
    expect(tester.widget<ProcessingConversationWidget>(processing).conversation.id, 'older');
    final dates = tester.widgetList<DateListItem>(find.byType(DateListItem)).map((header) => header.date).toList();
    expect(dates.length, 2);
    expect(dates, containsAll([conversationLocalDayKey(now), conversationLocalDayKey(yesterdayNoon)]));
    expect(find.byType(ConversationListItem), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('processing row joins its own day group ahead of that day\'s completed rows', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    final now = DateTime.now();
    final todayNoon = DateTime(now.year, now.month, now.day, 12);
    final yesterdayNoon = DateTime(now.year, now.month, now.day - 1, 12);
    await provider.addConversation(completed('today', createdAt: todayNoon));
    await provider.addConversation(completed('yesterday', createdAt: yesterdayNoon));
    provider.addProcessingConversation(
      completed('proc', createdAt: yesterdayNoon)..status = ConversationStatus.processing,
    );
    await tester.pump();

    final headers = tester.widgetList<DateListItem>(find.byType(DateListItem)).toList();
    expect(headers.length, 2);
    expect(headers[0].date, conversationLocalDayKey(todayNoon));
    expect(headers[1].date, conversationLocalDayKey(yesterdayNoon));
    expect(find.byType(ConversationListItem), findsNWidgets(2));
    final processing = find.byType(ProcessingConversationWidget);
    expect(processing, findsOneWidget);
    expect(tester.getBottomLeft(find.byKey(const ValueKey('today'))).dy,
        lessThanOrEqualTo(tester.getTopLeft(find.byWidget(headers[1])).dy));
    expect(tester.getBottomLeft(find.byWidget(headers[1])).dy, lessThanOrEqualTo(tester.getTopLeft(processing).dy));
    expect(tester.getBottomLeft(processing).dy,
        lessThanOrEqualTo(tester.getTopLeft(find.byKey(const ValueKey('yesterday'))).dy));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('processing row files under the startedAt local day, not the finishedAt day', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    final now = DateTime.now();
    final todayNoon = DateTime(now.year, now.month, now.day, 12);
    final yesterdayNoon = DateTime(now.year, now.month, now.day - 1, 12);
    await provider.addConversation(completed('today', createdAt: todayNoon));
    provider.addProcessingConversation(
      completed('proc', createdAt: now, startedAt: yesterdayNoon.toUtc(), finishedAt: now)
        ..status = ConversationStatus.processing,
    );
    await tester.pump();

    final headers = tester.widgetList<DateListItem>(find.byType(DateListItem)).toList();
    expect(headers.length, 2);
    expect(headers[0].date, conversationLocalDayKey(todayNoon));
    expect(headers[1].date, conversationLocalDayKey(yesterdayNoon));
    expect(find.byType(EmptyConversationsWidget), findsNothing);
    expect(find.byType(SliverFillRemaining), findsNothing);
    final processing = find.byType(ProcessingConversationWidget);
    expect(processing, findsOneWidget);
    expect(tester.getBottomLeft(find.byKey(const ValueKey('today'))).dy,
        lessThanOrEqualTo(tester.getTopLeft(find.byWidget(headers[1])).dy));
    expect(tester.getBottomLeft(find.byWidget(headers[1])).dy, lessThanOrEqualTo(tester.getTopLeft(processing).dy));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('processing rows stay on the real list while the first page is still loading', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    provider.setLoadingConversations(true);
    final placeholder = OptimisticProcessingPlaceholder.conversation();
    provider.addProcessingConversation(placeholder);
    await pumpPage(tester, provider);
    await tester.pump();

    expect(find.byType(ProcessingConversationWidget), findsOneWidget);
    final headers = find.byType(DateListItem);
    expect(headers, findsOneWidget);
    expect(tester.widget<DateListItem>(headers).date,
        conversationLocalDayKey(placeholder.startedAt ?? placeholder.createdAt));
    expect(find.byType(EmptyConversationsWidget), findsNothing);
    expect(find.byType(SliverFillRemaining), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('optimistic processing remains visible with an active filter and no results', (tester) async {
    final provider = ConversationProvider(isSignedIn: () => false);
    addTearDown(provider.dispose);
    await pumpPage(tester, provider);
    provider.selectedFolderId = 'folder';
    final placeholder = OptimisticProcessingPlaceholder.conversation();
    provider.addProcessingConversation(placeholder);
    await tester.pump();
    expect(find.byType(ProcessingConversationWidget), findsOneWidget);
    expect(find.byType(EmptyConversationsWidget), findsNothing);
    expect(find.byType(SliverFillRemaining), findsNothing);
    final headers = find.byType(DateListItem);
    expect(headers, findsOneWidget);
    expect(tester.widget<DateListItem>(headers).date,
        conversationLocalDayKey(placeholder.startedAt ?? placeholder.createdAt));
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
