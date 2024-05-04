import 'dart:convert';
import 'package:flutter/material.dart';
import '../../env/env.dart';
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
dynamic extractContentFromResponse(http.Response? response, {bool isEmbedding = false}) {
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
Future<dynamic> gptApiCall({
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

  var response = await makeApiCall(url: url, headers: headers, body: body, method: 'POST');
  return extractContentFromResponse(response, isEmbedding: urlSuffix == 'embeddings');
}

Future<String> executeGptPrompt(String? prompt) async {
  if (prompt == null) return '';
  return await gptApiCall(model: 'gpt-4-turbo', messages: [
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
  return await executeGptPrompt(prompt);
}

Future<String> getGPTFeedback(String? memory, String? structuredMemory) async {
  var prompt = '''
    you are Comind, the harsh honest and direct AI mentor who observes the conversation the user is having. 
    Based on the below conversation that your mdentee had with someone, respond with a message to your mentee in short sentences. 
    Make it very specific, short, concise, straightforward and include examples. In your response, keep everything on the same 
    line without \\n symbols, do not include quotes symbols. Ask clarifying questions. Conversation was taken with bad-quality microphone, 
    so do not include anything about clarity, conciseness or simillar. Raw conversation: \\n\\"\\"\\"$memory\\"\\"\\" 
    ''';
  return await executeGptPrompt(prompt);
}

Future<String> voiceCommandRequest(String? memory, String? longTermMemory) async {
  var prompt = '''
    LONG TERM MEMORIES: \\"\\"\\"$longTermMemory\\"\\"\\"\\n\\n CONVERSATION: \\"\\"\\"$memory\\"\\"\\"\\n\\n 
    Your name is Sama and you are harsh, funny, honest mentor who observes the conversation the user is having, 
    and they have asked you a question. You respond as concisely as possible. Figure out the question asked in the 
    latest sentence and return just your answer as best you can, concisely. \\n\\nYour answer: 
    ''';
  return await executeGptPrompt(prompt);
}

Future<String> requestSummary(String? structuredMemories) async {
  var prompt = '''
    Based on my recent memories below, summarize everything into 3-4 most important facts I need to remember. 
    Write the final output only and make it very short and concise, less than 200 symbols total as bullet-points. 
    Make it interesting with an insight, specific, professional and simple to read: $structuredMemories. 
    ''';
  return await executeGptPrompt(prompt);
}

Future<String> isFeedbackUseful(String? feedback, String? memory) async {
  var prompt = '''
    You are a mentor of a busy entrepreneur. Below is a conversation that your mentee had \\"$memory\\". 
    You provided the following feedback: \\"$feedback\\". Determine if the feedback is actually insightful and 
    important to the mentee's life or not. Return only Show or Hide. If important, return Show. If not, return Hide.
    ''';
  return await executeGptPrompt(prompt);
}

Future<List<double>> getEmbeddingsFromInput(String? input) async {
  var vector = await gptApiCall(model: 'text-embedding-3-small', urlSuffix: 'embeddings', contentToEmbed: input ?? '');
  return vector.map<double>((item) => double.tryParse(item.toString()) ?? 0.0).toList();
}

Future<dynamic> pineconeApiCall({required String urlSuffix, required String body}) async {
  var url = '${Env.pineconeIndexUrl}/$urlSuffix';
  final headers = {
    'Api-Key': Env.pineconeApiKey,
    'Content-Type': 'application/json',
  };
  var response = await makeApiCall(url: url, headers: headers, body: body, method: 'POST');
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
  var responseBody = await pineconeApiCall(urlSuffix: 'vectors/upsert', body: body);
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
  var responseBody = await pineconeApiCall(urlSuffix: 'query', body: body);
  return (responseBody['matches'])?.map((e) => e['metadata']).toList() ?? [];
}

Future<List<String>> testRequest(String? memory, String? structuredMemory) async {
  var responseBody = await gptApiCall(
      model: 'gpt-3.5-turbo',
      messages: [
        {
          'role': 'system',
          'content':
              '''You are a helpful assistant designed to output JSON in this format: key = memory. value = {your response}'''
        },
        {'role': 'user', 'content': '''return 5 random memories'''},
      ],
      jsonResponseFormat: true);
  var decoded = [jsonDecode(responseBody)];
  debugPrint('testRequest response: ${decoded.runtimeType} $decoded');
  return decoded.map<String>((e) => e.toString()).toList();
}
