import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/custom_functions.dart';
import 'package:flutter/material.dart';
import './streaming_models.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;

initAssistantResponse() {
  FFAppState().update(() {
    FFAppState().chatHistory = saveChatHistory(FFAppState().chatHistory, convertToJSONRole("", "assistant"));
  });
}

Future streamApiResponse(
  String context,
  Future<dynamic> Function(String) callback,
) async {
  var client = http.Client();
  const url = 'https://api.openai.com/v1/chat/completions';
  // final apiKey = '123';
  final headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ${getOpenAIApiKeyForUsage()}',
  };

  String body = qaStreamedBody(context, retrieveMostRecentMessages(FFAppState().chatHistory));
  // String body = qaStreamedFullMemories(FFAppState().memories, retrieveMostRecentMessages(FFAppState().chatHistory));
  var request = http.Request("POST", Uri.parse(url))
    ..headers.addAll(headers)
    ..body = body;

  initAssistantResponse();
  try {
    final http.StreamedResponse response = await client.send(request);
    if (response.statusCode == 401) {
      // TODO: callback for only errors, so that the message is not stored as history
      debugPrint('Unauthorized request');
      callback('Incorrect OpenAI API Key provided.');
      return;
    } else if (response.statusCode == 429) {
      callback('You have reached the Open AI API limit.');
      return;
    } else if (response.statusCode != 200) {
      callback('Unknown Error with OpenAI.');
      return;
    }
    debugPrint('Stream response: ${response.statusCode}');
    _listStream(response, callback);
  } catch (e) {
    debugPrint('Error sending request: $e');
  }
}

_listStream(response, callback) {
  StringBuffer buffer = StringBuffer();
  response.stream.listen(
    (List<int> value) async {
      buffer.write(utf8.decode(value));
      String bufferString = buffer.toString();

      // Check for a complete message (or more than one)
      if (bufferString.contains("data:")) {
        // Split the buffer by 'data:' delimiter
        var jsonBlocks = bufferString.split('data:').where((block) => block.isNotEmpty).toList();

        int processedBlocks = 0;
        for (var jsonBlock in jsonBlocks) {
          if (isValidJson(jsonBlock)) {
            handlePartialResponseContent(jsonBlock, callback);
            processedBlocks++;
          } else {
            bufferString = 'data: $jsonBlock';
          }
        }
        buffer.clear();
        if (processedBlocks < jsonBlocks.length) {
          //we have a partial message
          buffer.write(bufferString);
          print('Partial message in queue: $bufferString');
        }
      }
    },
    onError: (error) => debugPrint('Stream error: $error'),
    onDone: () => debugPrint('Stream completed'),
  );
}

bool isValidJson(String jsonString) {
  try {
    json.decode(jsonString);
    return true;
  } catch (e) {
    return false;
  }
}

void handlePartialResponseContent(String data, Future<dynamic> Function(String) callback) {
  if (data.contains("content")) {
    ContentResponse contentResponse = ContentResponse.fromJson(jsonDecode(data));
    if (contentResponse.choices != null &&
        contentResponse.choices![0].delta != null &&
        contentResponse.choices![0].delta!.content != null) {
      String content = jsonEncodeString(contentResponse.choices![0].delta!.content!)!;
      callback(content);
    }
  }
}
