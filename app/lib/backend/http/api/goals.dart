import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

/// Goal model
class Goal {
  final String id;
  final String title;
  final String goalType; // 'boolean', 'scale', 'numeric'
  final double targetValue;
  final double currentValue;
  final double minValue;
  final double maxValue;
  final String? unit;
  final bool isActive;
  final DateTime createdAt;
  final DateTime updatedAt;

  Goal({
    required this.id,
    required this.title,
    required this.goalType,
    required this.targetValue,
    required this.currentValue,
    required this.minValue,
    required this.maxValue,
    this.unit,
    required this.isActive,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Goal.fromJson(Map<String, dynamic> json) {
    return Goal(
      id: json['id'] ?? '',
      title: json['title'] ?? '',
      goalType: json['goal_type'] ?? 'scale',
      targetValue: (json['target_value'] ?? 0).toDouble(),
      currentValue: (json['current_value'] ?? 0).toDouble(),
      minValue: (json['min_value'] ?? 0).toDouble(),
      maxValue: (json['max_value'] ?? 10).toDouble(),
      unit: json['unit'],
      isActive: json['is_active'] ?? true,
      createdAt: json['created_at'] != null 
          ? DateTime.parse(json['created_at']) 
          : DateTime.now(),
      updatedAt: json['updated_at'] != null 
          ? DateTime.parse(json['updated_at']) 
          : DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'goal_type': goalType,
      'target_value': targetValue,
      'current_value': currentValue,
      'min_value': minValue,
      'max_value': maxValue,
      'unit': unit,
      'is_active': isActive,
    };
  }

  double get progressPercentage {
    // For numeric goals, progress is simply currentValue / targetValue
    if (targetValue <= 0) return currentValue > 0 ? 1.0 : 0.0;
    return (currentValue / targetValue).clamp(0.0, 1.0);
  }
}

/// Goal progress history entry
class GoalHistoryEntry {
  final String date;
  final double value;
  final DateTime recordedAt;

  GoalHistoryEntry({
    required this.date,
    required this.value,
    required this.recordedAt,
  });

  factory GoalHistoryEntry.fromJson(Map<String, dynamic> json) {
    return GoalHistoryEntry(
      date: json['date'] ?? '',
      value: (json['value'] ?? 0).toDouble(),
      recordedAt: json['recorded_at'] != null 
          ? DateTime.parse(json['recorded_at']) 
          : DateTime.now(),
    );
  }
}

/// Goal suggestion from AI
class GoalSuggestion {
  final String suggestedTitle;
  final String suggestedType;
  final double suggestedTarget;
  final double suggestedMin;
  final double suggestedMax;
  final String reasoning;

  GoalSuggestion({
    required this.suggestedTitle,
    required this.suggestedType,
    required this.suggestedTarget,
    required this.suggestedMin,
    required this.suggestedMax,
    required this.reasoning,
  });

  factory GoalSuggestion.fromJson(Map<String, dynamic> json) {
    return GoalSuggestion(
      suggestedTitle: json['suggested_title'] ?? '',
      suggestedType: json['suggested_type'] ?? 'scale',
      suggestedTarget: (json['suggested_target'] ?? 10).toDouble(),
      suggestedMin: (json['suggested_min'] ?? 0).toDouble(),
      suggestedMax: (json['suggested_max'] ?? 10).toDouble(),
      reasoning: json['reasoning'] ?? '',
    );
  }
}

/// Get current active goal (backward compatibility - returns first goal)
Future<Goal?> getCurrentGoal() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    if (decoded != null && decoded is Map<String, dynamic> && decoded.isNotEmpty) {
      return Goal.fromJson(decoded);
    }
  }
  return null;
}

/// Get all active goals (up to 3)
Future<List<Goal>> getAllGoals() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals/all',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  debugPrint('getAllGoals response: ${response.body}');
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    if (decoded != null && decoded is List) {
      return decoded.map((e) => Goal.fromJson(e)).toList();
    }
  }
  return [];
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
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals',
    headers: {},
    method: 'POST',
    body: json.encode({
      'title': title,
      'goal_type': goalType,
      'target_value': targetValue,
      'current_value': currentValue,
      'min_value': minValue,
      'max_value': maxValue,
      'unit': unit,
    }),
  );
  if (response == null) return null;
  debugPrint('createGoal response: ${response.body}');
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    return Goal.fromJson(decoded);
  }
  return null;
}

/// Update an existing goal
Future<Goal?> updateGoal(String goalId, {
  String? title,
  double? targetValue,
  double? currentValue,
  double? minValue,
  double? maxValue,
  String? unit,
}) async {
  Map<String, dynamic> updates = {};
  if (title != null) updates['title'] = title;
  if (targetValue != null) updates['target_value'] = targetValue;
  if (currentValue != null) updates['current_value'] = currentValue;
  if (minValue != null) updates['min_value'] = minValue;
  if (maxValue != null) updates['max_value'] = maxValue;
  if (unit != null) updates['unit'] = unit;

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals/$goalId',
    headers: {},
    method: 'PATCH',
    body: json.encode(updates),
  );
  if (response == null) return null;
  debugPrint('updateGoal response: ${response.body}');
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    return Goal.fromJson(decoded);
  }
  return null;
}

/// Update goal progress only
Future<Goal?> updateGoalProgress(String goalId, double currentValue) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals/$goalId/progress?current_value=$currentValue',
    headers: {},
    method: 'PATCH',
    body: '',
  );
  if (response == null) return null;
  debugPrint('updateGoalProgress response: ${response.body}');
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    return Goal.fromJson(decoded);
  }
  return null;
}

/// Get goal progress history
Future<List<GoalHistoryEntry>> getGoalHistory(String goalId, {int days = 30}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals/$goalId/history?days=$days',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    if (decoded is List) {
      return decoded.map((e) => GoalHistoryEntry.fromJson(e)).toList();
    }
  }
  return [];
}

/// Delete a goal
Future<bool> deleteGoal(String goalId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals/$goalId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) return false;
  return response.statusCode == 200;
}

/// Get AI-suggested goal based on user data
Future<GoalSuggestion?> suggestGoal() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals/suggest',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('suggestGoal response: ${response.body}');
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    return GoalSuggestion.fromJson(decoded);
  }
  return null;
}

/// Get AI-generated advice for current goal
Future<String?> getGoalAdvice() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals/advice',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getGoalAdvice response: ${response.body}');
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    return decoded['advice'];
  }
  return null;
}

/// Get AI-generated advice for a specific goal
Future<String?> getGoalAdviceById(String goalId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/goals/$goalId/advice',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getGoalAdviceById response: ${response.body}');
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    return decoded['advice'];
  }
  return null;
}

