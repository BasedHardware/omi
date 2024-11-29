import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:path/path.dart';

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
  var response = await makeApiCall(url: '${Env.apiBaseUrl}v1/messages', headers: {}, method: 'DELETE', body: '');
  if (response == null) throw Exception('Failed to delete chat');
  if (response.statusCode == 200) {
    return [ServerMessage.fromJson(jsonDecode(response.body))];
  } else {
    throw Exception('Failed to delete chat');
  }
}

Future<ServerMessage> sendMessageServer(String text, {String? appId}) {
  return makeApiCall(
    url: '${Env.apiBaseUrl}v1/messages?plugin_id=$appId',
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
