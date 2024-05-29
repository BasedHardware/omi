import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/backend/storage/segment.dart';
import 'package:friend_private/backend/utils.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/flutter_flow/flutter_flow_util.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart';

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
  } catch (e) {
    debugPrint('HTTP request failed: $e');
    return null;
  } finally {}
  return null;
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

_getPrevMemoriesStr(List<MemoryRecord> previousMemories) {
  var prevMemoriesStr = MemoryRecord.memoriesToString(previousMemories);
  return prevMemoriesStr.isNotEmpty
      ? '''\nFor extra context consider the previous recent memories:
    These below, are the user most recent memories, they were already structured and saved, so only use them for help structuring the new memory \
    if there's some connection within those memories and the one that we are structuring right now.
    For example if the user is talking about a project, and the previous memories explain more about the project, use that information to \
    structure the new memory.\n
    ```
    $prevMemoriesStr
    ```\n'''
      : '';
}

Future<Structured> generateTitleAndSummaryForMemory(String transcript, List<MemoryRecord> previousMemories) async {
  if (transcript.isEmpty || transcript.split(' ').length < 7) return Structured(actionItems: []);
  // TODO: this has to be toggled and played around
  // TODO: probably best to determine usefulness with function call before executing this prompt
  final languageCode = SharedPreferencesUtil().recordingsLanguage;
  var prompt =
      '''Based on the following recording transcript of a conversation, provide structure and clarity to the memory.
    The conversation language is $languageCode. Make sure to use English for your response.

    It is possible that the conversation is not important, has no value or is not worth remembering, in that case, output an empty title. 
    The purpose for structuring this memory is to remember important conversations, decisions, and action items. If there's nothing like that in the transcript, output an empty title.
     
    For the title, use the main topic of the conversation.
    For the overview, use a brief overview of the conversation.
    For the action items, use a list of actionable steps or bullet points for the conversation.
        
    Here is the transcript ```${transcript.trim()}```.
    ${_getPrevMemoriesStr(previousMemories)}
    
    The output should be formatted as a JSON instance that conforms to the JSON schema below.

    As an example, for the schema {"properties": {"foo": {"title": "Foo", "description": "a list of strings", "type": "array", "items": {"type": "string"}}}, "required": ["foo"]}
    the object {"foo": ["bar", "baz"]} is a well-formatted instance of the schema. The object {"properties": {"foo": ["bar", "baz"]}} is not well-formatted.
    
    Here is the output schema:
    ```
    {"properties": {"title": {"title": "Title", "description": "A title/name for this conversation", "default": "", "type": "string"}, "overview": {"title": "Overview", "description": "A brief overview of the conversation", "default": "", "type": "string"}, "action_items": {"title": "Action Items", "description": "A list of action items from the conversation", "default": [], "type": "array", "items": {"type": "string"}}}}
    ```'''
          .replaceAll('     ', '')
          .replaceAll('    ', '')
          .trim();
  var structured = (await executeGptPrompt(prompt)).replaceAll('```', '').replaceAll('json', '').trim();
  return Structured.fromJson(jsonDecode(structured));
}

