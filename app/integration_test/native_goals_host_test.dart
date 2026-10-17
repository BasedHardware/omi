import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/core/app_shell.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/action_items/widgets/accept_shared_tasks_sheet.dart';
import 'package:omi/pages/action_items/widgets/goal_form_sheet.dart';
import 'package:omi/pages/goals/goals_page.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/goals_provider.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

Goal _goal(String id, String title) => Goal(
      id: id,
      title: title,
      goalType: 'numeric',
      targetValue: 12,
      currentValue: 6,
      minValue: 0,
      maxValue: 12,
      isActive: true,
      createdAt: DateTime.utc(2026, 9, 1),
      updatedAt: DateTime.utc(2026, 9, 1),
    );

/// The existing goals owner with inert I/O: it reads a fixture list, and writes change that list and
/// refresh through the owner, so the native list shows what was saved.
class _FakeGoals extends GoalsProvider {
  _FakeGoals() : this._([_goal('g1', 'Read 12 books')]);
  _FakeGoals._(this.stored) : super(goalsFetcher: () async => stored.toList());

  final List<Goal> stored;

  @override
  Future<Goal?> createGoal({
    required String title,
    required String goalType,
    required double targetValue,
    double currentValue = 0,
    double minValue = 0,
    double maxValue = 10,
    String? unit,
  }) async {
    final goal = _goal('g${stored.length + 1}', title);
    stored.add(goal);
    await refresh();
    return goal;
  }

  @override
  Future<Goal?> updateGoal(String goalId,
      {String? title,
      double? targetValue,
      double? currentValue,
      double? minValue,
      double? maxValue,
      String? unit}) async {
    final index = stored.indexWhere((goal) => goal.id == goalId);
    stored[index] = _goal(goalId, title ?? stored[index].title);
    await refresh();
    return stored[index];
  }

  @override
  Future<Goal?> updateGoalProgress(String goalId, double currentValue) async => null;
}

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump(const Duration(milliseconds: 300));
  }
}

void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('Settings > Goals opens natively and add/edit round-trip through the existing owner', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final goals = _FakeGoals();
      addTearDown(goals.dispose);
      await tester.pumpWidget(nativeHostApp(
        Scaffold(
          body: Builder(
            builder: (context) => Center(
              child: TextButton(
                onPressed: () => openSettingsDestination(context, SettingsDestination.goals),
                child: const Text('Goals'),
              ),
            ),
          ),
        ),
        providers: [ChangeNotifierProvider<GoalsProvider>.value(value: goals)],
      ));
      await tester.tap(find.text('Goals'));
      await _settle(tester);
      expect(find.byType(GoalsPage), findsOneWidget);
      await checkNativeHost(tester, 'native-goals-shared-tasks-goals-dark');

      expect(nativeProjectedRow(tester, 'goal:0').subtitle, '6/12');
      expect(nativeProjectedRow(tester, 'goal_progress:0').kind, 'level');

      // Add: the toolbar opens the native form, whose Save reaches the existing owner.
      await nativeProjectedRow(tester, 'goals_add').action!(null);
      await _settle(tester);
      expect(find.byType(GoalFormSheet), findsOneWidget);
      await nativeProjectedRow(tester, 'goal_title').action!('Run 100 km');
      await tester.pump();
      await nativeProjectedRow(tester, 'goal_save').action!(null);
      await _settle(tester);
      expect(find.byType(GoalFormSheet), findsNothing);
      expect(nativeProjectedRow(tester, 'goal:1').title, endsWith('Run 100 km'));

      // Edit: a tap opens the goal in the same form.
      await nativeProjectedRow(tester, 'goal:0').action!(null);
      await _settle(tester);
      expect(find.byType(GoalFormSheet), findsOneWidget);
      await nativeProjectedRow(tester, 'goal_title').action!('Read 20 books');
      await tester.pump();
      await nativeProjectedRow(tester, 'goal_save').action!(null);
      await _settle(tester);
      expect(nativeProjectedRow(tester, 'goal:0').title, endsWith('Read 20 books'));
      expect(goals.stored.map((goal) => goal.title), ['Read 20 books', 'Run 100 km']);
      expect(find.byType(IosNativeSurface), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the shared-tasks deep link sheet opens natively and accepts once', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final tokens = <String>[];
      var accepted = 0;
      await tester.pumpWidget(nativeHostApp(
        Scaffold(
          body: Builder(
            builder: (context) => Center(
              child: TextButton(
                // The production entry point: the deep link handler opens exactly this.
                onPressed: () => showSharedTasksSheet(
                  context,
                  token: 'token',
                  data: {
                    'sender_name': 'Sam',
                    'tasks': [
                      {'description': 'Buy milk', 'due_at': '2026-10-09T12:00:00Z'},
                      {'description': 'Call back', 'due_at': null},
                    ],
                  },
                  onAccepted: () => accepted++,
                  acceptSharedTasks: (token) async {
                    tokens.add(token);
                    return {'count': 2};
                  },
                ),
                child: const Text('Shared tasks'),
              ),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('Shared tasks'));
      await _settle(tester);
      expect(tester.widget<AcceptSharedTasksSheet>(find.byType(AcceptSharedTasksSheet)).native, isTrue);
      await checkNativeHost(tester, 'native-goals-shared-tasks-shared-tasks-dark');

      expect(nativeProjectedRow(tester, 'shared_task:0').title, 'Buy milk');
      await nativeProjectedRow(tester, 'shared_tasks_accept').action!(null);
      await _settle(tester);
      expect(tokens, ['token']);
      expect(accepted, 1);
      expect(find.byType(AcceptSharedTasksSheet), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });
}
