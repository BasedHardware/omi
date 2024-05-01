import 'dart:convert';
import 'package:flutter/material.dart';
import '../../env/env.dart';
import 'package:http/http.dart' as http;

Future<http.Response?> _makeApiCall({
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
dynamic _extractContentFromResponse(http.Response? response, {bool isEmbedding = false}) {
  if (response != null && response.statusCode == 200) {
    var data = jsonDecode(response.body);
    if (isEmbedding) {
      var embedding = data['data'][0]['embedding'];
      return embedding;
    }
    return data['choices'][0]['message']['content'];
  } else {
    debugPrint('Error fetching data: ${response?.statusCode}');
    return null;
  }
}

// A general call function for the GPT API.
Future<dynamic> _gptApiCall({
  required String model,
  String urlSuffix = 'chat/completions',
  List<Map<String, String>> messages = const [],
  String contentToEmbed = '',
  bool jsonResponseFormat = false,
}) async {
  final url = 'https://api.openai.com/v1/$urlSuffix';
  final headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Authorization': 'Bearer ${Env.openAIApiKey}',
    'OpenAI-Organization': Env.openAIOrganization,
  };
  final String body;
  if (urlSuffix == 'embeddings') {
    body = jsonEncode({'model': model, 'input': contentToEmbed});
  } else {
    var bodyData = {'model': model, 'messages': messages};
    if (jsonResponseFormat) {
      bodyData['response_format'] = {'type': 'json_object'};
    }
    body = jsonEncode(bodyData);
  }

  var response = await _makeApiCall(url: url, headers: headers, body: body, method: 'POST');
  return _extractContentFromResponse(response, isEmbedding: urlSuffix == 'embeddings');
}

Future<String> _executeGptPrompt(String? prompt) async {
  if (prompt == null) return '';
  return await _gptApiCall(model: 'gpt-4-turbo', messages: [
    {'role': 'system', 'content': prompt}
  ]);
}

Future<String> generateTitleAndSummaryForMemory(String? memory) async {
  var prompt = '''
    Generate a title and a summary for the following recording chunk of a conversation.
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
  return await _executeGptPrompt(prompt);
}

Future<List<double>> getEmbeddingsFromInput(String? input) async {
  var vector = await _gptApiCall(model: 'text-embedding-3-small', urlSuffix: 'embeddings', contentToEmbed: input ?? '');
  return vector.map<double>((item) => double.tryParse(item.toString()) ?? 0.0).toList();
}

Future<dynamic> _pineconeApiCall({required String urlSuffix, required String body}) async {
  var url = '${Env.pineconeIndexUrl}/$urlSuffix';
  final headers = {
    'Api-Key': Env.pineconeApiKey,
    'Content-Type': 'application/json',
  };
  var response = await _makeApiCall(url: url, headers: headers, body: body, method: 'POST');
  var responseBody = jsonDecode(response?.body ?? '{}');
  return responseBody;
}

Future<bool> createPineconeVector(List<double>? vectorList, String? structuredMemory, String? id) async {
  var body = jsonEncode({
    'vectors': [
      {
        'id': id,
        'values': vectorList,
        'metadata': {'structuredMemory': structuredMemory}
      }
    ],
    'namespace': Env.pineconeIndexNamespace
  });
  var responseBody = await _pineconeApiCall(urlSuffix: 'vectors/upsert', body: body);
  debugPrint('createVectorPinecone response: $responseBody');
  return (responseBody['upserted_count'] ?? 0) > 0;
}

Future<List> queryPineconeVectors(List<double>? vectorList) async {
  var body = jsonEncode({
    'namespace': Env.pineconeIndexNamespace,
    'vector': vectorList,
    'topK': 10,
    'includeValues': true,
    'includeMetadata': true,
    'filter': {'genre': {}}
  });
  var responseBody = await _pineconeApiCall(urlSuffix: 'query', body: body);
  return (responseBody['matches'])?.map((e) => e['metadata']).toList() ?? [];
}
