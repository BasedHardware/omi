import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:http/http.dart' as http;

import './streaming_models.dart';

Future streamApiResponse(
  String prompt,
  Future<dynamic> Function(String) callback,
  VoidCallback onDone,
) async {
  var client = http.Client();
  const url = 'https://api.openai.com/v1/chat/completions';
  final headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ${getOpenAIApiKeyForUsage()}'};

  var body = jsonEncode({
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": prompt}
    ],
    "stream": true,
  });
  var request = http.Request("POST", Uri.parse(url))
    ..headers.addAll(headers)
    ..body = body;

  try {
    final http.StreamedResponse response = await client.send(request);
    if (response.statusCode == 401) {
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
    _listStream(response, callback, onDone);
  } catch (e) {
    debugPrint('Error sending request: $e');
  }
}

_listStream(response, callback, onDone) {
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
            // print('Partial message in queue: $bufferString');
          }
        }
      },
      onError: (error) => debugPrint('Stream error: $error'),
      onDone: () {
        debugPrint('Stream completed');
        onDone();
      });
}

bool isValidJson(String jsonString) {
  try {
    json.decode(jsonString);
    return true;
  } catch (e) {
    return false;
  }
}

String? jsonEncodeString(String? regularString) {
  if (regularString == null) return null;
  if (regularString.isEmpty | (regularString.length == 1)) return regularString;

  String encodedString = jsonEncode(regularString);
  return encodedString.substring(1, encodedString.length - 1);
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
