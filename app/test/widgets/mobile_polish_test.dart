import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/chat/widgets/chat_starters.dart';
import 'package:omi/pages/memories/widgets/memory_dialog.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _Tasks extends ActionItemsProvider {
  _Tasks()
      : super(
            getActionItems: (
                    {int limit = 50,
                    int offset = 0,
                    bool? completed,
                    String? conversationId,
                    DateTime? startDate,
                    DateTime? endDate,
                    DateTime? dueStartDate,
                    DateTime? dueEndDate}) async =>
                const ActionItemsResponse(actionItems: [], hasMore: false));
  Completer<ActionItemWithMetadata?> result = Completer();
  int writes = 0;
  DateTime? savedDueDate;

  @override
  Future<ActionItemWithMetadata?> createActionItem(
      {required String description, DateTime? dueAt, String? conversationId, bool completed = false}) {
    writes++;
    savedDueDate = dueAt;
    return result.future;
  }
}

Widget _app(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('starters suit available data, stay editable, and fit large text', (tester) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    String? selected;
    for (final hasData in [false, true]) {
      await tester.pumpWidget(_app(MediaQuery(
        data: const MediaQueryData(textScaler: TextScaler.linear(2)),
        child: ChatStarters(hasExistingData: hasData, isConnected: true, onSelected: (value) => selected = value),
      )));
      final key = Key(hasData ? 'chat_starter_activity' : 'chat_starter_goal');
      await tester.ensureVisible(find.byKey(key));
      await tester.tap(find.byKey(key));
      expect(selected, hasData ? 'Summarize my recent activity' : 'Help me set a goal');
      expect(find.text(hasData ? 'What can you do for me?' : 'Summarize my recent activity'), findsNothing);
      expect(tester.takeException(), isNull);
    }
    await tester.pumpWidget(_app(ChatStarters(hasExistingData: true, isConnected: false, onSelected: (_) {})));
    expect(find.byType(OutlinedButton), findsNothing);
  });

  testWidgets('empty or whitespace memory cannot be saved', (tester) async {
    final memories = MemoriesProvider();
    addTearDown(memories.dispose);
    await tester.pumpWidget(_app(MemoryDialog(provider: memories)));
    final save = find.byKey(const Key('memory_save_button'));
    expect(tester.widget<ElevatedButton>(save).onPressed, isNull);
    await tester.enterText(find.byKey(const Key('memory_content_field')), '   ');
    await tester.pump();
    expect(tester.widget<ElevatedButton>(save).onPressed, isNull);
    await tester.enterText(find.byKey(const Key('memory_content_field')), 'I prefer morning meetings.');
    await tester.pump();
    expect(tester.widget<ElevatedButton>(save).onPressed, isNotNull);
  });

  testWidgets('task awaits save, prevents duplicates, retains a rejected draft and retries', (tester) async {
    final tasks = _Tasks();
    addTearDown(tasks.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<ActionItemsProvider>.value(
      value: tasks,
      child: _app(Builder(
          builder: (context) => TextButton(
                onPressed: () => showModalBottomSheet(
                    context: context, isScrollControlled: true, builder: (_) => const ActionItemFormSheet()),
                child: const Text('Open'),
              ))),
    ));
    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();
    final save = find.byKey(const Key('task_save_button'));
    expect(tester.widget<FilledButton>(save).onPressed, isNull);
    await tester.enterText(find.byKey(const Key('task_description')), 'Send notes');
    await tester.pump();
    expect(find.text('10/4096'), findsOneWidget);
    await tester.tap(find.byKey(const Key('task_quick_date_1')));
    await tester.pump();
    await tester.tap(save);
    await tester.pump();
    await tester.tap(save);
    expect(tasks.writes, 1);
    expect(find.byType(ActionItemFormSheet), findsOneWidget);
    expect(find.text('Action item created'), findsNothing);
    final tomorrow = DateTime.now().add(const Duration(days: 1));
    expect(tasks.savedDueDate!.day, tomorrow.day);
    tasks.result.complete(null);
    await tester.pumpAndSettle();
    expect(find.text('Failed to create action item'), findsOneWidget);
    expect(tester.widget<TextField>(find.byKey(const Key('task_description'))).controller!.text, 'Send notes');
    tasks.result = Completer();
    await tester.tap(save);
    await tester.pump();
    tasks.result.complete(const ActionItemWithMetadata(id: 'saved', description: 'Send notes', completed: false));
    await tester.pumpAndSettle();
    expect(tasks.writes, 2);
    expect(find.byType(ActionItemFormSheet), findsNothing);
    expect(find.text('Action item created'), findsOneWidget);
  });
}
