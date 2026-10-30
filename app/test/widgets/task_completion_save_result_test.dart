/// Completing a task from the Tasks list or a chat task card must branch on whether the save
/// reached the server (#17848): a rejected save keeps the task as it was, says so, and records no
/// completion.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/pages/chat/widgets/content_blocks/task_card_block.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../support/typed_action_items_screen.dart';

const _failure = 'Failed to update task';

/// One task on a fake server that either accepts or rejects every completion write.
class _TaskServer {
  _TaskServer({required this.accept});

  final bool accept;
  bool _done = false;

  ActionItemWithMetadata get _task => ActionItemWithMetadata(id: 'task-1', description: 'Buy milk', completed: _done);

  Future<ActionItemsResponse?> list({
    int limit = 100,
    int offset = 0,
    bool? completed,
    String? conversationId,
    DateTime? startDate,
    DateTime? endDate,
    DateTime? dueStartDate,
    DateTime? dueEndDate,
  }) async =>
      ActionItemsResponse(actionItems: [_task]);

  Future<ActionItemWithMetadata?> update(String id, {String? description, bool? completed, DateTime? dueAt}) async {
    if (!accept) return null;
    _done = completed ?? _done;
    return _task;
  }
}

ActionItemsProvider _provider({required bool accept}) {
  final server = _TaskServer(accept: accept);
  return ActionItemsProvider(getActionItems: server.list, updateActionItemRequest: server.update);
}

void main() {
  late _RecordingAdapter adapter;

  setUp(() async {
    PlatformManager.initializeForLocalHarness();
    // Follow-up writes that are not injectable (e.g. sort persistence) hit a dead loopback port.
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    adapter = _RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
  });
  tearDown(() {
    AnalyticsManager.resetForTesting();
    Env.clearApiBaseUrlOverrideForTesting();
  });

  Future<int> completionEvents(WidgetTester tester) async {
    await tester.runAsync(() => AnalyticsManager.flushPending(force: true));
    return adapter.events.where((e) => e.$1 == 'Action Item Completed').length;
  }

  group('Tasks list', () {
    Future<ActionItemsProvider> pumpTasks(WidgetTester tester, {required bool accept}) async {
      final provider = _provider(accept: accept);
      addTearDown(provider.dispose);
      await tester.pumpWidget(await buildTypedActionItemsScreen(provider));
      await provider.ensureLoaded();
      await tester.pumpAndSettle();
      expect(find.text('Buy milk'), findsOneWidget);
      return provider;
    }

    void expectStillOpen(WidgetTester tester, ActionItemsProvider provider) {
      expect(provider.actionItems.single.completed, isFalse);
      expect(tester.widget<TaskCompletionMark>(find.byType(TaskCompletionMark)).completed, isFalse);
    }

    testWidgets('a rejected checkbox save keeps the task open, says so, and records no completion', (tester) async {
      final provider = await pumpTasks(tester, accept: false);

      await tester.tap(find.byType(TaskCompletionMark));
      await tester.pumpAndSettle();

      expectStillOpen(tester, provider);
      expect(find.text(_failure), findsOneWidget);
      expect(await completionEvents(tester), 0);
    });

    testWidgets('a rejected swipe save keeps the task open, says so, and records no completion', (tester) async {
      final provider = await pumpTasks(tester, accept: false);

      await tester.drag(find.text('Buy milk'), const Offset(400, 0));
      await tester.pumpAndSettle();

      expectStillOpen(tester, provider);
      expect(find.text(_failure), findsOneWidget);
      expect(await completionEvents(tester), 0);
    });

    testWidgets('an accepted checkbox save records exactly one completion and no error', (tester) async {
      final provider = await pumpTasks(tester, accept: true);

      await tester.tap(find.byType(TaskCompletionMark));
      await tester.pumpAndSettle();

      expect(provider.actionItems.single.completed, isTrue);
      expect(find.text(_failure), findsNothing);
      expect(await completionEvents(tester), 1);
    });
  });

  group('chat task card', () {
    const toggle = Key('chat-block-taskCard-block-task-toggle');

    Future<ActionItemsProvider> pumpCard(WidgetTester tester, {required bool accept}) async {
      final provider = _provider(accept: accept);
      addTearDown(provider.dispose);
      await tester.pumpWidget(
        ChangeNotifierProvider<ActionItemsProvider>.value(
          value: provider,
          child: const MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: [Locale('en')],
            home: Scaffold(
              body: TaskCardBlock(block: TaskCardContentBlock(id: 'block-task', taskId: 'task-1')),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(toggle), findsOneWidget);
      return provider;
    }

    testWidgets('a rejected save keeps the task open and says so', (tester) async {
      final provider = await pumpCard(tester, accept: false);

      await tester.tap(find.byKey(toggle));
      await tester.pumpAndSettle();

      expect(provider.actionItems.single.completed, isFalse);
      expect(find.descendant(of: find.byKey(toggle), matching: find.byIcon(Icons.circle_outlined)), findsOneWidget);
      expect(find.text(_failure), findsOneWidget);
    });

    testWidgets('an accepted save completes the task without an error', (tester) async {
      final provider = await pumpCard(tester, accept: true);

      await tester.tap(find.byKey(toggle));
      await tester.pumpAndSettle();

      expect(provider.actionItems.single.completed, isTrue);
      expect(find.text(_failure), findsNothing);
    });
  });
}

class _RecordingAdapter implements AnalyticsAdapter {
  final events = <(String, Map<String, Object>)>[];
  bool initialized = false;

  @override
  bool get isInitialized => initialized;

  @override
  Future<void> init() async => initialized = true;

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) =>
      events.add((eventName, properties ?? const {}));

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void registerSuperProperties(Map<String, Object> properties) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
