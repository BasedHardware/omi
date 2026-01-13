import 'dart:convert';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Response model for integration
class IntegrationResponse {
  final bool connected;
  final String appKey;

  IntegrationResponse({
    required this.connected,
    required this.appKey,
  });

  factory IntegrationResponse.fromJson(Map<String, dynamic> json) {
    return IntegrationResponse(
      connected: json['connected'] as bool? ?? false,
      appKey: json['app_key'] as String? ?? '',
    );
  }
}

/// Get integration connection status
Future<IntegrationResponse?> getIntegration(String appKey) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/integrations/$appKey',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return IntegrationResponse.fromJson(jsonDecode(body));
  } else {
    Logger.debug('getIntegration error ${response.statusCode}');
    return null;
  }
}

/// Save integration connection details
Future<bool> saveIntegration(String appKey, Map<String, dynamic> details) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/integrations/$appKey',
    headers: {},
    method: 'PUT',
    body: jsonEncode(details),
  );

  if (response == null) return false;

  if (response.statusCode == 200) {
    return true;
  } else {
    Logger.debug('saveIntegration error ${response.statusCode}');
    return false;
  }
}

/// Delete integration connection
Future<bool> deleteIntegration(String appKey) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/integrations/$appKey',
    headers: {},
    method: 'DELETE',
    body: '',
  );

  if (response == null) return false;

  if (response.statusCode == 204 || response.statusCode == 200) {
    return true;
  } else {
    Logger.debug('deleteIntegration error ${response.statusCode}');
    return false;
  }
}

/// Get OAuth URL for an integration
Future<String?> getIntegrationOAuthUrl(String appKey) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/integrations/$appKey/oauth-url',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var data = jsonDecode(body);
    return data['auth_url'] as String?;
  } else {
    Logger.debug('getIntegrationOAuthUrl error ${response.statusCode}');
    return null;
  }
}

/// GitHub repository model
class GitHubRepository {
  final String fullName;
  final String name;
  final String owner;
  final bool isPrivate;
  final String? description;
  final String updatedAt;

  GitHubRepository({
    required this.fullName,
    required this.name,
    required this.owner,
    required this.isPrivate,
    this.description,
    required this.updatedAt,
  });

  factory GitHubRepository.fromJson(Map<String, dynamic> json) {
    return GitHubRepository(
      fullName: json['full_name'] as String? ?? '',
      name: json['name'] as String? ?? '',
      owner: json['owner'] as String? ?? '',
      isPrivate: json['private'] as bool? ?? false,
      description: json['description'] as String?,
      updatedAt: json['updated_at'] as String? ?? '',
    );
  }
}

/// Get GitHub repositories
Future<List<GitHubRepository>> getGitHubRepositories() async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/integrations/github/repositories',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return [];

  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var data = jsonDecode(body);
    var repos = data['repositories'] as List? ?? [];
    return repos.map((repo) => GitHubRepository.fromJson(repo)).toList();
  } else {
    Logger.debug('getGitHubRepositories error ${response.statusCode}');
    return [];
  }
}

/// Set GitHub default repository
Future<bool> setGitHubDefaultRepo(String defaultRepo) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/integrations/github/default-repo?default_repo=${Uri.encodeComponent(defaultRepo)}',
    headers: {},
    method: 'PUT',
    body: '',
  );

  if (response == null) return false;

  if (response.statusCode == 200) {
    return true;
  } else {
    Logger.debug('setGitHubDefaultRepo error ${response.statusCode}');
    return false;
  }
}
