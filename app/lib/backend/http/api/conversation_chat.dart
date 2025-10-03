import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/other/string_utils.dart';

// Models for conversation chat
class ConversationChatMessage {
  final String id;
  final String text;
  final DateTime createdAt;
  final String sender; // 'human' or 'ai'
  final String conversationId;
  final List<String> memoriesId;
  final List<String> actionItemsId;
  final bool reported;

  ConversationChatMessage({
    required this.id,
    required this.text,
    required this.createdAt,
    required this.sender,
    required this.conversationId,
    this.memoriesId = const [],
    this.actionItemsId = const [],
    this.reported = false,
  });

  factory ConversationChatMessage.fromJson(Map<String, dynamic> json) {
    return ConversationChatMessage(
      id: json['id'],
      text: json['text'],
      createdAt: DateTime.parse(json['created_at']),
      sender: json['sender'],
      conversationId: json['conversation_id'],
      memoriesId: List<String>.from(json['memories_id'] ?? []),
      actionItemsId: List<String>.from(json['action_items_id'] ?? []),
      reported: json['reported'] ?? false,
    );
  }

  bool get isFromUser => sender == 'human';
  bool get isFromAI => sender == 'ai';
}

class ConversationChatResponse {
  final ConversationChatMessage message;
  final bool askForNps;

  ConversationChatResponse({
    required this.message,
    required this.askForNps,
  });

  factory ConversationChatResponse.fromJson(Map<String, dynamic> json) {
    return ConversationChatResponse(
      message: ConversationChatMessage.fromJson(json),
      askForNps: json['ask_for_nps'] ?? false,
    );
  }
}

// API Functions
Future<List<ConversationChatMessage>> getConversationMessages(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/conversations/$conversationId/chat/messages',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return [];
  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var decodedBody = jsonDecode(body) as List<dynamic>;
    if (decodedBody.isEmpty) {
      return [];
    }
    var messages = decodedBody.map((messageJson) => ConversationChatMessage.fromJson(messageJson)).toList();
    debugPrint('getConversationMessages length: ${messages.length}');
    return messages;
  }
  debugPrint('getConversationMessages error ${response.statusCode}');
  return [];
}

Future<bool> clearConversationChat(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/conversations/$conversationId/chat/messages',
    headers: {},
    method: 'DELETE',
    body: '',
  );

  if (response == null) {
    return false;
  }

  return response.statusCode == 200;
}

// Parse conversation chat streaming chunks (similar to main chat)
ServerMessageChunk? parseConversationChatChunk(String line, String messageId) {
  if (line.startsWith('think: ')) {
    return ServerMessageChunk(messageId, line.substring(7).replaceAll("__CRLF__", "\n"), MessageChunkType.think);
  }

  if (line.startsWith('data: ')) {
    return ServerMessageChunk(messageId, line.substring(6).replaceAll("__CRLF__", "\n"), MessageChunkType.data);
  }

  if (line.startsWith('done: ')) {
    var text = decodeBase64(line.substring(6));
    var responseJson = json.decode(text);
    return ServerMessageChunk(
      messageId,
      text,
      MessageChunkType.done,
      message: ServerMessage(
        responseJson['id'],
        DateTime.parse(responseJson['created_at']).toLocal(),
        responseJson['text'],
        MessageSender.values.firstWhere((e) => e.toString().split('.').last == responseJson['sender']),
        MessageType.text,
        null, // appId
        false, // fromIntegration
        [], // files
        [], // filesId
        [], // memories
        askForNps: responseJson['ask_for_nps'] ?? false,
      ),
    );
  }

  return null;
}

Stream<ServerMessageChunk> sendConversationMessageStream(String conversationId, String text) async* {
  var url = '${Env.apiBaseUrl}v2/conversations/$conversationId/chat/messages';
  var messageId = "conv_chat_${DateTime.now().millisecondsSinceEpoch}";

  await for (var line in makeStreamingApiCall(
    url: url,
    body: jsonEncode({
      'text': text,
      'conversation_id': conversationId,
    }),
  )) {
    var messageChunk = parseConversationChatChunk(line, messageId);
    if (messageChunk != null) {
      yield messageChunk;
    } else {
      yield ServerMessageChunk.failedMessage();
      return;
    }
  }
}

Future<Map<String, dynamic>?> getConversationContext(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/conversations/$conversationId/chat/context',
    headers: {},
    method: 'GET',
    body: '',
  );

  if (response == null) return null;
  if (response.statusCode == 200) {
    return jsonDecode(utf8.decode(response.bodyBytes));
  }
  debugPrint('getConversationContext error ${response.statusCode}');
  return null;
}
