import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';

import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/preferences.dart';

typedef GoalsFetcher = Future<List<Goal>?> Function();

class GoalsProvider extends ChangeNotifier {
  static const String _legacyGoalsStorageKey = 'goals_tracker_local_goals';

  GoalsProvider({GoalsFetcher? goalsFetcher}) : _goalsFetcher = goalsFetcher ?? getAllGoals;

  final GoalsFetcher _goalsFetcher;

  List<Goal> _goals = [];
  bool _isLoading = true;

  // Track last goal deletion to prevent API sync from resurrecting deleted goals
  DateTime? _lastGoalDeletion;
  int _sessionGeneration = 0;

  // Deletes waiting for their Undo toast to close (docs/ux-contract.md §4).
  final Map<String, ({Goal goal, int index})> _stagedDeletes = {};

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
      final goals = await _goalsFetcher();
      if (generation != _sessionGeneration) return;
      if (goals != null) {
        // A goal waiting on its Undo toast stays hidden until the delete commits or is undone.
        _goals = goals.where((g) => !_stagedDeletes.containsKey(g.id)).toList();
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
    _stagedDeletes.clear();
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
    final generation = _sessionGeneration;
    _lastGoalDeletion = DateTime.now();

    // Remove from local state immediately (optimistic update)
    final index = _goals.indexWhere((g) => g.id == goalId);
    final removed = index == -1 ? null : _goals.removeAt(index);
    await _saveToLocalStorage();
    notifyListeners();

    // Then delete from server
    final success = await deleteGoalApi(goalId);
    if (!success && removed != null && generation == _sessionGeneration && !_goals.any((g) => g.id == goalId)) {
      _goals.insert(index.clamp(0, _goals.length), removed);
      await _saveToLocalStorage();
      notifyListeners();
    }
    return success;
  }

  /// Hides the goal now and holds its server delete until [commitStagedGoalDelete];
  /// [undoStagedGoalDelete] puts it back. Swipe and sheet deletes go through this so they can offer
  /// Undo (D5) — see `deleteGoalWithUndo`.
  void stageDeleteGoal(String goalId) {
    if (_stagedDeletes.containsKey(goalId)) return;
    final index = _goals.indexWhere((g) => g.id == goalId);
    if (index == -1) return;
    _stagedDeletes[goalId] = (goal: _goals.removeAt(index), index: index);
    notifyListeners();
  }

  /// Restores a goal hidden by [stageDeleteGoal]. False when it was not staged.
  bool undoStagedGoalDelete(String goalId) {
    final staged = _stagedDeletes.remove(goalId);
    if (staged == null) return false;
    if (!_goals.any((g) => g.id == goalId)) {
      _goals.insert(staged.index.clamp(0, _goals.length), staged.goal);
    }
    notifyListeners();
    return true;
  }

  /// Deletes a goal hidden by [stageDeleteGoal] on the server; on failure it comes back.
  Future<bool> commitStagedGoalDelete(String goalId) async {
    final staged = _stagedDeletes.remove(goalId);
    if (staged == null) return false;
    // Put it back for one frame's worth of bookkeeping, then run the ordinary delete (optimistic
    // removal, local storage, server call, rollback on failure).
    if (!_goals.any((g) => g.id == goalId)) {
      _goals.insert(staged.index.clamp(0, _goals.length), staged.goal);
    }
    return deleteGoal(goalId);
  }

  @visibleForTesting
  bool isGoalDeleteStaged(String goalId) => _stagedDeletes.containsKey(goalId);

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
