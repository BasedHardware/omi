import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/env/env.dart';

Uri _buildUri(String path, {Map<String, dynamic>? query}) {
  final base = Env.apiBaseUrl!; // ensured non-null at runtime
  final baseUri = Uri.parse(base);
  return baseUri.replace(
    path: '${baseUri.path.endsWith('/') ? baseUri.path.substring(0, baseUri.path.length - 1) : baseUri.path}$path',
    queryParameters: query?.map((key, value) => MapEntry(key, value?.toString())),
  );
}

Future<List<ChatSession>> listChatSessions({required String uid, required String appId}) async {
  final uri = _buildUri('/v2/chat-sessions', query: {'app_id': appId});
  final response = await makeApiCall(url: uri.toString(), headers: {}, body: '', method: 'GET');
  if (response == null) return [];
  if (response.statusCode == 200) {
    final body = utf8.decode(response.bodyBytes);
    final data = jsonDecode(body) as List<dynamic>;
    return ChatSession.fromJsonList(data);
  }
  debugPrint('listChatSessions error ${response.statusCode}: ${response.body}');
  return [];
}

Future<ChatSession?> createChatSession({required String uid, required String appId, String? title}) async {
  final uri = _buildUri('/v2/chat-sessions');
  final response = await makeApiCall(
    url: uri.toString(),
    headers: {},
    method: 'POST',
    body: jsonEncode({'app_id': appId, if (title != null && title.isNotEmpty) 'title': title}),
  );
  if (response == null) return null;
  if (response.statusCode == 200) {
    final body = utf8.decode(response.bodyBytes);
    return ChatSession.fromJson(jsonDecode(body) as Map<String, dynamic>);
  }
  debugPrint('createChatSession error ${response.statusCode}: ${response.body}');
  return null;
}

Future<bool> deleteChatSession({required String uid, required String sessionId}) async {
  final uri = _buildUri('/v2/chat-sessions/$sessionId');
  final response = await makeApiCall(url: uri.toString(), headers: {}, body: '', method: 'DELETE');
  if (response == null) return false;
  if (response.statusCode == 200) return true;
  debugPrint('deleteChatSession error ${response.statusCode}: ${response.body}');
  return false;
}
