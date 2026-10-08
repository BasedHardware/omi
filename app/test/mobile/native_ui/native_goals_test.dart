import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_edit.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/action_items/widgets/accept_shared_tasks_sheet.dart';
import 'package:omi/pages/action_items/widgets/goal_form_sheet.dart';
import 'package:omi/pages/conversations/widgets/goals_widget.dart';
import 'package:omi/pages/goals/goals_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/ui/components/omi_sheet.dart';

import 'native_test_host.dart';

Goal _goal(String id, String title, {double current = 3, double target = 10}) => Goal(
      id: id,
      title: title,
      goalType: 'numeric',
      targetValue: target,
      currentValue: current,
      minValue: 0,
      maxValue: target,
      isActive: true,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
    );

/// The existing owner with inert I/O: reads come from the fetcher, writes are recorded.
class _FakeGoals extends GoalsProvider {
  _FakeGoals(List<Goal> goals) : super(goalsFetcher: () async => goals);

  final progress = <(String, double)>[];
  final updates = <(String, String)>[];
  final deletes = <String>[];

  @override
  Future<Goal?> updateGoalProgress(String goalId, double currentValue) async {
    progress.add((goalId, currentValue));
    return null;
  }

  @override
  Future<Goal?> updateGoal(String goalId,
      {String? title,
      double? targetValue,
      double? currentValue,
      double? minValue,
      double? maxValue,
      String? unit}) async {
    updates.add((goalId, title ?? ''));
    return null;
  }

  @override
  Future<bool> deleteGoal(String goalId) async {
    deletes.add(goalId);
    return true;
  }
}

/// The existing action items owner; only its refresh is observed.
class _FakeActionItems extends ActionItemsProvider {
  var refreshes = 0;

  @override
  Future<void> forceRefreshActionItems() async => refreshes++;
}

final _l10n = lookupAppLocalizations(const Locale('en'));

Widget _app(Widget home, GoalsProvider goals) => NativeTestHost.app(
      ChangeNotifierProvider<GoalsProvider>.value(value: goals, child: Scaffold(body: home)),
    );

List<NativeRow> _surfaceRows(WidgetTester tester) => [
      for (final state in tester.stateList<State<IosNativeSurface>>(find.byType(IosNativeSurface)))
        ...IosNativeSurface.debugDispatchRows(state),
    ];

NativeRow _row(WidgetTester tester, String id) => _surfaceRows(tester).lastWhere((row) => row.id == id);

Future<void> _send(NativeTestHost host, String id, [Object? value]) async {
  await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
}

