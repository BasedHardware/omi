import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/chat_session.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/utils/other/string_utils.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:path/path.dart';

Future<List<ServerMessage>> getMessagesServer({
  String? pluginId,
  bool dropdownSelected = false,
}) async {
  if (pluginId == 'no_selected') pluginId = null;
  // TODO: Add pagination
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/messages?plugin_id=${pluginId ?? ''}&dropdown_selected=$dropdownSelected',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  debugPrint('getMessages: ${response.body}');
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

Future<List<ServerMessage>> clearChatServer({String? pluginId}) async {
  if (pluginId == 'no_selected') pluginId = null;
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/messages?plugin_id=${pluginId ?? ''}',
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

Future<ServerMessage> sendMessageServer(String text, {String? appId}) {
  var url = '${Env.apiBaseUrl}v1/messages?plugin_id=$appId';
  if (appId == null || appId.isEmpty || appId == 'null' || appId == 'no_selected') {
    url = '${Env.apiBaseUrl}v1/messages';
  }
  return makeApiCall(
    url: url,
    headers: {},
    method: 'POST',
    body: jsonEncode({'text': text}),
  ).then((response) {
    if (response == null) throw Exception('Failed to send message');
    if (response.statusCode == 200) {
      return ServerMessage.fromJson(jsonDecode(response.body));
    } else {
      Logger.error('Failed to send message ${response.body}');
      CrashReporting.reportHandledCrash(
        Exception('Failed to send message ${response.body}'),
        StackTrace.current,
        level: NonFatalExceptionLevel.error,
      );
      return ServerMessage.failedMessage();
    }
  });
}

ServerMessageChunk? parseMessageChunk(String line, String messageId) {
  try {
    final jsonData = json.decode(line);
    if (jsonData is Map<String, dynamic>) {
      return ServerMessageChunk(
        messageId,
        jsonData['text'] ?? '',
        MessageChunkType.done,
        message: ServerMessage.fromJson(jsonData),
      );
    }
  } catch (_) {
    if (line.startsWith('think: ')) {
      return ServerMessageChunk(
        messageId, 
        line.substring(7).replaceAll("__CRLF__", "\n"), 
        MessageChunkType.think
      );
    }

    if (line.startsWith('data: ')) {
      return ServerMessageChunk(
        messageId, 
        line.substring(6).replaceAll("__CRLF__", "\n"), 
        MessageChunkType.data
      );
    }

    if (line.startsWith('done: ')) {
      var text = decodeBase64(line.substring(6));
      return ServerMessageChunk(
        messageId, 
        text, 
        MessageChunkType.done,
        message: ServerMessage.fromJson(json.decode(text))
      );
    }

    if (line.startsWith('message: ')) {
      var text = decodeBase64(line.substring(9));
      return ServerMessageChunk(
        messageId, 
        text, 
        MessageChunkType.message,
        message: ServerMessage.fromJson(json.decode(text))
      );
    }
  }

  return null;
}

Stream<ServerMessageChunk> sendMessageStreamServer(String text, {String? appId, String? sessionId}) async* {
  debugPrint('sendMessageStreamServer started');
  debugPrint('Text: $text, AppId: $appId, SessionId: $sessionId');

  var url = sessionId != null 
    ? '${Env.apiBaseUrl}v1/sessions/$sessionId/messages'  // Use sessions endpoint if sessionId exists
    : '${Env.apiBaseUrl}v1/messages';  // Fall back to old endpoint

  if (appId != null && appId.isNotEmpty && appId != 'null' && appId != 'no_selected') {
    url += '?plugin_id=$appId';
  }

  try {
    final request = await HttpClient().postUrl(Uri.parse(url));
    request.headers.set('Authorization', await getAuthHeader());
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode({'text': text}));

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
    url: '${Env.apiBaseUrl}v1/initial-message?plugin_id=$appId',
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

Future<List<ServerMessage>> sendVoiceMessageServer(List<File> files) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.apiBaseUrl}v1/voice-messages'),
  );
  for (var file in files) {
    request.files.add(await http.MultipartFile.fromPath('files', file.path, filename: basename(file.path)));
  }
  request.headers.addAll({'Authorization': await getAuthHeader()});

  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode == 200) {
      debugPrint('sendVoiceMessageServer response body: ${jsonDecode(response.body)}');
      return ((jsonDecode(response.body) ?? []) as List<dynamic>).map((m) => ServerMessage.fromJson(m)).toList();
    } else {
      debugPrint('Failed to upload sample. Status code: ${response.statusCode} ${response.body}');
      throw Exception('Failed to upload sample. Status code: ${response.statusCode}');
    }
  } catch (e) {
    debugPrint('An error occurred uploadSample: $e');
    throw Exception('An error occurred uploadSample: $e');
  }
}

