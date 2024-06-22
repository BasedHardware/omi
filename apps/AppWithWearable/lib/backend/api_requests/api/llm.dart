import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/shared.dart';
import 'package:friend_private/backend/preferences.dart';

Future<dynamic> gptApiCall({
  required String model,
  String urlSuffix = 'chat/completions',
  List<Map<String, String>> messages = const [],
  String contentToEmbed = '',
  bool jsonResponseFormat = false,
  List tools = const [],
  File? audioFile,
  double temperature = 0.3,
}) async {
  final url = 'https://api.openai.com/v1/$urlSuffix';
  final headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Authorization': 'Bearer ${getOpenAIApiKeyForUsage()}',
  };
  final Map<String, dynamic> bodyData = {
    'model': model,
    'messages': messages,
    'temperature': temperature,
  };
  if (urlSuffix == 'embeddings') {
    bodyData['input'] = contentToEmbed;
  } else {
    bodyData['messages'] = messages;
    if (jsonResponseFormat) {
      bodyData['response_format'] = {'type': 'json_object'};
    }
    if (tools.isNotEmpty) {
      bodyData['tools'] = tools;
      bodyData['tool_choice'] = 'auto';
    }
  }

  final String body = jsonEncode(bodyData);

  var response = await makeApiCall(url: url, headers: headers, body: body, method: 'POST');
  return extractContentFromResponse(response,
      isEmbedding: urlSuffix == 'embeddings', isFunctionCalling: tools.isNotEmpty);
}

Future<String> executeGptPrompt(String? prompt, {bool jsonResponseFormat = false}) async {
  if (prompt == null) return '';

  var prefs = SharedPreferencesUtil();
  var promptBase64 = base64Encode(utf8.encode(prompt));
  var cachedResponse = prefs.gptCompletionCache(promptBase64);
  if (prefs.gptCompletionCache(promptBase64).isNotEmpty) return cachedResponse;

  String response = await gptApiCall(
      model: 'gpt-4o',
      messages: [
        {'role': 'system', 'content': prompt}
      ],
      jsonResponseFormat: jsonResponseFormat);
  prefs.setGptCompletionCache(promptBase64, response);
  debugPrint('executeGptPrompt response: $response');
  return response;
}
