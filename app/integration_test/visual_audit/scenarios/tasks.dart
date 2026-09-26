// Tasks: the task form sheet (create, due dates, failed and successful save, edit) and the Tasks tab.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

import '../harness.dart';

void _openTaskForm(BuildContext context, {ActionItemWithMetadata? item}) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => ActionItemFormSheet(actionItem: item),
  );
}

final tasksScenarios = <AuditScenario>[
  AuditScenario(
    id: 'tasks-create',
    title: 'Task form: create, due date, quick date, failed save, saved',
    page: 'lib/pages/action_items/widgets/action_item_form_sheet.dart (ActionItemFormSheet)',
    state: 'Fixture-backed ActionItemsProvider with no tasks; the first save is rejected with a 400',
    run: (a) async {
      await a.pumpHost(_openTaskForm, providers: [ChangeNotifierProvider(create: (_) => ActionItemsProvider())]);
      await a.shot('Open the task creation sheet', step: 'empty');
      await a.enterText(find.byType(TextField).first, 'Send the design notes to Alex');
      await a.shot('Enter a task description', step: 'draft');
      await a.tap(find.text('Add Due Date'));
      await a.shot('Tap Add Due Date', step: 'date-picker');
      await a.tap(find.text('Done'));
      await a.shot('Confirm the date and return to the draft', step: 'date-selected');
      expect(find.text('29/4096'), findsOneWidget);
      await a.tap(find.byKey(const ValueKey('task_quick_date_1')));
      await a.shot('Choose Tomorrow in one tap', step: 'quick-date');
      // A non-retryable rejection reaches the form; transient 503s are retried by the HTTP client.
      a.server.failNext('POST', '/v1/action-items', status: 400);
      await a.tap(find.byKey(const Key('task_save_button')));
      expect(find.byType(ActionItemFormSheet), findsOneWidget);
      await a.shot('A rejected save keeps the draft available to retry', step: 'save-failed');
      await a.tap(find.byKey(const Key('task_save_button')));
      expect(a.server.actionItems.single['description'], 'Send the design notes to Alex');
      expect(find.byType(ActionItemFormSheet), findsNothing);
      await a.shot('Retry the save; the sheet closes on server success', step: 'saved');
    },
  ),
  AuditScenario(
    id: 'tasks-edit',
    title: 'Task form editing an existing task',
    page: 'lib/pages/action_items/widgets/action_item_form_sheet.dart (ActionItemFormSheet)',
    state: 'One open task due tomorrow at 9:00, opened for editing on a neutral host',
    run: (a) async {
      final tomorrow = DateTime.now().add(const Duration(days: 1));
      final item = ActionItemWithMetadata(
        id: 'task-1',
        description: 'Book the venue for the launch',
        completed: false,
        dueAt: DateTime(tomorrow.year, tomorrow.month, tomorrow.day, 9),
      );
      await a.pumpHost((context) => _openTaskForm(context, item: item));
      await a.shot('Open an existing task for editing');
    },
  ),
  AuditScenario(
    id: 'tasks-indented',
    title: 'Tasks tab with an indented subtask, and its long-press menu',
    page: 'lib/pages/action_items/action_items_page.dart (ActionItemsPage)',
    state: 'ActionItemsProvider loaded with a parent task and one indented child task',
    run: (a) async {
      Future<ActionItemsResponse?> items({
        int limit = 100,
        int offset = 0,
        bool? completed,
        String? conversationId,
        DateTime? startDate,
        DateTime? endDate,
        DateTime? dueStartDate,
        DateTime? dueEndDate,
      }) async =>
          const ActionItemsResponse(actionItems: [
            ActionItemWithMetadata(id: 'parent', description: 'Plan the launch', completed: false, sortOrder: 1000),
            ActionItemWithMetadata(
                id: 'child', description: 'Book the venue', completed: false, sortOrder: 2000, indentLevel: 1),
          ]);
      final actionItems = ActionItemsProvider(getActionItems: items);
      await a.tester.runAsync(actionItems.ensureLoaded);
      await a.pump(const ActionItemsPage(), providers: [
        ChangeNotifierProvider<ActionItemsProvider>.value(value: actionItems),
      ]);
      await a.shot('Tasks tab with a parent task and an indented child', step: 'list');
      await a.longPress(find.text('Book the venue'));
      await a.shot('Long-press the indented task row', step: 'menu');
    },
  ),
  AuditScenario(
    id: 'tasks-from-conversations',
    title: 'To do: overdue, today and undated tasks, each saying which conversation it came from',
    page: 'lib/pages/action_items/action_items_page.dart (ActionItemsPage)',
    state: 'Four open tasks: one overdue, two due today (one at 5 PM), one undated; three from conversations',
    run: (a) async {
      final now = DateTime.now();
      final today = DateTime(now.year, now.month, now.day);
      ServerConversation conversation(String id, String title) => ServerConversation(
            id: id,
            createdAt: today,
            structured: Structured(title, 'Overview', emoji: '', category: 'work'),
            status: ConversationStatus.completed,
          );
      final conversations = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        isSignedIn: () => true,
      )..conversations = [
          conversation('c1', 'Pricing review'),
          conversation('c2', 'App UX and battery'),
          conversation('c3', 'Subscription concerns'),
        ];
      Future<ActionItemsResponse?> items({
        int limit = 100,
        int offset = 0,
        bool? completed,
        String? conversationId,
        DateTime? startDate,
        DateTime? endDate,
        DateTime? dueStartDate,
        DateTime? dueEndDate,
      }) async =>
          ActionItemsResponse(actionItems: [
            ActionItemWithMetadata(
              id: 'overdue',
              description: 'Send the pricing draft to the team',
              completed: false,
              dueAt: today.subtract(const Duration(hours: 7)),
              conversationId: 'c1',
              sortOrder: 1000,
            ),
            ActionItemWithMetadata(
              id: 'call',
              description: 'Call Chitapa',
              completed: false,
              dueAt: today.add(const Duration(hours: 17)),
              sortOrder: 2000,
            ),
            ActionItemWithMetadata(
              id: 'battery',
              description: 'Pull battery reports',
              completed: false,
              dueAt: today.add(const Duration(hours: 23)),
              conversationId: 'c2',
              sortOrder: 3000,
            ),
            const ActionItemWithMetadata(
              id: 'errors',
              description: 'Separate plan-limit and verification errors',
              completed: false,
              conversationId: 'c3',
              sortOrder: 4000,
            ),
          ]);
      final actionItems = ActionItemsProvider(getActionItems: items);
      await a.tester.runAsync(actionItems.ensureLoaded);
      await a.pump(const ActionItemsPage(), providers: [
        ChangeNotifierProvider<ActionItemsProvider>.value(value: actionItems),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
      ]);
      await a.shot('To do with overdue, today and undated tasks from conversations');
    },
  ),
];
