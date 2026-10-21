import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/goals_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Goal _goal(String id) => Goal(
      id: id,
      title: 'Goal $id',
      goalType: 'numeric',
      targetValue: 10,
      currentValue: 2,
      minValue: 0,
      maxValue: 10,
      isActive: true,
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  Future<void> saveGoals(List<Goal> goals) async {
    SharedPreferences.setMockInitialValues({
      'uid': 'goals-test-user',
      'goals_tracker_local_goals:goals-test-user': jsonEncode(goals.map((goal) => goal.toJson()).toList()),
    });
    await SharedPreferencesUtil.init();
  }

  test('a goal the server did not delete comes back', () async {
    await saveGoals([_goal('a'), _goal('b')]);
    final provider = GoalsProvider();
    await provider.loadGoals();

    final deleted = await provider.deleteGoal('a');

    expect(deleted, isFalse);
    expect(provider.goals.map((goal) => goal.id), ['a', 'b']);
  });

  test('a failed goal fetch keeps the saved goals', () async {
    await saveGoals([_goal('a')]);
    final provider = GoalsProvider();

    await provider.loadGoals();

    expect(provider.goals.map((goal) => goal.id), ['a']);
  });

  test('an empty goal list from the server clears goals deleted elsewhere', () async {
    await saveGoals([_goal('a')]);
    final provider = GoalsProvider(goalsFetcher: () async => []);

    await provider.loadGoals();

    expect(provider.goals, isEmpty);
  });
}
