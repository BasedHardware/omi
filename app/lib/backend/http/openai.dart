import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/shared.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/env/env.dart';
import 'package:tuple/tuple.dart';

class SummaryResult {
  final Structured structured;
  final List<Tuple2<Plugin, String>> pluginsResponse;

  SummaryResult(this.structured, this.pluginsResponse);
}

Future<String> triggerTestMemoryPrompt(String prompt, String transcript) async {
  return await executeGptPrompt('''
        Your are an AI with the following characteristics:
        Task: $prompt
        
        Note: It is possible that the conversation you are given, has nothing to do with your task, \
        in that case, output an empty string. (For example, you are given a business conversation, but your task is medical analysis)
        
        Conversation: ```${transcript.trim()}```,
       
        Output your response in plain text, without markdown.
        Make sure to be concise and clear.
        '''
      .replaceAll('     ', '')
      .replaceAll('    ', '')
      .trim());
}

Future<String> getPhotoDescription(Uint8List data) async {
  var messages = [
    {
      'role': 'user',
      'content': [
        {'type': "text", 'text': "What’s in this image?"},
        {
          'type': "image_url",
          'image_url': {"url": "data:image/jpeg;base64,${base64Encode(data)}"},
        },
      ],
    },
  ];
  return await gptApiCall(model: 'gpt-4o', messages: messages, maxTokens: 100);
}

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
    'Authorization': 'Bearer ${Env.openAIAPIKey}',
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
