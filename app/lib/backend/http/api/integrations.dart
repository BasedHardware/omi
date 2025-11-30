import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

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
    debugPrint('getIntegration error ${response.statusCode}');
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
    debugPrint('saveIntegration error ${response.statusCode}');
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
    debugPrint('deleteIntegration error ${response.statusCode}');
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
    debugPrint('getIntegrationOAuthUrl error ${response.statusCode}');
    return null;
  }
}
