import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/chat_session.dart';
// import 'package:omi/env/env.dart';

Future<List<ChatSession>> listChatSessions({required String uid, required List<String> appIds}) async {
  // Fetch chat sessions from all provided apps and combine them
  List<ChatSession> allSessions = [];

  for (String appId in appIds) {
    try {
      final uri = buildApiUri('/v2/chat-sessions', query: {'app_id': appId});
      final response = await makeApiCall(url: uri.toString(), headers: {}, body: '', method: 'GET');

      if (response != null && response.statusCode == 200) {
        final body = utf8.decode(response.bodyBytes);
        final data = jsonDecode(body) as List<dynamic>;
        final sessions = ChatSession.fromJsonList(data);
        allSessions.addAll(sessions);
      }
    } catch (e) {
      debugPrint('listChatSessions error for app $appId: $e');
      // Continue with other apps even if one fails
    }
  }

  // Remove duplicates by session ID
  final uniqueSessions = <String, ChatSession>{};
  for (final session in allSessions) {
    uniqueSessions[session.id] = session;
  }
  final deduplicatedSessions = uniqueSessions.values.toList();

  // Sort by creation date (newest first)
  deduplicatedSessions.sort((a, b) => b.createdAt.compareTo(a.createdAt));
  return deduplicatedSessions;
}

// PERFORMANCE FIX: Efficient function that makes ONE request instead of 4000+
Future<List<ChatSession>> listAllUserChatSessions({required String uid}) async {
  try {
    // Call backend without app_id parameter to get ALL user sessions
    final uri = buildApiUri('/v2/chat-sessions'); // No query parameters = all sessions
    final response = await makeApiCall(url: uri.toString(), headers: {}, body: '', method: 'GET');

    if (response != null && response.statusCode == 200) {
      final body = utf8.decode(response.bodyBytes);
      final data = jsonDecode(body) as List<dynamic>;
      final sessions = ChatSession.fromJsonList(data);

      // Sessions are already sorted by created_at DESC from backend
      return sessions;
    }
  } catch (e) {
    debugPrint('listAllUserChatSessions error: $e');
  }
  return [];
}

Future<ChatSession?> createChatSession({required String uid, required String appId, String? title}) async {
  final uri = buildApiUri('/v2/chat-sessions');

  final Map<String, dynamic> body = {
    'app_id': appId == 'omi' ? null : appId, // Send null for OMI app to maintain backward compatibility
    'title': title ?? 'New Chat', // Always send title, default to 'New Chat'
  };

  final response = await makeApiCall(
    url: uri.toString(),
    headers: {},
    method: 'POST',
    body: jsonEncode(body),
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
  final uri = buildApiUri('/v2/chat-sessions/$sessionId');
  final response = await makeApiCall(url: uri.toString(), headers: {}, body: '', method: 'DELETE');
  if (response == null) return false;
  if (response.statusCode == 200) return true;
  debugPrint('deleteChatSession error ${response.statusCode}: ${response.body}');
  return false;
}

Future<String?> generateChatSessionTitle(
    {required String uid, required String sessionId, required String firstMessage}) async {
  final uri = buildApiUri('/v2/chat-sessions/$sessionId/generate-title');

  final Map<String, dynamic> body = {
    'first_message': firstMessage,
  };

  final response = await makeApiCall(
    url: uri.toString(),
    headers: {},
    method: 'POST',
    body: jsonEncode(body),
  );

  if (response == null) return null;

  if (response.statusCode == 200) {
    final responseBody = utf8.decode(response.bodyBytes);
    final data = jsonDecode(responseBody) as Map<String, dynamic>;
    return data['title'] as String?;
  }
  debugPrint('generateChatSessionTitle error ${response.statusCode}: ${response.body}');
  return null;
}
