import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/content_blocks/task_card_block.dart';
import 'package:omi/pages/conversations/widgets/today_tasks_widget.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../spine/c7_registry_test.dart' show RecordingAdapter;
import '../support/typed_action_items_screen.dart';

const _task = ActionItemWithMetadata(id: 'task-1', description: 'Buy milk', completed: false);

void main() {
  late RecordingAdapter analytics;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.543',
      buildNumber: '992',
      buildSignature: '',
    );
    AnalyticsManager.resetForTesting();
    analytics = RecordingAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  for (final (control, targetState, closeBeforeResult, firstWriteSucceeds) in [
    ('checkbox', true, false, false),
    ('swipe', true, false, false),
    ('chat', true, false, false),
    ('checkbox', false, false, false),
    ('swipe', false, false, false),
    ('chat', false, false, false),
    ('home', true, false, false),
    ('chat', true, true, false),
    ('home', true, true, false),
    ('checkbox', true, false, true),
    ('swipe', true, false, true),
    ('chat', true, false, true),
    ('home', true, false, true),
  ]) {
    testWidgets(
        '$control completion=$targetState ${closeBeforeResult ? 'handles navigation away' : firstWriteSucceeds ? 'saves on the first attempt' : 'reports rejection and retries'}',
        (tester) async {
      var serverTask = _task.copyWith(completed: !targetState, dueAt: DateTime.now());
      final writes = <bool?>[];
      final firstWrite = Completer<ActionItemWithMetadata?>();
      final provider = ActionItemsProvider(
        getActionItems: ({
          int limit = 50,
          int offset = 0,
          bool? completed,
          String? conversationId,
          DateTime? startDate,
          DateTime? endDate,
          DateTime? dueStartDate,
          DateTime? dueEndDate,
        }) async =>
            ActionItemsResponse(actionItems: [serverTask]),
        updateActionItemRequest: (id, {description, completed, dueAt}) async {
          writes.add(completed);
          if (writes.length == 1) return firstWrite.future;
          serverTask = serverTask.copyWith(completed: completed);
          return serverTask;
        },
      );
      addTearDown(provider.dispose);
      await provider.ensureLoaded();
      if (control == 'home') await provider.ensureHomeTodayTasksLoaded();

      if (control == 'chat') {
        await tester.pumpWidget(ChangeNotifierProvider.value(
          value: provider,
          child: const MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: [Locale('en')],
            home: Scaffold(body: TaskCardBlock(block: TaskCardContentBlock(id: 'card-1', taskId: 'task-1'))),
          ),
        ));
      } else if (control == 'home') {
        await tester.pumpWidget(ChangeNotifierProvider.value(
          value: provider,
          child: const MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: [Locale('en')],
            home: Scaffold(body: TodayTasksWidget()),
          ),
        ));
      } else {
        await tester.pumpWidget(await buildTypedActionItemsScreen(provider));
      }
      await tester.pumpAndSettle();

      if (control == 'swipe') {
        expect(tester.widget<Dismissible>(find.byKey(const Key('dismiss_task-1'))).direction,
            DismissDirection.horizontal);
        await tester.drag(find.byKey(const Key('dismiss_task-1')), const Offset(500, 0));
        await tester.pumpAndSettle();
      } else if (control == 'chat') {
        await tester.tap(find.byKey(const Key('chat-block-taskCard-card-1-toggle')));
        // A second tap before the next frame must neither send another write
        // nor turn an in-flight save into a false failure message.
        await tester.tap(find.byKey(const Key('chat-block-taskCard-card-1-toggle')));
      } else if (control == 'home') {
        await tester.tap(find.byKey(const Key('today-task-task-1-toggle')));
      } else {
        await tester.tap(find.byKey(const Key('action-item-task-1-toggle')));
      }
      await tester.pump();
      expect(writes, [targetState]);
      expect(provider.actionItems.single.completed, targetState);
      expect(find.text('Failed to update action item'), findsNothing);

      if (closeBeforeResult) {
        await tester.pumpWidget(const SizedBox.shrink());
        firstWrite.complete(null);
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(provider.actionItems.single.completed, !targetState);
        return;
      }

      if (firstWriteSucceeds) serverTask = serverTask.copyWith(completed: targetState);
      firstWrite.complete(firstWriteSucceeds ? serverTask : null);
      await tester.pumpAndSettle();
      if (control == 'swipe' && !firstWriteSucceeds) {
        expect(tester.widget<Dismissible>(find.byKey(const Key('dismiss_task-1'))).direction,
            DismissDirection.horizontal);
      }
      if (firstWriteSucceeds) {
        expect(provider.actionItems.single.completed, targetState);
        expect(find.text('Failed to update action item'), findsNothing);
        await AnalyticsManager.flushPending(force: true);
        expect(analytics.events.where((event) => event.$1 == 'Action Item Completed'),
            hasLength(control != 'chat' && control != 'home' ? 1 : 0));
        await provider.fetchActionItems();
        expect(provider.actionItems.single.completed, targetState);
        await tester.pumpWidget(const SizedBox.shrink());
        return;
      }
      expect(provider.actionItems.single.completed, !targetState);
      await AnalyticsManager.flushPending(force: true);
      expect(analytics.events.where((event) => event.$1 == 'Action Item Completed'), isEmpty);
      expect(find.text('Failed to update action item'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);

      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(writes, [targetState, targetState]);
      expect(provider.actionItems.single.completed, targetState);
      await AnalyticsManager.flushPending(force: true);
      expect(analytics.events.where((event) => event.$1 == 'Action Item Completed'),
          hasLength(control != 'chat' && control != 'home' && targetState ? 1 : 0));
      await provider.fetchActionItems();
      await tester.pumpAndSettle();
      expect(provider.actionItems.single.completed, targetState);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