Future reportMessageServer(String messageId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/messages/$messageId/report',
    headers: {},
    method: 'POST',
    body: '',
  );
  if (response == null) throw Exception('Failed to report message');
  if (response.statusCode != 200) {
    throw Exception('Failed to report message');
  }
}

Future<List<ChatSession>> getChatSessionsServer({
  String? pluginId,
  int limit = 20,
  String? offset,
}) async {
  try {
    var queryParams = {
      if (pluginId != null) 'plugin_id': pluginId,
      'limit': limit.toString(),
      if (offset != null) 'offset': offset,
    };

    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sessions',
      headers: {},
      method: 'GET',
      queryParams: queryParams,
    );


    if (response == null) return [];
    
    if (response.statusCode == 200) {
      var decodedBody = jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>;
      var sessions = decodedBody.map((session) {
        debugPrint('Processing session: $session');
        try {
          return ChatSession.fromJson(session);
        } catch (e) {
          debugPrint('Error parsing session: $e');
          return null;
        }
      })
      .whereType<ChatSession>() // Filter out nulls
      .toList();
      
      debugPrint('Parsed sessions: $sessions');
      return sessions;
    }
    return [];
  } catch (e) {
    Logger.error('Error getting chat sessions: $e');
    return [];
  }
}

Future<ChatSession?> createChatSessionServer({String? pluginId}) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sessions',
      headers: {},
      method: 'POST',
      queryParams: pluginId != null ? {'plugin_id': pluginId} : null,
    );

    if (response == null) return null;

    if (response.statusCode == 200) {
      return ChatSession.fromJson(jsonDecode(response.body));
    }
    return null;
  } catch (e) {
    Logger.error('Error creating chat session: $e');
    return null;
  }
}

Future<bool> deleteChatSessionServer(String sessionId) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sessions/$sessionId',
      headers: {},
      method: 'DELETE',
    );

    return response?.statusCode == 200;
  } catch (e) {
    Logger.error('Error deleting chat session: $e');
    return false;
  }
}

Future<ChatSession?> updateChatSessionServer(
  String sessionId, 
  Map<String, dynamic> updates
) async {
  try {
    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sessions/$sessionId',
      headers: {},
      method: 'PATCH',
      body: jsonEncode(updates),
    );

    if (response == null) return null;

    if (response.statusCode == 200) {
      return ChatSession.fromJson(jsonDecode(response.body));
    }
    return null;
  } catch (e) {
    Logger.error('Error updating chat session: $e');
    return null;
  }
}

Future<List<ServerMessage>> getSessionMessagesServer(
  String sessionId, {
  DateTime? before,
}) async {
  try {
    var queryParams = {
      if (before != null) 'before': before.toIso8601String(),
    };

    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sessions/$sessionId/messages',
      headers: {},
      method: 'GET',
      queryParams: queryParams,
    );

    if (response == null) return [];

    if (response.statusCode == 200) {
      var decodedBody = jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>;
      return decodedBody.map((msg) => ServerMessage.fromJson(msg)).toList();
    }
    return [];
  } catch (e) {
    Logger.error('Error getting session messages: $e');
    return [];
  }
}

Future<ServerMessage?> sendSessionMessageServer(
  String sessionId,
  String text, {
  String? pluginId,
}) async {
  try {
    var queryParams = {
      if (pluginId != null) 'plugin_id': pluginId,
    };

    var response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/sessions/$sessionId/messages',
      headers: {},
      method: 'POST',
      queryParams: queryParams,
      body: jsonEncode({'text': text}),
    );

    if (response == null) return null;

    if (response.statusCode == 200) {
      return ServerMessage.fromJson(jsonDecode(response.body));
    }
    return null;
  } catch (e) {
    Logger.error('Error sending session message: $e');
    return null;
  }
}