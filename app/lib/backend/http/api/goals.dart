import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/goals_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Map<String, dynamic> _goalSuggestionJsonWithDefaults(Map<String, dynamic> json) {
  final normalized = Map<String, dynamic>.from(json);
  normalized['suggested_title'] ??= '';
  normalized['suggested_type'] ??= 'scale';
  normalized['suggested_target'] ??= 10;
  normalized['suggested_min'] ??= 0;
  normalized['suggested_max'] ??= 10;
  normalized['reasoning'] ??= '';
  return normalized;
}

double _goalResponseDouble(dynamic value, {double fallback = 0}) {
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value) ?? fallback;
  }
  return fallback;
}

bool _goalResponseBool(dynamic value, {bool fallback = true}) {
  if (value is bool) {
    return value;
  }
  if (value is String) {
    final normalized = value.trim().toLowerCase();
    if (normalized == 'true' || normalized == '1') {
      return true;
    }
    if (normalized == 'false' || normalized == '0') {
      return false;
    }
  }
  if (value is num) {
    return value != 0;
  }
  return fallback;
}

Map<String, dynamic> _goalJsonWithDefaults(Map<String, dynamic> json) {
  final normalized = Map<String, dynamic>.from(json);
  final now = DateTime.now().toUtc().toIso8601String();
  normalized['created_at'] ??= normalized['updated_at'] ?? now;
  normalized['updated_at'] ??= normalized['created_at'] ?? now;

  final id = normalized['id']?.toString() ?? '';
  normalized['id'] = id;
  normalized['goal_id'] ??= id;
  normalized['title'] ??= '';
  normalized['desired_outcome'] ??= normalized['title'];
  final status = normalized['status']?.toString();
  if (status == null || !{'background', 'focused', 'paused', 'achieved', 'abandoned'}.contains(status)) {
    normalized['status'] = _goalResponseBool(normalized['is_active'], fallback: true) ? 'background' : 'abandoned';
  }
  normalized['source'] ??= 'imported';

  final metric = normalized['metric'];
  if (metric is Map<String, dynamic>) {
    normalized['goal_type'] ??= metric['type'] ?? 'scale';
    normalized['target_value'] ??= _goalResponseDouble(metric['target']);
    normalized['current_value'] ??= _goalResponseDouble(metric['current']);
    normalized['min_value'] ??= _goalResponseDouble(metric['min']);
    final target = _goalResponseDouble(normalized['target_value']);
    normalized['max_value'] ??= metric['max'] ?? (target > 10 ? target : 10);
  } else {
    normalized['metric'] = null;
    normalized['goal_type'] ??= 'scale';
    normalized['target_value'] ??= 0;
    normalized['current_value'] ??= 0;
    normalized['min_value'] ??= 0;
    normalized['max_value'] ??= 10;
  }

  normalized['is_active'] ??= normalized['status'] != 'achieved' && normalized['status'] != 'abandoned';
  normalized['latest_progress_sequence'] ??= 0;
  return normalized;
}

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
    return Goal.fromGenerated(wire.GeneratedGoalResponse.fromJson(_goalJsonWithDefaults(json)));
  }

  factory Goal.fromGenerated(wire.GeneratedGoalResponse generated) {
    return Goal(
      id: generated.id,
      title: generated.title,
      goalType: generated.goalType,
      targetValue: generated.targetValue,
      currentValue: generated.currentValue,
      minValue: generated.minValue,
      maxValue: generated.maxValue,
      unit: generated.unit,
      isActive: generated.isActive,
      createdAt: generated.createdAt,
      updatedAt: generated.updatedAt,
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
      'created_at': createdAt.toUtc().toIso8601String(),
      'updated_at': updatedAt.toUtc().toIso8601String(),
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

  GoalHistoryEntry({required this.date, required this.value, required this.recordedAt});

  factory GoalHistoryEntry.fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedGoalHistoryEntryResponse.fromJson(json);
    return GoalHistoryEntry(date: generated.date, value: generated.value, recordedAt: generated.recordedAt);
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
    return GoalSuggestion.fromGenerated(
      wire.GeneratedGoalSuggestionResponse.fromJson(_goalSuggestionJsonWithDefaults(json)),
    );
  }

  factory GoalSuggestion.fromGenerated(wire.GeneratedGoalSuggestionResponse generated) {
    return GoalSuggestion(
      suggestedTitle: generated.suggestedTitle,
      suggestedType: generated.suggestedType,
      suggestedTarget: generated.suggestedTarget,
      suggestedMin: generated.suggestedMin,
      suggestedMax: generated.suggestedMax,
      reasoning: generated.reasoning,
    );
  }
}

