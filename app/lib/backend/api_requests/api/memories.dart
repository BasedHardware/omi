import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/shared.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/server/memory.dart';
import 'package:friend_private/backend/server/message.dart';
import 'package:friend_private/env/env.dart';
import 'package:tuple/tuple.dart';

Future<CreateMemoryResponse?> createMemoryServer({
  required DateTime startedAt,
  required DateTime finishedAt,
  required List<TranscriptSegment> transcriptSegments,
  Geolocation? geolocation,
  List<Tuple2<String, String>> photos = const [],
}) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories?language_code=${SharedPreferencesUtil().recordingsLanguage}',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'started_at': startedAt.toIso8601String(),
      'finished_at': finishedAt.toIso8601String(),
      'transcript_segments': transcriptSegments.map((segment) => segment.toJson()).toList(),
      'geolocation': geolocation?.toJson(),
      'photos': photos.map((photo) => {'base63': photo.item1, 'description': photo.item2}).toList(),
    }),
  );
  if (response == null) return null; // TODO: if fails should tell, do something
  debugPrint('createMemoryServer: ${response.body}');
  if (response.statusCode == 200) {
    return CreateMemoryResponse.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<List<ServerMemory>> getMemories() async {
  // TODO: Add pagination
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/memories', headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  debugPrint('getMemories: ${response.body}');
  if (response.statusCode == 200) {
    var memories = (jsonDecode(response.body) as List<dynamic>).map((memory) => ServerMemory.fromJson(memory)).toList();
    debugPrint('getMemories length: ${memories.length}');
    return memories;
  }
  return [];
}

Future<ServerMemory?> reProcessMemoryServer(String memoryId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/memories/$memoryId/reprocess?language_code=${SharedPreferencesUtil().recordingsLanguage}',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) return null;
  debugPrint('getMemories: ${response.body}');
  if (response.statusCode == 200) {
    return ServerMemory.fromJson(jsonDecode(response.body));
  }
  return null;
}

Future<List<ServerMessage>> getMessagesServer() async {
  // TODO: Add pagination
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/messages', headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  debugPrint('getMessages: ${response.body}');
  if (response.statusCode == 200) {
    var messages =
        (jsonDecode(response.body) as List<dynamic>).map((memory) => ServerMessage.fromJson(memory)).toList();
    debugPrint('getMessages length: ${messages.length}');
    return messages;
  }
  return [];
}

Future<ServerMessage> sendMessageServer(String text, {String? pluginId}) {
  return makeApiCall(
    url: '${Env.apiBaseUrl}v1/messages?plugin_id=$pluginId',
    headers: {},
    method: 'POST',
    body: jsonEncode({'text': text}),
  ).then((response) {
    if (response == null) throw Exception('Failed to send message');
    if (response.statusCode == 200) {
      return ServerMessage.fromJson(jsonDecode(response.body));
    } else {
      throw Exception('Failed to send message');
    }
  });
}

Future<ServerMessage> getInitialPluginMessage(String? pluginId) {
  return makeApiCall(
    url: '${Env.apiBaseUrl}v1/initial-message?plugin_id=$pluginId',
    headers: {},
    method: 'POST',
    body: '',
  ).then((response) {
    if (response == null) throw Exception('Failed to send message');
    if (response.statusCode == 200) {
      return ServerMessage.fromJson(jsonDecode(response.body));
    } else {
      throw Exception('Failed to send message');
    }
  });
}
