import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/goals.dart';

class GoalsProvider extends ChangeNotifier {
  static const String _goalsStorageKey = 'goals_tracker_local_goals';

  List<Goal> _goals = [];
  bool _isLoading = true;

  // Track last goal deletion to prevent API sync from resurrecting deleted goals
  DateTime? _lastGoalDeletion;

  List<Goal> get goals => _goals;
  bool get isLoading => _isLoading;

  /// Initialize the provider by loading goals
  Future<void> init() async {
    await loadGoals();
  }

  /// Load goals from local storage first, then sync with API
  Future<void> loadGoals() async {
    _isLoading = true;
    notifyListeners();

    // Load from local storage first (most up-to-date with recent deletions/changes)
    await _loadFromLocalStorage();

    // Then sync with API in the background
    await _syncWithApi();

    _isLoading = false;
    notifyListeners();
  }

  Future<void> _loadFromLocalStorage() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final goalsJson = prefs.getString(_goalsStorageKey);
      if (goalsJson != null) {
        final List<dynamic> decoded = jsonDecode(goalsJson);
        _goals = decoded.map((e) => Goal.fromJson(e)).toList();
        notifyListeners();
      }
    } catch (_) {}
  }

  Future<void> _syncWithApi() async {
    // Skip if we just deleted a goal to prevent resurrecting it
    final now = DateTime.now();
    final skipApiSync = _lastGoalDeletion != null && now.difference(_lastGoalDeletion!) < const Duration(seconds: 3);

    if (skipApiSync) return;

    try {
      final goals = await getAllGoals();
      if (goals.isNotEmpty) {
        _goals = goals;
        await _saveToLocalStorage();
        notifyListeners();
      }
    } catch (_) {}
  }

  Future<void> _saveToLocalStorage() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final goalsJson = jsonEncode(_goals.map((g) => g.toJson()).toList());
      await prefs.setString(_goalsStorageKey, goalsJson);
    } catch (_) {}
  }

  /// Create a new goal
  Future<Goal?> createGoal({
    required String title,
    required String goalType,
    required double targetValue,
    double currentValue = 0,
    double minValue = 0,
    double maxValue = 10,
    String? unit,
  }) async {
    final goal = await createGoalApi(
      title: title,
      goalType: goalType,
      targetValue: targetValue,
      currentValue: currentValue,
      minValue: minValue,
      maxValue: maxValue,
      unit: unit,
    );

    if (goal != null) {
      _goals.add(goal);
      await _saveToLocalStorage();
      notifyListeners();
    }

    return goal;
  }

  /// Update an existing goal
  Future<Goal?> updateGoal(
    String goalId, {
    String? title,
    double? targetValue,
    double? currentValue,
    double? minValue,
    double? maxValue,
    String? unit,
  }) async {
    final updatedGoal = await updateGoalApi(
      goalId,
      title: title,
      targetValue: targetValue,
      currentValue: currentValue,
      minValue: minValue,
      maxValue: maxValue,
      unit: unit,
    );

    if (updatedGoal != null) {
      final index = _goals.indexWhere((g) => g.id == goalId);
      if (index != -1) {
        _goals[index] = updatedGoal;
        await _saveToLocalStorage();
        notifyListeners();
      }
    }

    return updatedGoal;
  }

  /// Update goal progress only
  Future<Goal?> updateGoalProgress(String goalId, double currentValue) async {
    final updatedGoal = await updateGoalProgressApi(goalId, currentValue);

    if (updatedGoal != null) {
      final index = _goals.indexWhere((g) => g.id == goalId);
      if (index != -1) {
        _goals[index] = updatedGoal;
        await _saveToLocalStorage();
        notifyListeners();
      }
    }

    return updatedGoal;
  }

  /// Delete a goal
  Future<bool> deleteGoal(String goalId) async {
    _lastGoalDeletion = DateTime.now();

    // Remove from local state immediately (optimistic update)
    _goals.removeWhere((g) => g.id == goalId);
    await _saveToLocalStorage();
    notifyListeners();

    // Then delete from server
    final success = await deleteGoalApi(goalId);
    return success;
  }

  /// Refresh goals from API
  Future<void> refresh() async {
    _lastGoalDeletion = null; // Reset deletion flag to allow API sync
    await loadGoals();
  }
}

// Rename API functions to avoid conflicts with provider methods
Future<Goal?> createGoalApi({
  required String title,
  required String goalType,
  required double targetValue,
  double currentValue = 0,
  double minValue = 0,
  double maxValue = 10,
  String? unit,
}) {
  return createGoal(
    title: title,
    goalType: goalType,
    targetValue: targetValue,
    currentValue: currentValue,
    minValue: minValue,
    maxValue: maxValue,
    unit: unit,
  );
}

Future<Goal?> updateGoalApi(
  String goalId, {
  String? title,
  double? targetValue,
  double? currentValue,
  double? minValue,
  double? maxValue,
  String? unit,
}) {
  return updateGoal(
    goalId,
    title: title,
    targetValue: targetValue,
    currentValue: currentValue,
    minValue: minValue,
    maxValue: maxValue,
    unit: unit,
  );
}

Future<Goal?> updateGoalProgressApi(String goalId, double currentValue) {
  return updateGoalProgress(goalId, currentValue);
}

Future<bool> deleteGoalApi(String goalId) {
  return deleteGoal(goalId);
}
