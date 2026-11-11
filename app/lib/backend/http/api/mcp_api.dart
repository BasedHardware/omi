import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/backend/schema/connector_access.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/env/env.dart';

class McpApi {
  static String get _baseUrl => '${Env.apiBaseUrl}v1/mcp';

  /// Offline fallback for older/unavailable scope-contract endpoints.
  static const List<String> readOnlyScopes = [
    'memories.read',
    'conversations.read',
    'action_items.read',
    'goals.read',
  ];

  static Future<List<McpApiKey>> getMcpApiKeys() async {
    final response = await makeApiCall(url: '$_baseUrl/keys', headers: {}, body: '{}', method: 'GET');

    if (response != null && response.statusCode == 200) {
      final List<dynamic> body = jsonDecode(response.body);
      return body.map((dynamic item) => McpApiKey.fromJson(item as Map<String, dynamic>)).toList();
    } else {
      throw Exception('Failed to load API keys: ${response?.body}');
    }
  }

  static Future<McpApiKeyCreated> createMcpApiKey(
    String name, {
    List<String>? scopes,
  }) async {
    final response = await makeApiCall(
      url: '$_baseUrl/keys',
      headers: {},
      body: jsonEncode({'name': name, 'scopes': scopes ?? await _defaultKeyScopes()}),
      method: 'POST',
    );

    if (response != null && response.statusCode == 200) {
      return McpApiKeyCreated.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    } else {
      throw Exception('Failed to create API key: ${response?.body}');
    }
  }

  static Future<List<String>> _defaultKeyScopes() async {
    try {
      final response = await makeApiCall(
        url: '$_baseUrl/keys/scopes',
        headers: {},
        body: '',
        method: 'GET',
        timeout: const Duration(seconds: 5),
        retries: 0,
      );
      final contract = response?.statusCode == 200 ? ConnectorAccess.fromJson(jsonDecode(response!.body)) : null;
      if (contract != null && contract.defaultScopes.isNotEmpty) return contract.defaultScopes;
    } catch (_) {
      // Older/offline backends retain the existing explicit read-only request.
    }
    Logger.debug('MCP scope contract unavailable; using read-only fallback');
    return readOnlyScopes;
  }

  /// OAuth grants live on the identity plane, which stays production even when mobile Beta serves
  /// product traffic from the development API (`Env.authApiBaseUrl`); ChatGPT's directory app
  /// grants there.
  static String get _grantsUrl => '${Env.authApiBaseUrl}v1/mcp/oauth/grants';

  /// The OAuth grants apps such as ChatGPT hold on this account, newest first. Each is a raw map
  /// (`id`, `client_id`, `scopes`, `revoked_at`, `status`, ...), revoked ones included.
  static Future<McpOauthGrants> getOauthGrants() async {
    final response = await makeApiCall(url: _grantsUrl, headers: {}, body: '', method: 'GET');

    if (response != null && response.statusCode == 200) {
      return McpOauthGrants.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
    } else {
      throw Exception('Failed to load OAuth grants: ${response?.statusCode}');
    }
  }

  static Future<void> revokeOauthGrant(String grantId) async {
    final response = await makeApiCall(url: '$_grantsUrl/$grantId', headers: {}, body: '', method: 'DELETE');

    if (response == null || response.statusCode != 204) {
      throw Exception('Failed to revoke OAuth grant: ${response?.statusCode}');
    }
  }

  static Future<void> deleteMcpApiKey(String keyId) async {
    final response = await makeApiCall(url: '$_baseUrl/keys/$keyId', headers: {}, body: '{}', method: 'DELETE');

    if (response == null || response.statusCode != 204) {
      throw Exception('Failed to delete API key: ${response?.body}');
    }
  }
}
