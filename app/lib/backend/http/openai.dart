import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:tuple/tuple.dart';

class SummaryResult {
  final Structured structured;
  final List<Tuple2<App, String>> appsResponse;

  SummaryResult(this.structured, this.appsResponse);
}

Future<String> triggerTestConversationPrompt(String prompt, String transcript) async {
  return await executeGptPrompt('''
        Your task is: $prompt
        
        Current Conversation: ```${transcript.trim()}```,
       
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
        {
          'type': "text",
          'text':
              "What’s in this image? Describe in detail. The camera quality may be low, but do your best to accurately describe what you see anyway. The image may or may not be rotated 90 degrees. Do not comment on the image quality, damage, or distortion; only describe the content. If there is any text, please include the text content (including original language and translating to English if necessary).  If there is any media/tv/book/website/screen/etc, do your best to identify what it is and what it's about."
        },
        {
          'type': "image_url",
          'image_url': {"url": "data:image/jpeg;base64,${base64Encode(data)}"},
        },
      ],
    },
  ];
  var res = await gptApiCall(model: 'gpt-4o', messages: messages, maxTokens: 100);
  if (res == null) return '';
  return res;
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

/// Generate speech from text using OpenAI TTS API with streaming
/// Returns audio bytes in MP3 format
Future<Uint8List?> openAiTextToSpeech(String text, {String voice = 'nova', String model = 'tts-1'}) async {
  if (text.isEmpty) {
    debugPrint('[OpenAI TTS] Text is empty, skipping');
    return null;
  }

  try {
    final startTime = DateTime.now();
    debugPrint('[OpenAI TTS] ⏱️ START - Generating speech for ${text.length} characters with voice: $voice');
    
    final url = 'https://api.openai.com/v1/audio/speech';
    final headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ${Env.openAIAPIKey}',
    };
    final body = jsonEncode({
      'model': model, // 'tts-1' or 'tts-1-hd' (higher quality, slower)
      'input': text,
      'voice': voice, // alloy, echo, fable, onyx, nova, shimmer
      'response_format': 'mp3', // mp3 for better compatibility, opus for lower latency
    });

    final apiCallStart = DateTime.now();
    final client = http.Client();
    
    // Use send() instead of post() to get streamed response
    final request = http.Request('POST', Uri.parse(url));
    request.headers.addAll(headers);
    request.body = body;
    
    final streamedResponse = await client.send(request).timeout(const Duration(seconds: 30));
    
    if (streamedResponse.statusCode != 200) {
      final errorBody = await streamedResponse.stream.bytesToString();
      debugPrint('[OpenAI TTS] ❌ Error ${streamedResponse.statusCode}: $errorBody');
      return null;
    }

    // Collect audio bytes as they stream in
    final audioBytes = <int>[];
    var firstChunkReceived = false;
    
    await for (var chunk in streamedResponse.stream) {
      if (!firstChunkReceived) {
        final firstChunkTime = DateTime.now().difference(apiCallStart).inMilliseconds;
        debugPrint('[OpenAI TTS] ⏱️ First audio chunk received in ${firstChunkTime}ms (TTFB)');
        firstChunkReceived = true;
      }
      audioBytes.addAll(chunk);
    }
    
    final apiCallDuration = DateTime.now().difference(apiCallStart).inMilliseconds;
    final totalDuration = DateTime.now().difference(startTime).inMilliseconds;
    
    debugPrint('[OpenAI TTS] ⏱️ Full download took ${apiCallDuration}ms');
    debugPrint('[OpenAI TTS] ✅ Received ${audioBytes.length} bytes in ${totalDuration}ms total');
    
    return Uint8List.fromList(audioBytes);
  } catch (e) {
    debugPrint('[OpenAI TTS] ❌ Exception: $e');
    return null;
  }
}