Future<_FakeGoals> _mountGoals(WidgetTester tester, List<Goal> goals) async {
  final provider = _FakeGoals(goals);
  addTearDown(provider.dispose);
  await tester.pumpWidget(_app(const GoalsPage(), provider));
  // The page refreshes the existing owner after its first frame.
  for (var frame = 0; frame < 4; frame++) {
    await tester.pump();
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
  }
  await NativeTestHost.settle(tester);
  return provider;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'goal-user'});
    await SharedPreferencesUtil.init();
  });

  group('Goals page', () {
    testWidgets('projects each goal with its progress level and degenerate targets as labels', (tester) async {
      final host = NativeTestHost.install();
      await _mountGoals(tester, [
        _goal('a', 'Read 12 books', current: 6, target: 12),
        _goal('b', 'Run far', current: 250, target: 100),
        _goal('c', 'Save', current: 2.5, target: 1000000),
        _goal('d', 'Broken', current: 1, target: 0),
        _goal('e', 'Half', current: 2.5, target: 10),
      ]);

      expect(find.byType(UiKitView), findsOneWidget, reason: 'every projected row is valid');
      expect(host.created, isNotEmpty);
      final rows = _surfaceRows(tester);
      expect(rows.every((row) => row.valid), isTrue);
      expect(rows.map((row) => row.id),
          containsAll(['goals_back', 'goals_add', 'goal:0', 'goal_progress:0', 'goal:3', 'goal_progress:3']));

      final first = _row(tester, 'goal:0');
      expect(first.title, '🎯 Read 12 books');
      expect(first.kind, 'navigation');
      expect(first.subtitle, '6/12');
      expect(first.options.keys, ['edit', 'delete']);
      expect(first.swipeTrailing, ['delete']);

      final level = _row(tester, 'goal_progress:0');
      expect(level.kind, 'level');
      expect(level.value, 6);
      expect(level.maximumValue, 12);
      expect(level.step, 1);
      expect(level.subtitle, '6/12');

      final over = _row(tester, 'goal_progress:1');
      expect(over.value, 100, reason: 'progress past the target is clamped into the range');
      expect(over.subtitle, '250/100');

      final large = _row(tester, 'goal_progress:2');
      expect(large.step, isNull, reason: 'large targets stay continuous, like the Flutter slider');
      expect(large.value, 2.5);

      final degenerate = _row(tester, 'goal_progress:3');
      expect(degenerate.kind, 'label', reason: 'a zero target has no control range');
      expect(degenerate.subtitle, '1/0');

      final half = _row(tester, 'goal_progress:4');
      expect(half.step, 1, reason: 'small whole targets snap to whole steps, like the Flutter divisions');
      expect(half.value, 3);
      expect(half.subtitle, '2.5/10');
    });

    testWidgets('an empty list offers Add Goal and loading shows only while nothing is known', (tester) async {
      NativeTestHost.install();
      await _mountGoals(tester, []);
      final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      expect(surface.loading, isFalse);
      expect(_row(tester, 'goals_empty_add').title, _l10n.addGoal);
      expect(surface.onRefresh, isNotNull);
    });

    testWidgets('a burst of progress changes saves only the final value after the debounce', (tester) async {
      final host = NativeTestHost.install();
      final provider = await _mountGoals(tester, [_goal('a', 'Read', current: 3, target: 10)]);

      for (final value in [4.0, 6.0, 7.0]) {
        await _send(host, 'goal_progress:0', value);
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(provider.progress, isEmpty, reason: 'the save waits for the burst to end');
      expect(_row(tester, 'goal_progress:0').value, 7, reason: 'the projection keeps the latest value');

      await tester.pump(goalProgressSaveDelay);
      expect(provider.progress, [('a', 7.0)]);
      await tester.pump(const Duration(seconds: 1));
      expect(provider.progress, hasLength(1));
    });

    testWidgets('leaving the page saves a pending progress change', (tester) async {
      final host = NativeTestHost.install();
      final provider = await _mountGoals(tester, [_goal('a', 'Read', current: 3, target: 10)]);
      await _send(host, 'goal_progress:0', 5.0);
      await tester.pumpWidget(const SizedBox());
      expect(provider.progress, [('a', 5.0)]);
    });

    testWidgets('an off-grid progress value is refused before it reaches the owner', (tester) async {
      final host = NativeTestHost.install();
      final provider = await _mountGoals(tester, [_goal('a', 'Read', current: 3, target: 10)]);
      await expectLater(_send(host, 'goal_progress:0', 4.5), completes);
      await tester.pump(const Duration(seconds: 1));
      expect(provider.progress, isEmpty);
    });

    testWidgets('delete stages the goal and offers Undo', (tester) async {
      final host = NativeTestHost.install();
      final provider = await _mountGoals(tester, [_goal('a', 'Read'), _goal('b', 'Run')]);

      await _send(host, 'goal:1', 'delete');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(provider.isGoalDeleteStaged('b'), isTrue);
      expect(find.text(_l10n.goalDeleted), findsOneWidget);
      expect(find.byType(AlertDialog), findsNothing, reason: 'goal deletes are Undo-only (D5)');

      await tester.tap(find.text(_l10n.undo));
      await tester.pumpAndSettle();
      expect(provider.goals.map((goal) => goal.id), ['a', 'b']);
      expect(provider.deletes, isEmpty);
    });

    testWidgets('adding past the maximum explains the limit instead of opening the sheet', (tester) async {
      final host = NativeTestHost.install();
      await _mountGoals(tester, [for (var i = 0; i < maxGoalCount; i++) _goal('$i', 'Goal $i')]);

      await _send(host, 'goals_add');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.text(_l10n.maximumGoalsAllowed(maxGoalCount)), findsOneWidget);
      expect(find.byType(GoalFormSheet), findsNothing);
    });

    testWidgets('tapping a goal opens its editor through the existing owner', (tester) async {
      final host = NativeTestHost.install();
      await _mountGoals(tester, [_goal('a', 'Read')]);
      await _send(host, 'goal:0');
      await tester.pumpAndSettle();
      final sheet = tester.widget<GoalFormSheet>(find.byType(GoalFormSheet));
      expect(sheet.goal?.id, 'a');
      expect(sheet.emojiChoices, goalEmojiChoices);
      expect(sheet.onDelete, isNotNull);
    });

    testWidgets('without the preview the page is the Flutter list', (tester) async {
      final provider = _FakeGoals([_goal('a', 'Read')]);
      addTearDown(provider.dispose);
      await tester.pumpWidget(_app(const GoalsPage(), provider));
      await tester.pumpAndSettle();
      expect(find.byType(IosNativeSurface), findsNothing);
      expect(find.byType(GoalsWidget), findsOneWidget);
      expect(find.text('Read'), findsOneWidget);
    });
  });

  group('Goal form', () {
    Future<void> open(WidgetTester tester,
        {Goal? goal, GoalSaveCallback? onSave, VoidCallback? onDelete, String? emoji}) async {
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => showGoalFormSheet(
              context,
              goal: goal,
              onSave: onSave ?? (_, __, ___, ____) {},
              onDelete: onDelete,
              emojiChoices: goal == null ? const [] : goalEmojiChoices,
              initialEmoji: emoji,
            ),
            child: const Text('open'),
          ),
        ),
      )));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
    }

    IosNativeEdit edit(WidgetTester tester) => tester.widget<IosNativeEdit>(find.byType(IosNativeEdit));
    NativeRow row(WidgetTester tester, String id) => [
          ...edit(tester).toolbar,
          ...edit(tester).sections.expand((section) => section.rows)
        ].singleWhere((row) => row.id == id);

    testWidgets('validation and the dirty guard match the Flutter form', (tester) async {
      final saved = <(String, double, double, String?)>[];
      await open(tester, onSave: (title, current, target, emoji) => saved.add((title, current, target, emoji)));

      expect(edit(tester).title, _l10n.addGoal);
      expect(edit(tester).isDirty, isFalse);
      expect(row(tester, 'goal_save').enabled, isFalse, reason: 'a goal needs a title');
      expect(row(tester, 'goal_save').title, _l10n.addGoal);
      expect(row(tester, 'goal_current').keyboard, 'decimal');
      expect(row(tester, 'goal_target').keyboard, 'decimal');
      expect(edit(tester).sections.expand((section) => section.rows).map((row) => row.id),
          ['goal_title', 'goal_current', 'goal_target'],
          reason: 'a new goal has no icon choice and no delete');

      await row(tester, 'goal_title').action!('   ');
      await tester.pump();
      expect(edit(tester).isDirty, isFalse, reason: 'whitespace is not an edit');
      expect(row(tester, 'goal_save').enabled, isFalse);

      await row(tester, 'goal_title').action!('Read');
      await row(tester, 'goal_target').action!('not a number');
      await tester.pump();
      expect(edit(tester).isDirty, isTrue);
      expect(row(tester, 'goal_save').enabled, isTrue);
      expect(
          [...edit(tester).toolbar, ...edit(tester).sections.expand((s) => s.rows)].every((row) => row.valid), isTrue);

      await row(tester, 'goal_save').action!(null);
      await tester.pumpAndSettle();
      expect(saved, [('Read', 0.0, 100.0, null)], reason: 'an unreadable target keeps the default, as in Flutter');
      expect(find.byType(GoalFormSheet), findsNothing);
    });

    testWidgets('a chosen emoji is saved, including a keyword emoji the picker does not list', (tester) async {
      String? savedEmoji;
      var deleted = 0;
      await open(tester,
          goal: _goal('a', 'Lose weight'),
          emoji: '⚖️',
          onSave: (_, __, ___, emoji) => savedEmoji = emoji,
          onDelete: () => deleted++);

      expect(edit(tester).title, _l10n.editGoal);
      final choice = row(tester, 'goal_emoji');
      expect(choice.kind, 'choice');
      expect(choice.value, '⚖️');
      expect(choice.options.keys.first, '⚖️');
      expect(choice.options.keys.skip(1), goalEmojiChoices);
      expect(choice.valid, isTrue);
      expect(row(tester, 'goal_delete').destructive, isTrue);

      await choice.action!('🔥');
      await tester.pump();
      expect(edit(tester).isDirty, isTrue);
      await row(tester, 'goal_save').action!(null);
      await tester.pumpAndSettle();
      expect(savedEmoji, '🔥');
      expect(deleted, 0);
    });

    testWidgets('delete closes the sheet and hands over to the Undo path', (tester) async {
      var deleted = 0;
      await open(tester, goal: _goal('a', 'Read'), emoji: '📚', onDelete: () => deleted++);
      await row(tester, 'goal_delete').action!(null);
      await tester.pumpAndSettle();
      expect(deleted, 1);
      expect(find.byType(GoalFormSheet), findsNothing);
    });

    test('saveGoal persists the chosen emoji through the existing owner', () async {
      final provider = _FakeGoals([]);
      addTearDown(provider.dispose);
      final emojis = GoalEmojis();
      addTearDown(emojis.dispose);
      await saveGoal(provider, emojis, _goal('a', 'Read'), 'Read more', 3, 10, '🔥');

      expect(provider.updates, [('a', 'Read more')]);
      expect(emojis.of('a'), '🔥');
      final stored = (await SharedPreferences.getInstance()).getString('goals_tracker_emojis');
      expect(json.decode(stored!), {'a': '🔥'});

      final reloaded = GoalEmojis();
      addTearDown(reloaded.dispose);
      await reloaded.load();
      expect(reloaded.of('a'), '🔥');
    });

    test('new goals start with a keyword emoji', () {
      expect(goalSmartEmoji('Read 12 books'), '📚');
      expect(goalSmartEmoji('Something else'), '🎯');
    });
  });

  group('Shared tasks', () {
    testWidgets('accepting from the deep link sheet refreshes the action items owner once', (tester) async {
      final actionItems = _FakeActionItems();
      addTearDown(actionItems.dispose);
      await tester.pumpWidget(NativeTestHost.app(ChangeNotifierProvider<ActionItemsProvider>.value(
        value: actionItems,
        child: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showSharedTasksSheet(context,
                  token: 'token',
                  data: {
                    'sender_name': 'Sam',
                    'tasks': [
                      {'description': 'Buy milk', 'due_at': null},
                    ],
                  },
                  acceptSharedTasks: (_) async => {'count': 1}),
              child: const Text('open'),
            ),
          ),
        ),
      )));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text(_l10n.sharedTasksAddButton(1)));
      await tester.pumpAndSettle();
      expect(actionItems.refreshes, 1);
      expect(find.byType(AcceptSharedTasksSheet), findsNothing);
    });

    final data = <String, dynamic>{
      'sender_name': 'Sam',
      'tasks': [
        {'description': 'Buy milk', 'due_at': '2026-10-09T12:00:00Z'},
        {'description': 'Call back', 'due_at': null},
      ],
    };

    // showOmiSheet's native branch needs the compile-time flag, so this mounts the sheet in the same
    // shell itself; the host test covers the production wiring on Simulator.
    Future<NativeTestHost> openNative(WidgetTester tester, Completer<Map<String, dynamic>?> accept,
        {required void Function() onRequest, required VoidCallback onAccepted}) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => showOmiSurfaceSheet<void>(
              context: context,
              builder: (_) => FractionallySizedBox(
                heightFactor: 0.9,
                child: AcceptSharedTasksSheet(
                  native: true,
                  token: 'token',
                  senderName: 'Sam',
                  tasks: [
                    for (final task in data['tasks'] as List) Map<String, dynamic>.from(task as Map),
                  ],
                  onAccepted: onAccepted,
                  acceptSharedTasks: (token) {
                    onRequest();
                    return accept.future;
                  },
                ),
              ),
            ),
            child: const Text('open'),
          ),
        ),
      )));
      await tester.tap(find.text('open'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await NativeTestHost.settle(tester);
      return host;
    }

    testWidgets('a failed native accept re-enables Accept and keeps the sheet', (tester) async {
      final accept = Completer<Map<String, dynamic>?>();
      var requests = 0;
      var refreshed = 0;
      final host = await openNative(tester, accept, onRequest: () => requests++, onAccepted: () => refreshed++);
      unawaited(_send(host, 'shared_tasks_accept'));
      await tester.pump();
      expect(_row(tester, 'shared_tasks_accept').enabled, isFalse);
      accept.complete(null);
      await tester.pump();
      await tester.pump();
      expect(requests, 1);
      expect(refreshed, 0);
      expect(find.byType(AcceptSharedTasksSheet), findsOneWidget);
      expect(_row(tester, 'shared_tasks_accept').enabled, isTrue);
    });

    testWidgets('the native sheet lists the tasks and accepts once', (tester) async {
      final accept = Completer<Map<String, dynamic>?>();
      var requests = 0;
      var refreshed = 0;
      final host = await openNative(tester, accept, onRequest: () => requests++, onAccepted: () => refreshed++);

      expect(find.byType(UiKitView), findsOneWidget);
      final rows = _surfaceRows(tester);
      expect(rows.every((row) => row.valid), isTrue);
      expect(rows.map((row) => row.id),
          ['shared_tasks_close', 'shared_tasks_accept', 'shared_tasks_sender', 'shared_task:0', 'shared_task:1']);
      expect(_row(tester, 'shared_tasks_sender').title, _l10n.sharedTasksTitle('Sam', 2));
      expect(_row(tester, 'shared_task:0').title, 'Buy milk');
      expect(_row(tester, 'shared_task:0').subtitle, startsWith(_l10n.taskDueDate('').trim()));
      expect(_row(tester, 'shared_task:1').subtitle, '');
      expect(_row(tester, 'shared_tasks_accept').title, _l10n.sharedTasksAddButton(2));

      unawaited(_send(host, 'shared_tasks_accept'));
      unawaited(_send(host, 'shared_tasks_accept'));
      await tester.pump();
      expect(requests, 1);
      expect(_row(tester, 'shared_tasks_accept').enabled, isFalse);

      accept.complete({'count': 2});
      await tester.pumpAndSettle();
      expect(requests, 1);
      expect(refreshed, 1);
      expect(find.byType(AcceptSharedTasksSheet), findsNothing);
    });

    testWidgets('off iOS or without the preview the deep link keeps the transparent modal sheet', (tester) async {
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () => showSharedTasksSheet(context, token: 'token', data: data, onAccepted: () {}),
            child: const Text('open'),
          ),
        ),
      )));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      final sheet = tester.widget<AcceptSharedTasksSheet>(find.byType(AcceptSharedTasksSheet));
      expect(sheet.native, isFalse);
      expect(sheet.tasks.map((task) => task['description']), ['Buy milk', 'Call back']);
      final route = ModalRoute.of(tester.element(find.byType(AcceptSharedTasksSheet)));
      expect(route, isA<ModalBottomSheetRoute<dynamic>>());
      expect(route, isNot(isA<OmiSheetRoute<dynamic>>()));
      expect(find.byType(IosNativeSurface), findsNothing);
    });

    testWidgets('the preview shell keeps one header when the native renderer is unavailable', (tester) async {
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
        body: Builder(
          builder: (context) => TextButton(
            onPressed: () =>
                showSharedTasksSheet(context, token: 'token', data: data, onAccepted: () {}, nativePreview: true),
            child: const Text('open'),
          ),
        ),
      )));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(ModalRoute.of(tester.element(find.byType(AcceptSharedTasksSheet))), isA<OmiSheetRoute<dynamic>>());
      expect(find.text(_l10n.sharedTasksTitle('Sam', 2)), findsOneWidget);
      expect(find.byTooltip(_l10n.close), findsOneWidget);
    });
  });
}
