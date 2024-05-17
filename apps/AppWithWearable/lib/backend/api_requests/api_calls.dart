import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/utils.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;

Future<http.Response?> makeApiCall({
  required String url,
  required Map<String, String> headers,
  required String body,
  required String method,
}) async {
  final transaction = Sentry.startTransaction(
    'webrequest',
    'request',
    bindToScope: true,
  );
  var response;
  var client = SentryHttpClient();

  try {
    if (method == 'POST') {
      response = await client.post(Uri.parse(url), headers: headers, body: body);
    } else if (method == 'GET') {
      response = await client.get(Uri.parse(url), headers: headers);
    }
  } catch (e) {
    debugPrint('HTTP request failed: $e');
    await transaction.finish(status: const SpanStatus.unknownError());
    return null;
  } finally {
    client.close();
  }
  await transaction.finish(status: const SpanStatus.ok());
  return response;
}

// Function to extract content from the API response.
dynamic extractContentFromResponse(http.Response? response,
    {bool isEmbedding = false, bool isFunctionCalling = false}) {
  if (response != null && response.statusCode == 200) {
    var data = jsonDecode(response.body);
    if (isEmbedding) {
      var embedding = data['data'][0]['embedding'];
      return embedding;
    }
    var message = data['choices'][0]['message'];
    if (isFunctionCalling && message['tool_calls'] != null) {
      debugPrint('message $message');
      debugPrint('message ${message['tool_calls'].runtimeType}');
      return message['tool_calls'];
    }
    return data['choices'][0]['message']['content'];
  } else {
    debugPrint('Error fetching data: ${response?.statusCode}');
    throw Exception('Error fetching data: ${response?.statusCode}');
    // return {'error': response?.statusCode};
  }
}

// A general call function for the GPT API.
Future<dynamic> gptApiCall({
  required String model,
  String urlSuffix = 'chat/completions',
  List<Map<String, String>> messages = const [],
  String contentToEmbed = '',
  bool jsonResponseFormat = false,
  List tools = const [],
  File? audioFile,
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
    var bodyData = {'model': model, 'messages': messages};
    if (jsonResponseFormat) {
      bodyData['response_format'] = {'type': 'json_object'};
    } else if (tools.isNotEmpty) {
      bodyData['tools'] = tools;
      bodyData['tool_choice'] = 'auto';
    }
    body = jsonEncode(bodyData);
  }

  var response = await makeApiCall(url: url, headers: headers, body: body, method: 'POST');
  return extractContentFromResponse(response,
      isEmbedding: urlSuffix == 'embeddings', isFunctionCalling: tools.isNotEmpty);
}

Future<String> executeGptPrompt(String? prompt) async {
  if (prompt == null) return '';

  var prefs = SharedPreferencesUtil();
  var promptBase64 = base64Encode(utf8.encode(prompt));
  var cachedResponse = prefs.gptCompletionCache(promptBase64);
  if (prefs.gptCompletionCache(promptBase64).isNotEmpty) return cachedResponse;

  String response = await gptApiCall(model: 'gpt-4o', messages: [
    {'role': 'system', 'content': prompt}
  ]);
  prefs.setGptCompletionCache(promptBase64, response);
  debugPrint('executeGptPrompt response: $response');
  return response;
}

Future<String> generateTitleAndSummaryForMemory(String rawMemory, List<MemoryRecord> previousMemories) async {
  final languageCode = SharedPreferencesUtil().recordingsLanguage;
  final language = availableLanguagesByCode[languageCode] ?? 'English';

  var prevMemoriesStr = '';
  // seconds or minutes ago
  for (var value in previousMemories) {
    var timePassed = DateTime.now().difference(value.date).inMinutes < 1
        ? '${DateTime.now().difference(value.date).inSeconds} seconds ago'
        : '${DateTime.now().difference(value.date).inMinutes} minutes ago';
    prevMemoriesStr += '$timePassed\n${value.structuredMemory}\n\n';
  }

  var prompt = '''
    ${languageCode == 'en' ? 'Generate a title and a summary for the following recording chunk of a conversation.' : 'Generate a title and a summary in English for the following recording chunk of a conversation that was performed in $language.'} 
    For the title, use the most important topic or the most important action-item in the conversation.
    For the summary, Identify the specific details in the conversation and specific facts that are important to remember or
    action-items in very concise short points in second person (use bullet points). 
    
    Is possible that the transcript is only 1 speaker, in that case, is most likely the user speaking, so consider that a thought or something he wants to look at in the future and act accordingly.
    Is possible that the conversation is empty or is useless, in that case output "N/A".
    
    Here is the recording ```${rawMemory.trim()}```.
    ${prevMemoriesStr.isNotEmpty ? '''\nFor extra context consider the previous recent memories:
    These below, are the user most recent memories, they were already structured and saved, so only use them for help structuring the new memory \
    if there's some connection within those memories and the one that we are structuring right now.
    For example if the user is talking about a project, and the previous memories explain more about the project, use that information to \
    structure the new memory.\n
    ```
    $prevMemoriesStr
    ```\n''' : ''}
    Output using the following format:
    ```
    Title: ... 
    Summary:
    - Action item 1
    - Action item 2
    ...
    ```
    '''
      .replaceAll('     ', '')
      .replaceAll('    ', '')
      .trim();
  return (await executeGptPrompt(prompt)).replaceAll('```', '').trim();
}

