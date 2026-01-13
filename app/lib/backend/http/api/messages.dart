import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/string_utils.dart';

Future<List<ServerMessage>> getMessagesServer({
  String? appId,
  bool dropdownSelected = false,
}) async {
  if (appId == 'no_selected') appId = null;
  // TODO: Add pagination
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/messages?app_id=${appId ?? ''}&dropdown_selected=$dropdownSelected',
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
    var messages = decodedBody.map((conversation) => ServerMessage.fromJson(conversation)).toList();
    debugPrint('getMessages length: ${messages.length}');
    // Debug: Check if any messages have ratings
    var ratedMessages = messages.where((m) => m.rating != null).toList();
    if (ratedMessages.isNotEmpty) {
      debugPrint('📊 Messages with ratings: ${ratedMessages.length}');
      for (var m in ratedMessages) {
        debugPrint('  - Message ${m.id}: rating=${m.rating}');
      }
    }
    return messages;
  }
  return [];
}

Future<List<ServerMessage>> clearChatServer({String? appId}) async {
  if (appId == 'no_selected') appId = null;
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/messages?app_id=${appId ?? ''}',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) throw Exception('Failed to delete chat');
  if (response.statusCode == 200) {
    return [ServerMessage.fromJson(jsonDecode(response.body))];
  } else {
    throw Exception('Failed to delete chat');
  }
}

ServerMessageChunk? parseMessageChunk(String line, String messageId) {
  if (line.startsWith('think: ')) {
    return ServerMessageChunk(messageId, line.substring(7).replaceAll("__CRLF__", "\n"), MessageChunkType.think);
  }

  if (line.startsWith('data: ')) {
    return ServerMessageChunk(messageId, line.substring(6).replaceAll("__CRLF__", "\n"), MessageChunkType.data);
  }

  if (line.startsWith('done: ')) {
    var text = decodeBase64(line.substring(6));
    return ServerMessageChunk(messageId, text, MessageChunkType.done,
        message: ServerMessage.fromJson(json.decode(text)));
  }

  if (line.startsWith('message: ')) {
    var text = decodeBase64(line.substring(9));
    return ServerMessageChunk(messageId, text, MessageChunkType.message,
        message: ServerMessage.fromJson(json.decode(text)));
  }

  return null;
}

Stream<ServerMessageChunk> sendMessageStreamServer(String text, {String? appId, List<String>? filesId}) async* {
  var url = '${Env.apiBaseUrl}v2/messages?app_id=$appId';
  if (appId == null || appId.isEmpty || appId == 'null' || appId == 'no_selected') {
    url = '${Env.apiBaseUrl}v2/messages';
  }

  var messageId = "1000"; // Default new message

  await for (var line in makeStreamingApiCall(
    url: url,
    body: jsonEncode({'text': text, 'file_ids': filesId}),
  )) {
    var messageChunk = parseMessageChunk(line, messageId);
    if (messageChunk != null) {
      yield messageChunk;
    } else {
      yield ServerMessageChunk.failedMessage();
      return;
    }
  }
}

Future<ServerMessage> getInitialAppMessage(String? appId) {
  return makeApiCall(
    url: '${Env.apiBaseUrl}v2/initial-message?app_id=$appId',
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

Stream<ServerMessageChunk> sendVoiceMessageStreamServer(List<File> files) async* {
  var messageId = "1000"; // Default new message

  await for (var line in makeMultipartStreamingApiCall(
    url: '${Env.apiBaseUrl}v2/voice-messages',
    files: files,
  )) {
    var messageChunk = parseMessageChunk(line, messageId);
    if (messageChunk != null) {
      yield messageChunk;
    } else {
      yield ServerMessageChunk.failedMessage();
      return;
    }
  }
}

Future<List<MessageFile>?> uploadFilesServer(List<File> files, {String? appId}) async {
  var url = '${Env.apiBaseUrl}v2/files?app_id=$appId';
  if (appId == null || appId.isEmpty || appId == 'null' || appId == 'no_selected') {
    url = '${Env.apiBaseUrl}v2/files';
  }

  try {
    var response = await makeMultipartApiCall(
      url: url,
      files: files,
    );

    if (response.statusCode == 200) {
      debugPrint('uploadFileServer response body: ${jsonDecode(response.body)}');
      return MessageFile.fromJsonList(jsonDecode(response.body));
    } else {
      debugPrint('Failed to upload file. Status code: ${response.statusCode} ${response.body}');
      throw Exception('Failed to upload file. Status code: ${response.statusCode}');
    }
  } catch (e) {
    debugPrint('An error occurred uploadFileServer: $e');
    throw Exception('An error occurred uploadFileServer: $e');
  }
}

Future reportMessageServer(String messageId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/messages/$messageId/report',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) throw Exception('Failed to report message');
  if (response.statusCode != 200) {
    throw Exception('Failed to report message');
  }
}

Future<String> transcribeVoiceMessage(File audioFile) async {
  try {
    var response = await makeMultipartApiCall(
      url: '${Env.apiBaseUrl}v2/voice-message/transcribe',
      files: [audioFile],
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      return data['transcript'] ?? '';
    } else {
      debugPrint('Failed to transcribe voice message: ${response.statusCode} ${response.body}');
      throw Exception('Failed to transcribe voice message');
    }
  } catch (e) {
    debugPrint('Error transcribing voice message: $e');
    throw Exception('Error transcribing voice message: $e');
  }
}
