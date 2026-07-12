import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';

import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/preferences.dart';

class GoalsProvider extends ChangeNotifier {
  static const String _legacyGoalsStorageKey = 'goals_tracker_local_goals';

  List<Goal> _goals = [];
  bool _isLoading = true;

  // Track last goal deletion to prevent API sync from resurrecting deleted goals
  DateTime? _lastGoalDeletion;
  int _sessionGeneration = 0;

  List<Goal> get goals => _goals;
  bool get isLoading => _isLoading;

  /// Initialize the provider by loading goals
  Future<void> init() async {
    await loadGoals();
  }

  /// Load goals from local storage first, then sync with API
  Future<void> loadGoals() async {
    final generation = _sessionGeneration;
    _isLoading = true;
    notifyListeners();

    // Load from local storage first (most up-to-date with recent deletions/changes)
    await _loadFromLocalStorage(generation);
    if (generation != _sessionGeneration) return;

    // Then sync with API in the background
    await _syncWithApi(generation);
    if (generation != _sessionGeneration) return;

    _isLoading = false;
    _notifyAfterFrame();
  }

  void _notifyAfterFrame() {
    SchedulerBinding.instance.addPostFrameCallback((_) => notifyListeners());
  }

  Future<void> _loadFromLocalStorage(int generation) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (generation != _sessionGeneration) return;
      SharedPreferencesUtil().scopeLegacyUserDataForCurrentUser();
      final storageKey = _goalsStorageKey;
      if (storageKey == null) return;
      final goalsJson = prefs.getString(storageKey);
      if (goalsJson != null) {
        final List<dynamic> decoded = jsonDecode(goalsJson);
        _goals = decoded.map((e) => Goal.fromJson(e)).toList();
        _notifyAfterFrame();
      }
    } catch (_) {}
  }

  Future<void> _syncWithApi(int generation) async {
    // Skip if we just deleted a goal to prevent resurrecting it
    final now = DateTime.now();
    final skipApiSync = _lastGoalDeletion != null && now.difference(_lastGoalDeletion!) < const Duration(seconds: 3);

    if (skipApiSync) return;

    try {
      final goals = await getAllGoals();
      if (generation != _sessionGeneration) return;
      if (goals.isNotEmpty) {
        _goals = goals;
        await _saveToLocalStorage();
        _notifyAfterFrame();
      }
    } catch (_) {}
  }

  Future<void> _saveToLocalStorage() async {
    try {
      final storageKey = _goalsStorageKey;
      if (storageKey == null) return;
      final prefs = await SharedPreferences.getInstance();
      final goalsJson = jsonEncode(_goals.map((g) => g.toJson()).toList());
      await prefs.setString(storageKey, goalsJson);
    } catch (_) {}
  }

  String? get _goalsStorageKey {
    final ownerUid = SharedPreferencesUtil().uid;
    return ownerUid.isEmpty ? null : '$_legacyGoalsStorageKey:$ownerUid';
  }

  void clearUserData() {
    _sessionGeneration++;
    _goals = [];
    _isLoading = false;
    _lastGoalDeletion = null;
    notifyListeners();
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
    final generation = _sessionGeneration;
    final goal = await createGoalApi(
      title: title,
      goalType: goalType,
      targetValue: targetValue,
      currentValue: currentValue,
      minValue: minValue,
      maxValue: maxValue,
      unit: unit,
    );
    if (generation != _sessionGeneration) return null;

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
    final generation = _sessionGeneration;
    final updatedGoal = await updateGoalApi(
      goalId,
      title: title,
      targetValue: targetValue,
      currentValue: currentValue,
      minValue: minValue,
      maxValue: maxValue,
      unit: unit,
    );
    if (generation != _sessionGeneration) return null;

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
    final generation = _sessionGeneration;
    final updatedGoal = await updateGoalProgressApi(goalId, currentValue);
    if (generation != _sessionGeneration) return null;

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
