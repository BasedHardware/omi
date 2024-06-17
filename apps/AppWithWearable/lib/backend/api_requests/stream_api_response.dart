import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/utils/temp.dart';
import 'package:flutter/material.dart';
import './streaming_models.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;

Future streamApiResponse(
  dynamic personality,
  String context,
  Future<dynamic> Function(String) callback,
  List<Message> chatHistory,
  VoidCallback onDone,
) async {
  var client = http.Client();
  const url = 'https://api.openai.com/v1/chat/completions';
  // final apiKey = '123';
  final headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ${getOpenAIApiKeyForUsage()}',
  };

  String body = qaStreamedBody(personality, context, retrieveMostRecentMessages(chatHistory));
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
            print('Partial message in queue: $bufferString');
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

String qaStreamedBody(dynamic personality, String context, List<Message> chatHistory) {

  var personalityPrompt = '';
  if (personality is String) {
    personalityPrompt = personality.isNotEmpty ? 'This is your personality, you should try to answer in this style: $personality\n' : '';
  } else if (personality is List<String>) {
    if (personality.isNotEmpty) {
      personalityPrompt = 'These are your available personalities, pick the style among them that fits best to the ongoing conversation:\n${personality.map((p) => '- $p').join('\n')}\n';
    }
  }
  var prompt = '''
    $personalityPrompt
    You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. 
    If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.
    If the message doesn't require context, it will be empty, so answer the question casually.
    
    Conversation History:
    ${chatHistory.map((e) => '${e.type.toString().toUpperCase()}: ${e.text}').join('\n')}

    Context:
    ```
    $context
    ```
    Answer:
    '''
      .replaceAll('    ', '');
  debugPrint(prompt);
  var body = jsonEncode({
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": prompt}
    ],
    "stream": true,
  });
  return body;
}
