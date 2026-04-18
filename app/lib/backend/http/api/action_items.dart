import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

Future<ActionItemsResponse> getActionItems({
  int limit = 50,
  int offset = 0,
  bool? completed,
  String? conversationId,
  DateTime? startDate,
  DateTime? endDate,
}) async {
  String url = '${Env.apiBaseUrl}v1/action-items?limit=$limit&offset=$offset';

  if (completed != null) {
    url += '&completed=$completed';
  }
  if (conversationId != null) {
    url += '&conversation_id=$conversationId';
  }
  if (startDate != null) {
    url += '&start_date=${startDate.toUtc().toIso8601String()}';
  }
  if (endDate != null) {
    url += '&end_date=${endDate.toUtc().toIso8601String()}';
  }

  var response = await makeApiCall(url: url, headers: {}, method: 'GET', body: '');

  if (response == null) return ActionItemsResponse(actionItems: [], hasMore: false);

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return ActionItemsResponse.fromJson(jsonDecode(body));
  } else {
    Logger.debug('getActionItems error ${response.statusCode}');
    return ActionItemsResponse(actionItems: [], hasMore: false);
  }
}

Future<ActionItemWithMetadata?> createActionItem({
  required String description,
  DateTime? dueAt,
  String? conversationId,
  bool completed = false,
}) async {
  var requestBody = {'description': description, 'completed': completed};

  if (dueAt != null) {
    requestBody['due_at'] = dueAt.toUtc().toIso8601String();
  }
  if (conversationId != null) {
    requestBody['conversation_id'] = conversationId;
  }

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items',
    headers: {},
    method: 'POST',
    body: jsonEncode(requestBody),
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return ActionItemWithMetadata.fromJson(jsonDecode(body));
  } else {
    Logger.debug('createActionItem error ${response.statusCode}');
    return null;
  }
}

Future<ActionItemWithMetadata?> updateActionItem(
  String actionItemId, {
  String? description,
  bool? completed,
  DateTime? dueAt,
  bool clearDueAt = false, // Flag to explicitly clear due date
  bool? exported,
  DateTime? exportDate,
  String? exportPlatform,
  String? appleReminderId,
  int? sortOrder,
  int? indentLevel,
}) async {
  var requestBody = <String, dynamic>{};

  if (description != null) {
    requestBody['description'] = description;
  }
  if (completed != null) {
    requestBody['completed'] = completed;
  }
  // Handle dueAt - send ISO string if set, or null to clear deadline
  if (clearDueAt) {
    requestBody['due_at'] = null;
  } else if (dueAt != null) {
    requestBody['due_at'] = dueAt.toUtc().toIso8601String();
  }
  if (exported != null) {
    requestBody['exported'] = exported;
  }
  if (exportDate != null) {
    requestBody['export_date'] = exportDate.toUtc().toIso8601String();
  }
  if (exportPlatform != null) {
    requestBody['export_platform'] = exportPlatform;
  }
  if (appleReminderId != null) {
    requestBody['apple_reminder_id'] = appleReminderId;
  }
  if (sortOrder != null) {
    requestBody['sort_order'] = sortOrder;
  }
  if (indentLevel != null) {
    requestBody['indent_level'] = indentLevel;
  }

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/$actionItemId',
    headers: {},
    method: 'PATCH',
    body: jsonEncode(requestBody),
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return ActionItemWithMetadata.fromJson(jsonDecode(body));
  } else {
    Logger.debug('updateActionItem error ${response.statusCode}');
    return null;
  }
}

Future<bool> deleteActionItem(String actionItemId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/$actionItemId',
    headers: {},
    method: 'DELETE',
    body: '',
  );

  if (response == null) return false;

  return response.statusCode == 204;
}

// Task sharing
Future<Map<String, dynamic>?> shareActionItems(List<String> taskIds) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/share',
    headers: {},
    method: 'POST',
    body: jsonEncode({'task_ids': taskIds}),
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return jsonDecode(body) as Map<String, dynamic>;
  } else {
    Logger.debug('shareActionItems error ${response.statusCode}');
    return null;
  }
}

Future<Map<String, dynamic>?> getSharedActionItems(String token) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/shared/$token',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return jsonDecode(body) as Map<String, dynamic>;
  } else {
    Logger.debug('getSharedActionItems error ${response.statusCode}');
    return null;
  }
}

Future<Map<String, dynamic>?> acceptSharedActionItems(String token) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/accept',
    headers: {},
    method: 'POST',
    body: jsonEncode({'token': token}),
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return jsonDecode(body) as Map<String, dynamic>;
  } else {
    Logger.debug('acceptSharedActionItems error ${response.statusCode}');
    return null;
  }
}

// Batch update sort_order/indent_level
Future<bool> batchUpdateActionItems(List<Map<String, dynamic>> items) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/batch',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({'items': items}),
  );

  if (response == null) return false;

  if (response.statusCode == 200) {
    return true;
  } else {
    Logger.debug('batchUpdateActionItems error ${response.statusCode}');
    return false;
  }
}

// Apple Reminders sync
Future<PendingSyncResponse?> getPendingSyncItems({String platform = 'apple_reminders'}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/pending-sync?platform=$platform',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return PendingSyncResponse.fromJson(jsonDecode(body));
  } else {
    Logger.debug('getPendingSyncItems error ${response.statusCode}');
    return null;
  }
}

Future<bool> syncBatchUpdate(List<Map<String, dynamic>> items) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/sync-batch',
    headers: {},
    method: 'PATCH',
    body: jsonEncode({'items': items}),
  );

  if (response == null) return false;

  if (response.statusCode == 200) {
    return true;
  } else {
    Logger.debug('syncBatchUpdate error ${response.statusCode}');
    return false;
  }
}
