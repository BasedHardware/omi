import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

/// Response model for task integrations
class TaskIntegrationsResponse {
  final Map<String, dynamic> integrations;
  final String? defaultApp;

  TaskIntegrationsResponse({
    required this.integrations,
    this.defaultApp,
  });

  factory TaskIntegrationsResponse.fromJson(Map<String, dynamic> json) {
    return TaskIntegrationsResponse(
      integrations: json['integrations'] as Map<String, dynamic>? ?? {},
      defaultApp: json['default_app'] as String?,
    );
  }
}

/// Get all task integrations for the current user
Future<TaskIntegrationsResponse?> getTaskIntegrations() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return TaskIntegrationsResponse.fromJson(jsonDecode(body));
  } else {
    debugPrint('getTaskIntegrations error ${response.statusCode}');
    return null;
  }
}

/// Get the user's default task integration app
Future<String?> getDefaultTaskIntegration() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/default',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var data = jsonDecode(body);
    return data['default_app'] as String?;
  } else {
    debugPrint('getDefaultTaskIntegration error ${response.statusCode}');
    return null;
  }
}

/// Set the user's default task integration app
Future<bool> setDefaultTaskIntegration(String appKey) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/default',
    headers: {},
    method: 'PUT',
    body: jsonEncode({'app_key': appKey}),
  );

  if (response == null) return false;

  if (response.statusCode == 200) {
    return true;
  } else {
    debugPrint('setDefaultTaskIntegration error ${response.statusCode}');
    return false;
  }
}

/// Save task integration connection details
Future<bool> saveTaskIntegration(String appKey, Map<String, dynamic> details) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/$appKey',
    headers: {},
    method: 'PUT',
    body: jsonEncode(details),
  );

  if (response == null) return false;

  if (response.statusCode == 200) {
    return true;
  } else {
    debugPrint('saveTaskIntegration error ${response.statusCode}');
    return false;
  }
}

/// Delete task integration connection
Future<bool> deleteTaskIntegration(String appKey) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/$appKey',
    headers: {},
    method: 'DELETE',
    body: '',
  );

  if (response == null) return false;

  if (response.statusCode == 204 || response.statusCode == 200) {
    return true;
  } else {
    debugPrint('deleteTaskIntegration error ${response.statusCode}');
    return false;
  }
}
