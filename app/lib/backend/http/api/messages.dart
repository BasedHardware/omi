import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/env/env.dart';

Future<List<ServerMessage>> getMessagesServer() async {
  // TODO: Add pagination
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/messages', headers: {}, method: 'GET', body: '');
  if (response == null) return [];
  debugPrint('getMessages: ${response.body}');
  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var decodedBody = jsonDecode(body) as List<dynamic>;
    if (decodedBody.isEmpty) {
      return [];
    }
    var messages = decodedBody.map((memory) => ServerMessage.fromJson(memory)).toList();
    debugPrint('getMessages length: ${messages.length}');
    return messages;
  }
  return [];
}

Future<List<ServerMessage>> clearChatServer() async {
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/clear-chat', headers: {}, method: 'DELETE', body: '');
  if (response == null) throw Exception('Failed to delete chat');
  if (response.statusCode == 200) {
    return [ServerMessage.fromJson(jsonDecode(response.body))];
  } else {
    throw Exception('Failed to delete chat');
  }
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
