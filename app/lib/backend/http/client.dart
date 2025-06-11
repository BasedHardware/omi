import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:omi/backend/auth.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;
  ApiClient._internal();

  Future<Map<String, String>> _getHeaders() async {
    final token = await getIdToken();
    return {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
  }

  Future<http.Response> get(String path) async {
    final url = Uri.parse('${Env.apiBaseUrl}/$path');
    Logger.info('GET $url');
    final headers = await _getHeaders();
    return http.get(url, headers: headers);
  }

  Future<http.Response> post(String path, {Map<String, dynamic>? body}) async {
    final url = Uri.parse('${Env.apiBaseUrl}/$path');
    Logger.info('POST $url, body: $body');
    final headers = await _getHeaders();
    return http.post(url, headers: headers, body: jsonEncode(body));
  }

  Future<http.Response> patch(String path, {Map<String, dynamic>? body}) async {
    final url = Uri.parse('${Env.apiBaseUrl}/$path');
    Logger.info('PATCH $url, body: $body');
    final headers = await _getHeaders();
    return http.patch(url, headers: headers, body: jsonEncode(body));
  }
}