Future<String> adviseOnCurrentConversation(String transcript) async {
  if (transcript.isEmpty) return '';
  if (transcript.split(' ').length < 20) return ''; // not enough to extract something out of it
  // if (transcript.contains('Speaker 0') &&
  //     (!transcript.contains('Speaker 1') && !transcript.contains('Speaker 2') && !transcript.contains('Speaker 3'))) {
  //   return '';
  // }

  var prompt = '''
    You are a conversation coach, you provide clear and concise advice for conversations in real time. 
    The following is a transcript of the conversation (in progress) where most likely I am "Speaker 0", \
    provide advice on my current way of speaking, and my interactions with the other speaker(s).
    
    Transcription:
    ```
    $transcript
    ```
    
    Consider that the transcription is not perfect, so there might be mixed up words or sentences between speakers, try to work around that.
    
    Also, it's possible that there's nothing worth notifying the user about his interactions, in that case, output N/A.
    Remember that the purpose of this advice, is to notify the user about his way of interacting in real time, so he can improve his communication skills.
    Be concise and short, respond in 10 to 15 words.
    
    IMPORTANT: Is this feedback so valuable that its worth to interrupt a busy entrepreneur? If not, output N/A.
    '''
      .replaceAll('     ', '')
      .replaceAll('    ', '')
      .trim();
  debugPrint(prompt);
  var result = await executeGptPrompt(prompt);
  if (result.contains('N/A') || result.split(' ').length < 5) return '';
  return result;
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

Future<List<double>> getEmbeddingsFromInput(String input) async {
  var vector = await gptApiCall(model: 'text-embedding-3-large', urlSuffix: 'embeddings', contentToEmbed: input);
  return vector.map<double>((item) => double.tryParse(item.toString()) ?? 0.0).toList();
}

// ------

Future<String?> determineRequiresContext(String lastMessage, List<Message> messages) async {
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
        ${messages.map((e) => '${e.type.toString().toUpperCase()}: ${e.text}').join('\n')}\n
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

Future<bool> createPineconeVectors(List<String> memoriesId, List<List<double>> vectors) async {
  var body = jsonEncode({
    'vectors': memoriesId.mapIndexed((index, id) {
      return {
        'id': id,
        'values': vectors[index],
        'metadata': {
          'created_at': DateTime.now(),
          'memory_id': id,
          'uid': SharedPreferencesUtil().uid,
        }
      };
    }).toList(),
    'namespace': Env.pineconeIndexNamespace
  });
  var responseBody = await pineconeApiCall(urlSuffix: 'vectors/upsert', body: body);
  debugPrint('createVectorPinecone response: $responseBody');
  return true;
}

Future<bool> createPineconeVector(String? memoryId, List<double>? vectorList) async {
  var body = jsonEncode({
    'vectors': [
      {
        'id': memoryId,
        'values': vectorList,
        'metadata': {
          'created_at': DateTime.now().toIso8601String(),
          'memory_id': memoryId,
          'uid': SharedPreferencesUtil().uid,
        }
      }
    ],
    'namespace': Env.pineconeIndexNamespace
  });
  var responseBody = await pineconeApiCall(urlSuffix: 'vectors/upsert', body: body);
  debugPrint('createVectorPinecone response: $responseBody');
  return (responseBody['upserted_count'] ?? 0) > 0;
}

Future<List<String>> queryPineconeVectors(List<double>? vectorList) async {
  var body = jsonEncode({
    'namespace': Env.pineconeIndexNamespace,
    'vector': vectorList,
    'topK': 5,
    'includeValues': false,
    'includeMetadata': false,
    'filter': {
      'uid': {'\$eq': SharedPreferencesUtil().uid},
    }
  });
  var responseBody = await pineconeApiCall(urlSuffix: 'query', body: body);
  debugPrint(responseBody.toString());
  return (responseBody['matches'])?.map<String>((e) => e['id'].toString()).toList() ?? [];
}

Future<bool> deleteVector(String memoryId) async {
  var body = jsonEncode({
    'ids': [memoryId],
    'namespace': Env.pineconeIndexNamespace
  });
  var response = await pineconeApiCall(urlSuffix: 'vectors/delete', body: body);
  debugPrint(response.toString());
  return true;
}

// TODO: update vectors when fields updated

Future<List<TranscriptSegment>> transcribeAudioFile(File file, String uid) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.customTranscriptApiBaseUrl}transcribe?language=en&uid=$uid'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));

  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      var data = jsonDecode(response.body);
      debugPrint('Response body: ${response.body}');
      return TranscriptSegment.fromJsonList(data);
    } else {
      debugPrint('Failed to upload file. Status code: ${response.statusCode}');
    }
  } catch (e) {
    debugPrint('An error occurred transcribeAudioFile: $e');
  }
  return [];
}
