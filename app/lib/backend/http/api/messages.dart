import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/string_utils.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart';

Future<List<ServerMessage>> getMessagesServer({
  String? pluginId,
  String? chatSessionId,
  bool dropdownSelected = false,
}) async {
  if (pluginId == 'no_selected') pluginId = null;
  
  var url = '${Env.apiBaseUrl}v2/messages?plugin_id=${pluginId ?? ''}&dropdown_selected=$dropdownSelected';
  if (chatSessionId != null) {
    url += '&chat_session_id=$chatSessionId';
  }
  
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

Future<List<ServerMessage>> clearChatServer({String? pluginId, String? chatSessionId}) async {
  if (pluginId == 'no_selected') pluginId = null;
  
  var url = '${Env.apiBaseUrl}v2/messages?plugin_id=${pluginId ?? ''}';
  if (chatSessionId != null) {
    url += '&chat_session_id=$chatSessionId';
  }
  
  var response = await makeApiCall(
    url: url,
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

Stream<ServerMessageChunk> sendMessageStreamServer(String text, {String? appId, String? chatSessionId, List<String>? filesId}) async* {
  var url = '${Env.apiBaseUrl}v2/messages?plugin_id=$appId';
  if (appId == null || appId.isEmpty || appId == 'null' || appId == 'no_selected') {
    url = '${Env.apiBaseUrl}v2/messages';
  }
  if (chatSessionId != null) {
    // Check if URL already has query parameters
    var separator = url.contains('?') ? '&' : '?';
    url += '${separator}chat_session_id=$chatSessionId';
  }

  try {
    final request = await HttpClient().postUrl(Uri.parse(url));
    request.headers.set('Authorization', await getAuthHeader());
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode({'text': text, 'file_ids': filesId}));

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


Future<List<ChatSession>> getChatSessions({String? appId}) async {
  if (appId == 'no_selected') appId = null;
  
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/chat-sessions?app_id=${appId ?? ''}',
    headers: {},
    method: 'GET',
    body: '',
  );
  
  if (response == null) return [];
  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    var decodedBody = jsonDecode(body) as List<dynamic>;
    return decodedBody.map((session) => ChatSession.fromJson(session)).toList();
  }
  return [];
}

Future<ChatSession?> createChatSession({String? appId, String? title}) async {
  if (appId == 'no_selected') appId = null;
  
  var url = '${Env.apiBaseUrl}v2/chat-sessions?app_id=${appId ?? ''}';
  if (title != null) {
    url += '&title=${Uri.encodeComponent(title)}';
  }
  
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: '',
  );
  
  if (response == null) return null;
  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return ChatSession.fromJson(jsonDecode(body));
  }
  return null;
}

Future<ChatSession?> getChatSessionById(String sessionId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/chat-sessions/$sessionId',
    headers: {},
    method: 'GET',
    body: '',
  );
  
  if (response == null) return null;
  if (response.statusCode == 200) {
    var body = utf8.decode(response.bodyBytes);
    return ChatSession.fromJson(jsonDecode(body));
  }
  return null;
}

Future<bool> updateChatSessionTitle(String sessionId, String title) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/chat-sessions/$sessionId/title',
    headers: {},
    method: 'PUT',
    body: jsonEncode({'title': title}),
  );
  
  return response?.statusCode == 200;
}

Future<bool> deleteChatSession(String sessionId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/chat-sessions/$sessionId',
    headers: {},
    method: 'DELETE',
    body: '',
  );
  
  return response?.statusCode == 200;
}

Future<ServerMessage?> createInitialMessage({String? appId, String? chatSessionId}) async {
  var url = '${Env.apiBaseUrl}v2/initial-message?app_id=${appId ?? ''}';
  if (chatSessionId != null) {
    url += '&chat_session_id=$chatSessionId';
  }
  
  var response = await makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: '',
  );
  
  if (response == null) return null;
  if (response.statusCode == 200) {
    return ServerMessage.fromJson(jsonDecode(response.body));
  }
  return null;
}
