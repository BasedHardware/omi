import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/shared.dart';
import 'package:friend_private/backend/preferences.dart';

Future<dynamic> gptApiCall({
  required String model,
  String urlSuffix = 'chat/completions',
  List<Map<String, dynamic>> messages = const [],
  String contentToEmbed = '',
  bool jsonResponseFormat = false,
  List tools = const [],
  File? audioFile,
  double temperature = 0.3,
  int? maxTokens,
}) async {
  final url = 'https://api.openai.com/v1/$urlSuffix';
  final headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Authorization': 'Bearer ${getOpenAIApiKeyForUsage()}',
  };
  final String body;
  if (urlSuffix == 'embeddings') {
    body = jsonEncode({'model': model, 'input': contentToEmbed});
  } else {
    var bodyData = {'model': model, 'messages': messages, 'temperature': temperature};
    if (jsonResponseFormat) {
      bodyData['response_format'] = {'type': 'json_object'};
    } else if (tools.isNotEmpty) {
      bodyData['tools'] = tools;
      bodyData['tool_choice'] = 'auto';
    }
    if (maxTokens != null) {
      bodyData['max_tokens'] = maxTokens;
    }
    body = jsonEncode(bodyData);
  }

  var response = await makeApiCall(url: url, headers: headers, body: body, method: 'POST');
  return extractContentFromResponse(
    response,
    isEmbedding: urlSuffix == 'embeddings',
    isFunctionCalling: tools.isNotEmpty,
  );
}

Future<String> executeGptPrompt(String? prompt, {bool ignoreCache = false}) async {
  if (prompt == null) return '';

  var prefs = SharedPreferencesUtil();
  var promptBase64 = base64Encode(utf8.encode(prompt));
  var cachedResponse = prefs.gptCompletionCache(promptBase64);
  if (!ignoreCache && prefs.gptCompletionCache(promptBase64).isNotEmpty) return cachedResponse;

  String response = await gptApiCall(model: 'gpt-4o', messages: [
    {'role': 'system', 'content': prompt}
  ]);
  prefs.setGptCompletionCache(promptBase64, response);
  debugPrint('executeGptPrompt response: $response');
  return response;
}
