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

Uri _buildApiUri(String path, {Map<String, dynamic>? query}) {
  final base = Env.apiBaseUrl!;
  final baseUri = Uri.parse(base);
  return baseUri.replace(
    path: '${baseUri.path.endsWith('/') ? baseUri.path.substring(0, baseUri.path.length - 1) : baseUri.path}$path',
    queryParameters: query?.map((k, v) => MapEntry(k, v?.toString())),
  );
}

Future<List<ServerMessage>> getMessagesServer({
  String? appId,
  bool dropdownSelected = false,
  String? chatSessionId,
}) async {
  final uri = _buildApiUri('/v2/messages', query: {
    'app_id': appId, // Send actual app_id ('omi' for OMI, actual ID for others)
    'dropdown_selected': dropdownSelected,
    if (chatSessionId != null) 'chat_session_id': chatSessionId,
  });
  var response = await makeApiCall(url: uri.toString(), headers: {}, method: 'GET', body: '');
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

Future<Map<String, dynamic>?> clearChatServer({String? appId, String? chatSessionId}) async {
  final uri = _buildApiUri('/v2/messages', query: {
    'app_id': appId, // Send actual app_id ('omi' for OMI, actual ID for others)
    if (chatSessionId != null) 'chat_session_id': chatSessionId,
  });
  var response = await makeApiCall(url: uri.toString(), headers: {}, method: 'DELETE', body: '');
  if (response == null) return null;

  if (response.statusCode == 200) {
    final body = utf8.decode(response.bodyBytes);
    final result = jsonDecode(body) as Map<String, dynamic>;

    // Handle new structured response format
    if (result['status'] == 'success') {
      debugPrint('Chat cleared successfully for app: ${result['cleared']?['app_id']}');
      debugPrint('Session: ${result['cleared']?['chat_session_id']}');
      debugPrint('Timestamp: ${result['cleared']?['timestamp']}');
      return result;
    } else {
      debugPrint('Clear chat failed: ${result['message'] ?? 'Unknown error'}');
      return null;
    }
  } else {
    debugPrint('Clear chat HTTP error: ${response.statusCode} ${response.body}');
    return null;
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
    {String? appId, String? chatSessionId, List<String>? filesId}) async* {
  final uri = _buildApiUri('/v2/messages', query: {
    if (appId != null && appId.isNotEmpty && appId != 'null' && appId != 'no_selected') 'app_id': appId,
    if (chatSessionId != null && chatSessionId.isNotEmpty) 'chat_session_id': chatSessionId,
  });

  try {
    final request = await HttpClient().postUrl(uri);
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

Future<ServerMessage> getInitialAppMessage(String? appId, {String? chatSessionId}) {
  return makeApiCall(
    url: _buildApiUri('/v2/initial-message', query: {
      if (appId != null) 'app_id': appId,
      if (chatSessionId != null) 'chat_session_id': chatSessionId,
    }).toString(),
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

Stream<ServerMessageChunk> sendVoiceMessageStreamServer(List<File> files,
    {String? appId, String? chatSessionId}) async* {
  final uri = _buildApiUri('/v2/voice-messages', query: {
    if (appId != null && appId.isNotEmpty && appId != 'null' && appId != 'no_selected') 'app_id': appId,
    if (chatSessionId != null && chatSessionId.isNotEmpty) 'chat_session_id': chatSessionId,
  });
  var request = http.MultipartRequest(
    'POST',
    uri,
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

Future<List<MessageFile>?> uploadFilesServer(List<File> files, {String? appId, String? chatSessionId}) async {
  final uri = _buildApiUri('/v2/files', query: {
    if (appId != null && appId.isNotEmpty && appId != 'null' && appId != 'no_selected') 'app_id': appId,
    if (chatSessionId != null && chatSessionId.isNotEmpty) 'chat_session_id': chatSessionId,
  });
  var request = http.MultipartRequest(
    'POST',
    uri,
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
