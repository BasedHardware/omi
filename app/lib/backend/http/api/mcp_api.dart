import 'dart:convert';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/mcp_api_key.dart';
import 'package:omi/env/env.dart';

class McpApi {
  static final String _baseUrl = '${Env.apiBaseUrl}v1/mcp';

  static Future<List<McpApiKey>> getMcpApiKeys() async {
    final response = await makeApiCall(
      url: '$_baseUrl/keys',
      headers: {},
      body: '{}',
      method: 'GET',
    );

    if (response != null && response.statusCode == 200) {
      final List<dynamic> body = jsonDecode(response.body);
      return body.map((dynamic item) => McpApiKey.fromJson(item)).toList();
    } else {
      throw Exception('Failed to load API keys: ${response?.body}');
    }
  }

  static Future<McpApiKeyCreated> createMcpApiKey(String name) async {
    final response = await makeApiCall(
      url: '$_baseUrl/keys',
      headers: {},
      body: jsonEncode({'name': name}),
      method: 'POST',
    );

    if (response != null && response.statusCode == 200) {
      return McpApiKeyCreated.fromJson(jsonDecode(response.body));
    } else {
      throw Exception('Failed to create API key: ${response?.body}');
    }
  }

  static Future<void> deleteMcpApiKey(String keyId) async {
    final response = await makeApiCall(
      url: '$_baseUrl/keys/$keyId',
      headers: {},
      body: '{}',
      method: 'DELETE',
    );

    if (response == null || response.statusCode != 204) {
      throw Exception('Failed to delete API key: ${response?.body}');
    }
  }
}
