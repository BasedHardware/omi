import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/gen/wrapped_task_integrations_wire.g.dart' as wire;
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Response model for task integrations
class TaskIntegrationsResponse {
  final Map<String, dynamic> integrations;
  final String? defaultApp;

  TaskIntegrationsResponse({required this.integrations, this.defaultApp});

  factory TaskIntegrationsResponse.fromJson(Map<String, dynamic> json) {
    return TaskIntegrationsResponse.fromGenerated(wire.GeneratedTaskIntegrationsResponse.fromJson(json));
  }

  factory TaskIntegrationsResponse.fromGenerated(wire.GeneratedTaskIntegrationsResponse generated) {
    return TaskIntegrationsResponse(integrations: generated.integrations, defaultApp: generated.defaultApp);
  }

  wire.GeneratedTaskIntegrationsResponse toGenerated() {
    return wire.GeneratedTaskIntegrationsResponse(integrations: integrations, defaultApp: defaultApp);
  }
}

/// Get all task integrations for the current user
Future<TaskIntegrationsResponse?> getTaskIntegrations() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/task-integrations', headers: {}, method: 'GET', body: '');

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return TaskIntegrationsResponse.fromGenerated(
      wire.GeneratedTaskIntegrationsResponse.fromJson(jsonDecode(body) as Map<String, dynamic>),
    );
  } else {
    Logger.debug('getTaskIntegrations error ${response.statusCode}');
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
    Logger.debug('setDefaultTaskIntegration error ${response.statusCode}');
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
    Logger.debug('saveTaskIntegration error ${response.statusCode}');
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
    Logger.debug('deleteTaskIntegration error ${response.statusCode}');
    return false;
  }
}

/// Get OAuth URL for a task integration
Future<String?> getOAuthUrl(String appKey) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/$appKey/oauth-url',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    final data = wire.GeneratedOAuthUrlResponse.fromJson(jsonDecode(body) as Map<String, dynamic>);
    return data.authUrl;
  } else {
    Logger.debug('getOAuthUrl error ${response.statusCode}');
    return null;
  }
}

/// Create a task via backend integration API
Future<Map<String, dynamic>?> createTaskViaIntegration(
  String appKey, {
  required String title,
  String? description,
  DateTime? dueDate,
}) async {
  var requestBody = {
    'title': title,
    if (description != null) 'description': description,
    if (dueDate != null) 'due_date': dueDate.toUtc().toIso8601String(),
  };

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/$appKey/tasks',
    headers: {},
    method: 'POST',
    body: jsonEncode(requestBody),
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return wire.GeneratedCreateTaskResponse.fromJson(jsonDecode(body) as Map<String, dynamic>).toJson();
  } else {
    Logger.debug('createTaskViaIntegration error ${response.statusCode}');
    return null;
  }
}

/// Get Asana workspaces
Future<List<Map<String, dynamic>>?> getAsanaWorkspaces() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/asana/workspaces',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return wire.GeneratedAsanaWorkspacesResponse.fromJson(jsonDecode(body) as Map<String, dynamic>).workspaces ?? [];
  } else {
    Logger.debug('getAsanaWorkspaces error ${response.statusCode}');
    return null;
  }
}

/// Get Asana projects
Future<List<Map<String, dynamic>>?> getAsanaProjects(String workspaceGid) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/asana/projects/$workspaceGid',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return wire.GeneratedAsanaProjectsResponse.fromJson(jsonDecode(body) as Map<String, dynamic>).projects ?? [];
  } else {
    Logger.debug('getAsanaProjects error ${response.statusCode}');
    return null;
  }
}

/// Get ClickUp teams
Future<List<Map<String, dynamic>>?> getClickUpTeams() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/clickup/teams',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return wire.GeneratedClickUpTeamsResponse.fromJson(jsonDecode(body) as Map<String, dynamic>).teams ?? [];
  } else {
    Logger.debug('getClickUpTeams error ${response.statusCode}');
    return null;
  }
}

/// Get ClickUp spaces
Future<List<Map<String, dynamic>>?> getClickUpSpaces(String teamId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/clickup/spaces/$teamId',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return wire.GeneratedClickUpSpacesResponse.fromJson(jsonDecode(body) as Map<String, dynamic>).spaces ?? [];
  } else {
    Logger.debug('getClickUpSpaces error ${response.statusCode}');
    return null;
  }
}

/// Get ClickUp lists
Future<List<Map<String, dynamic>>?> getClickUpLists(String spaceId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/task-integrations/clickup/lists/$spaceId',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return wire.GeneratedClickUpListsResponse.fromJson(jsonDecode(body) as Map<String, dynamic>).lists ?? [];
  } else {
    Logger.debug('getClickUpLists error ${response.statusCode}');
    return null;
  }
}
