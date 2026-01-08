import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';

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

  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return ActionItemsResponse(actionItems: [], hasMore: false);

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return ActionItemsResponse.fromJson(jsonDecode(body));
  } else {
    debugPrint('getActionItems error ${response.statusCode}');
    return ActionItemsResponse(actionItems: [], hasMore: false);
  }
}

Future<ActionItemWithMetadata?> getActionItem(String actionItemId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/$actionItemId',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return ActionItemWithMetadata.fromJson(jsonDecode(body));
  } else {
    debugPrint('getActionItem error ${response.statusCode}');
    return null;
  }
}

Future<ActionItemWithMetadata?> createActionItem({
  required String description,
  DateTime? dueAt,
  String? conversationId,
  bool completed = false,
}) async {
  var requestBody = {
    'description': description,
    'completed': completed,
  };

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
    debugPrint('createActionItem error ${response.statusCode}');
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
    debugPrint('updateActionItem error ${response.statusCode}');
    return null;
  }
}

Future<ActionItemWithMetadata?> toggleActionItemCompletion(
  String actionItemId,
  bool completed,
) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/$actionItemId/completed?completed=$completed',
    headers: {},
    method: 'PATCH',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return ActionItemWithMetadata.fromJson(jsonDecode(body));
  } else {
    debugPrint('toggleActionItemCompletion error ${response.statusCode}');
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

// Conversation-specific action items
Future<ActionItemsResponse> getConversationActionItems(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/action-items',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return ActionItemsResponse(actionItems: [], hasMore: false);

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var data = jsonDecode(body);
    return ActionItemsResponse(
      actionItems:
          (data['action_items'] as List<dynamic>).map((item) => ActionItemWithMetadata.fromJson(item)).toList(),
      hasMore: false, // Conversation-specific calls don't have pagination
    );
  } else {
    debugPrint('getConversationActionItems error ${response.statusCode}');
    return ActionItemsResponse(actionItems: [], hasMore: false);
  }
}

Future<bool> deleteConversationActionItems(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/action-items',
    headers: {},
    method: 'DELETE',
    body: '',
  );

  if (response == null) return false;

  return response.statusCode == 204;
}

// Batch operations
Future<List<ActionItemWithMetadata>> createActionItemsBatch(
  List<Map<String, dynamic>> actionItems,
) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/action-items/batch',
    headers: {},
    method: 'POST',
    body: jsonEncode(actionItems),
  );

  if (response == null) return [];

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var data = jsonDecode(body);
    return (data['action_items'] as List<dynamic>).map((item) => ActionItemWithMetadata.fromJson(item)).toList();
  } else {
    debugPrint('createActionItemsBatch error ${response.statusCode}');
    return [];
  }
}
