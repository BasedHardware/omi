import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/string_utils.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart';

String _buildMessagesUrl({
  String? appId,
  String? chatSessionId,
  bool? dropdownSelected,
}) {
  final hasSession = chatSessionId != null && chatSessionId != 'no_selected';
  final hasAppId = appId != null && appId != 'no_selected';
  final hasDropdownSelected = dropdownSelected != null;
  final params = <String, String>{
    if (hasSession) 'chat_session_id': chatSessionId,
    if (hasAppId) 'app_id': appId,
    if (hasDropdownSelected) 'dropdown_selected': '$dropdownSelected',
  };
  return Uri.parse('${Env.apiBaseUrl}v2/messages').replace(queryParameters: params).toString();
}

Future<List<ServerMessage>> getMessagesServer({
  String? chatSessionId,
  bool dropdownSelected = false,
}) async {
  // TODO: Add pagination
  final url = _buildMessagesUrl(
    appId: null,
    chatSessionId: chatSessionId,
    dropdownSelected: dropdownSelected,
  );
  var response = await makeApiCall(
    url: url,
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
    return messages;
  }
  return [];
}

Future<void> clearChatServer({String? chatSessionId}) async {
  final url = _buildMessagesUrl(appId: null, chatSessionId: chatSessionId);
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null) throw Exception('Failed to delete chat');
  if (response.statusCode != 204) {
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

Stream<ServerMessageChunk> sendMessageStreamServer(String text,
    {String? appId, String? chatSessionId, List<String>? filesId, Map<String, dynamic>? context}) async* {
  final url = _buildMessagesUrl(appId: appId, chatSessionId: chatSessionId);

  try {
    final request = await HttpClient().postUrl(Uri.parse(url));
    request.headers.set('Authorization', await getAuthHeader());
    request.headers.contentType = ContentType.json;
    final Map<String, dynamic> body = {
      'text': text,
      'file_ids': filesId,
      'context': context ?? {},
    };
    request.write(jsonEncode(body));

    final response = await request.close();

    if (response.statusCode != 200) {
      Logger.error('Failed to send message: ${response.statusCode}');
      yield ServerMessageChunk.failedMessage();
      return;
    }

    var buffers = <String>[];
    var messageId = "1000"; // Default new message
    await for (var data in response.transform(utf8.decoder)) {
      var lines = data.split('\n\n');
      for (var line in lines.where((line) => line.isNotEmpty)) {
        // Dealing w/ the package spliting by 1024 bytes in dart
        // Waiting for the next package
        if (line.length >= 1024) {
          buffers.add(line);
          continue;
        }

        // Merge package if needed
        if (buffers.isNotEmpty) {
          buffers.add(line);
          line = buffers.join();
          buffers.clear();
        }

        var messageChunk = parseMessageChunk(line, messageId);
        if (messageChunk != null) {
          yield messageChunk;
        }
      }
    }

    // Flush remainings
    if (buffers.isNotEmpty) {
      var messageChunk = parseMessageChunk(buffers.join(), messageId);
      if (messageChunk != null) {
        yield messageChunk;
      }
    }
  } catch (e) {
    Logger.error('Error sending message: $e');
    yield ServerMessageChunk.failedMessage();
  }
}

// ---------------- Chat sessions API (multi-session) ----------------

Future<Map<String, dynamic>> createChatSessionServer({String? appId, List<String>? pinnedConversationIds}) async {
  final url = '${Env.apiBaseUrl}v2/chat-sessions?app_id=$appId';
  final Map<String, dynamic> bodyMap = {};
  final response = await makeApiCall(
    url: url,
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode(bodyMap),
  );
  if (response == null || response.statusCode != 200) {
    throw Exception('Failed to create chat session');
  }
  return jsonDecode(utf8.decode(response.bodyBytes));
}

Future<List<Map<String, dynamic>>> listChatSessionsServer({int limit = 20}) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/chat-sessions?limit=$limit',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) {
    throw Exception('Failed to list chat sessions');
  }
  final body = jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>;
  return body.cast<Map<String, dynamic>>();
}

Future<Map<String, dynamic>> getChatSessionServer(String chatSessionId) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/chat-sessions/$chatSessionId',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null || response.statusCode != 200) {
    throw Exception('Failed to get chat session');
  }
  return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
}

Future<void> deleteChatSessionServer(String chatSessionId) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/chat-sessions/$chatSessionId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  if (response == null || response.statusCode != 200) {
    throw Exception('Failed to delete chat session');
  }
}

Stream<ServerMessageChunk> sendVoiceMessageStreamServer(List<File> files) async* {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}v2/voice-messages'),
  );
  for (var file in files) {
    request.files.add(await http.MultipartFile.fromPath('files', file.path, filename: basename(file.path)));
  }
  request.headers.addAll({'Authorization': await getAuthHeader()});

  try {
    var response = await request.send();
    if (response.statusCode != 200) {
      Logger.error('Failed to send message: ${response.statusCode}');
      yield ServerMessageChunk.failedMessage();
      return;
    }

    var buffers = <String>[];
    var messageId = "1000"; // Default new message
    await for (var data in response.stream.transform(utf8.decoder)) {
      var lines = data.split('\n\n');
      for (var line in lines.where((line) => line.isNotEmpty)) {
        // Dealing w/ the package spliting by 1024 bytes in dart
        // Waiting for the next package
        if (line.length >= 1024) {
          buffers.add(line);
          continue;
        }

        // Merge package if needed
        if (buffers.isNotEmpty) {
          buffers.add(line);
          line = buffers.join();
          buffers.clear();
        }

        var messageChunk = parseMessageChunk(line, messageId);
        if (messageChunk != null) {
          yield messageChunk;
        }
      }
    }

    // Flush remainings
    if (buffers.isNotEmpty) {
      var messageChunk = parseMessageChunk(buffers.join(), messageId);
      if (messageChunk != null) {
        yield messageChunk;
      }
    }
  } catch (e) {
    Logger.error('Error sending message: $e');
    yield ServerMessageChunk.failedMessage();
  }
}

Future<List<MessageFile>?> uploadFilesServer(List<File> files, {String? appId}) async {
  var url = '${Env.apiBaseUrl}v2/files?app_id=$appId';
  if (appId == null || appId.isEmpty || appId == 'null' || appId == 'no_selected') {
    url = '${Env.apiBaseUrl}v2/files';
  }
  var request = http.MultipartRequest(
    'POST',
    Uri.parse(url),
  );
  request.headers.addAll({'Authorization': await getAuthHeader()});
  for (var file in files) {
    var stream = http.ByteStream(file.openRead());
    var length = await file.length();
    var multipartFile = http.MultipartFile(
      'files',
      stream,
      length,
      filename: basename(file.path),
    );
    request.files.add(multipartFile);
  }

  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);
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
    var request = http.MultipartRequest(
      'POST',
      Uri.parse('${Env.apiBaseUrl}v2/voice-message/transcribe'),
    );

    request.headers.addAll({'Authorization': await getAuthHeader()});
    request.files.add(await http.MultipartFile.fromPath('files', audioFile.path));

    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

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
