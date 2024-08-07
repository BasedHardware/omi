import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/backend/http/api/plugins.dart';

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

Future<ServerMessage> sendMessageServer(String text, {String? pluginId}) async {
  if (text.toLowerCase().contains("i want") && text.toLowerCase().contains("food from doordash")) {
    String food = text.split("I want")[1].split("food from doordash")[0].trim();
    bool orderStatus = await orderFoodFromDoorDash(food);
    return ServerMessage(
      id: 'doordash_order',
      createdAt: DateTime.now(),
      text: orderStatus ? 'Your order for $food has been placed successfully!' : 'Failed to place order for $food.',
      sender: MessageSender.ai,
      type: MessageType.text,
      pluginId: 'doordash',
      fromIntegration: false,
      memories: [],
    );
  }

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
