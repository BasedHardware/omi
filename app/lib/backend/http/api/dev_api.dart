import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/dev_api_key.dart';
import 'package:omi/env/env.dart';

class DevApi {
  static final String _baseUrl = '${Env.apiBaseUrl}v1/dev';

  static Future<List<DevApiKey>> getDevApiKeys() async {
    final response = await makeApiCall(
      url: '$_baseUrl/keys',
      headers: {},
      body: '{}',
      method: 'GET',
    );

    if (response != null && response.statusCode == 200) {
      final List<dynamic> body = jsonDecode(response.body);
      return body.map((dynamic item) => DevApiKey.fromJson(item)).toList();
    } else {
      throw Exception('Failed to load API keys: ${response?.body}');
    }
  }

  static Future<DevApiKeyCreated> createDevApiKey(String name, {List<String>? scopes}) async {
    final body = <String, dynamic>{'name': name};
    if (scopes != null) {
      body['scopes'] = scopes;
    }

    final response = await makeApiCall(
      url: '$_baseUrl/keys',
      headers: {},
      body: jsonEncode(body),
      method: 'POST',
    );

    if (response != null && response.statusCode == 200) {
      return DevApiKeyCreated.fromJson(jsonDecode(response.body));
    } else {
      throw Exception('Failed to create API key: ${response?.body}');
    }
  }

  static Future<void> deleteDevApiKey(String keyId) async {
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