/// Get current active goal (backward compatibility - returns first goal)
Future<Goal?> getCurrentGoal() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/goals', headers: {}, method: 'GET', body: '');
  if (response == null) return null;
  if (response.statusCode == 200) {
    try {
      return Goal.fromGenerated(
        wire.GeneratedGoalResponse.fromJson(_goalJsonWithDefaults(json.decode(response.body) as Map<String, dynamic>)),
      );
    } on FormatException catch (error) {
      Logger.warning('Skipping malformed current goal response: $error');
      return null;
    } on TypeError catch (error) {
      Logger.warning('Skipping malformed current goal response: $error');
      return null;
    }
  }
  return null;
}

/// Get all active goals (up to 4)
Future<List<Goal>> getAllGoals() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/goals/all', headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  Logger.debug('getAllGoals response: ${response.body}');
  if (response.statusCode == 200) {
    final goals = <Goal>[];
    for (final entry in json.decode(response.body) as List<dynamic>) {
      try {
        goals.add(
          Goal.fromGenerated(wire.GeneratedGoalResponse.fromJson(_goalJsonWithDefaults(entry as Map<String, dynamic>))),
        );
      } on FormatException catch (error) {
        Logger.warning('Skipping malformed goal in list: $error');
      } on TypeError catch (error) {
        Logger.warning('Skipping malformed goal in list: $error');
      }
    }
    return goals;
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
  Logger.debug('createGoal response: ${response.body}');
  if (response.statusCode == 200) {
    return Goal.fromGenerated(
      wire.GeneratedGoalResponse.fromJson(_goalJsonWithDefaults(json.decode(response.body) as Map<String, dynamic>)),
    );
  }
  return null;
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
  Logger.debug('updateGoal response: ${response.body}');
  if (response.statusCode == 200) {
    return Goal.fromGenerated(
      wire.GeneratedGoalResponse.fromJson(_goalJsonWithDefaults(json.decode(response.body) as Map<String, dynamic>)),
    );
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
  Logger.debug('updateGoalProgress response: ${response.body}');
  if (response.statusCode == 200) {
    return Goal.fromGenerated(
      wire.GeneratedGoalResponse.fromJson(_goalJsonWithDefaults(json.decode(response.body) as Map<String, dynamic>)),
    );
  }
  return null;
}

/// Delete a goal
Future<bool> deleteGoal(String goalId) async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/goals/$goalId', headers: {}, method: 'DELETE', body: '');
  if (response == null) return false;
  if (response.statusCode == 200) {
    return wire.GeneratedGoalDeleteResponse.fromJson(json.decode(response.body) as Map<String, dynamic>).success;
  }
  return false;
}

/// Get AI-suggested goal based on user data
Future<GoalSuggestion?> suggestGoal() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/goals/suggest', headers: {}, method: 'GET', body: '');
  if (response == null) return null;
  Logger.debug('suggestGoal response: ${response.body}');
  if (response.statusCode == 200) {
    return GoalSuggestion.fromGenerated(
      wire.GeneratedGoalSuggestionResponse.fromJson(
        _goalSuggestionJsonWithDefaults(json.decode(response.body) as Map<String, dynamic>),
      ),
    );
  }
  return null;
}

/// Get AI-generated advice for current goal
Future<String?> getGoalAdvice() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/goals/advice', headers: {}, method: 'GET', body: '');
  if (response == null) return null;
  Logger.debug('getGoalAdvice response: ${response.body}');
  if (response.statusCode == 200) {
    var decoded = json.decode(response.body);
    return wire.GeneratedAdviceResponse.fromJson(decoded as Map<String, dynamic>).advice;
  }
  return null;
}
