import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/utils.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;

Future<http.Response?> makeApiCall({
  required String url,
  required Map<String, String> headers,
  required String body,
  required String method,
}) async {
  try {
    if (method == 'POST') {
      return await http.post(Uri.parse(url), headers: headers, body: body);
    } else if (method == 'GET') {
      return await http.get(Uri.parse(url), headers: headers);
    }
    return null;
  } catch (e) {
    debugPrint('HTTP request failed: $e');
    return null;
  }
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
    // TODO: include a global error handler + memory creation
    debugPrint('Error fetching data: ${response?.statusCode}');
    return {'error': response?.statusCode};
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
}) async {
  final url = 'https://api.openai.com/v1/$urlSuffix';
  final prefs = await SharedPreferences.getInstance();
  final apiKey = prefs.getString('openaiApiKey') ?? '';
  final headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Authorization': 'Bearer $apiKey',
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

  var prefs = await SharedPreferences.getInstance();
  var promptBase64 = base64Encode(utf8.encode(prompt));
  var cachedResponse = prefs.getString(promptBase64);
  if (cachedResponse != null) return cachedResponse;

  String response = await gptApiCall(model: 'gpt-4-turbo', messages: [
    {'role': 'system', 'content': prompt}
  ]);
  prefs.setString(promptBase64, response);
  return response;
}

Future<String> generateTitleAndSummaryForMemory(String? memory) async {
  final prefs = await SharedPreferences.getInstance();
  final languageCode = prefs.getString('recordingsLanguage') ?? 'en';
  final language = availableLanguagesByCode[languageCode] ?? 'English';

  var prompt = '''
    ${languageCode == 'en' ? 'Generate a title and a summary for the following recording chunk of a conversation.' : 'Generate a title and a summary in English for the following recording chunk of a conversation that was performed in $language.'} 
    For the title, use the most important topic or the most important action-item in the conversation.
    For the summary, Identify the specific details in the conversation and specific facts that are important to remember or
    action-items in very concise short points in second person (use bullet points). 
    
    Is possible that the conversation is empty or is useless, in that case output "N/A".
    Here is the recording ```$memory```.
    
    Remember to output using the following format:
    ```
    Title: ... 
    Summary:
    - Action item 1
    - Action item 2
    ...
    ```
    ''';
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
      model: 'gpt-4-turbo',
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