Future<String> requestSummary(List<MemoryRecord> memories) async {
  var prompt = '''
    Based on my recent memories below, summarize everything into 3-4 most important facts I need to remember. 
    Write the final output only and make it very short and concise, less than 200 symbols total as bullet-points. 
    Make it interesting with an insight, specific, professional and simple to read:
    ``` 
    ${MemoryRecord.memoriesToString(memories)}
    ``` 
    ''';
  return await executeGptPrompt(prompt);
}

Future<List<double>> getEmbeddingsFromInput(String? input) async {
  var vector = await gptApiCall(model: 'text-embedding-3-small', urlSuffix: 'embeddings', contentToEmbed: input ?? '');
  return vector.map<double>((item) => double.tryParse(item.toString()) ?? 0.0).toList();
}

String qaStreamedFullMemories(List<MemoryRecord> memories, List<dynamic> chatHistory) {
  var prompt = '''
    You are an assistant for question-answering tasks. Use the list of stored user audio transcript memories to answer the question. 
    If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.
    
    Conversation History:
    ${chatHistory.map((e) => '${e['role'].toString().toUpperCase()}: ${e['content']}').join('\n')}

    Memories:
    ```
    ${MemoryRecord.memoriesToString(memories)}
    ```
    Answer:
    '''
      .replaceAll('    ', '');
  debugPrint(prompt);
  var body = jsonEncode({
    "model": "gpt-4-turbo",
    "messages": [
      {"role": "system", "content": prompt}
    ],
    "stream": true,
  });
  return body;
}

// ------

Future<String?> determineRequiresContext(String lastMessage, List<dynamic> chatHistory) async {
  var tools = [
    {
      "type": "function",
      "function": {
        "name": "retrieve_rag_context",
        "description": "Retrieve pieces of user memories as context.",
        "parameters": {
          "type": "object",
          "properties": {
            "question": {
              "type": "string",
              "description": '''
              Based on the current conversation, determine if the message is a question and if there's 
              context that needs to be retrieved from the user recorded audio memories in order to answer that question.
              If that's the case, return the question better parsed so that retrieved pieces of context are better.
              ''',
            },
          },
        },
      },
    }
  ];
  String message = '''
        Conversation:
        ${chatHistory.map((e) => '${e['role'].toString().toUpperCase()}: ${e['content']}').join('\n')}\n
        USER:$lastMessage
        '''
      .replaceAll('        ', '');
  debugPrint('determineRequiresContext message: $message');
  var response = await gptApiCall(
      model: 'gpt-4o',
      messages: [
        {"role": "user", "content": message}
      ],
      tools: tools);
  if (response.toString().contains('retrieve_rag_context')) {
    var args = jsonDecode(response[0]['function']['arguments']);
    return args['question'];
  }
  return null;
}

String qaStreamedBody(String context, List<dynamic> chatHistory) {
  var prompt = '''
    You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. 
    If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.
    If the message doesn't require context, it will be empty, so answer the question casually.
    
    Conversation History:
    ${chatHistory.map((e) => '${e['role'].toString().toUpperCase()}: ${e['content']}').join('\n')}

    Context:
    ``` 
    $context
    ```
    Answer:
    '''
      .replaceAll('    ', '');
  debugPrint(prompt);
  var body = jsonEncode({
    "model": "gpt-4-turbo",
    "messages": [
      {"role": "system", "content": prompt}
    ],
    "stream": true,
  });
  return body;
}

Future<String> transcribeAudioFile(File audioFile) async {
  const url = 'https://api.openai.com/v1/audio/transcriptions';
  var request = http.MultipartRequest('POST', Uri.parse(url))
    ..headers['Authorization'] = 'Bearer ${getOpenAIApiKeyForUsage()}'
    ..headers['Content-Type'] = 'multipart/form-data';
  var file = await http.MultipartFile.fromPath(
    'file',
    audioFile.path,
  );

  request.files.add(file);
  request.fields['model'] = 'whisper-1';
  request.fields['timestamp_granularities[]'] = 'word';
  request.fields['response_format'] = 'verbose_json';
  request.fields['language'] = 'en';
  // request.fields['prompt'] =
  //     'The audio of a conversation recorded with an AI wearable, it could be empty, just random noises, or have multiple speakers.';
  var response = await request.send();
  String responseBody = await response.stream.bytesToString();
  var jsonResponse = jsonDecode(responseBody);

  debugPrint('Transcript response: ${jsonResponse}');
  return '';
}
