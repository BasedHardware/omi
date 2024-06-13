import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/backend/storage/plugin.dart';
import 'package:friend_private/backend/storage/sample.dart';
import 'package:friend_private/backend/storage/segment.dart';
import 'package:friend_private/env/env.dart';
import 'package:http/http.dart' as http;
import 'package:instabug_http_client/instabug_http_client.dart';
import 'package:intl/intl.dart';
import 'package:path/path.dart';

import '../../utils/string_utils.dart';

Future<http.Response?> makeApiCall({
  required String url,
  required Map<String, String> headers,
  required String body,
  required String method,
}) async {
  try {
    final client = InstabugHttpClient();

    if (method == 'POST') {
      return await client.post(Uri.parse(url), headers: headers, body: body);
    } else if (method == 'GET') {
      return await client.get(Uri.parse(url), headers: headers);
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
  double temperature = 0.3,
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

_getPrevMemoriesStr(List<Memory> previousMemories) {
  var prevMemoriesStr = Memory.memoriesToString(previousMemories);
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

Future<MemoryStructured> generateTitleAndSummaryForMemory(String transcript, List<Memory> previousMemories) async {
  if (transcript.isEmpty || transcript.split(' ').length < 7) {
    return MemoryStructured(actionItems: [], pluginsResponse: [], category: '');
  }

  final languageCode = SharedPreferencesUtil().recordingsLanguage;
  final pluginsEnabled = SharedPreferencesUtil().pluginsEnabled;
  // final plugin = SharedPreferencesUtil().pluginsList.firstWhereOrNull((e) => pluginsEnabled.contains(e.id));
  final pluginsList = SharedPreferencesUtil().pluginsList;
  final enabledPlugins = pluginsList.where((e) => pluginsEnabled.contains(e.id)).toList();

  var prompt =
      '''Based on the following recording transcript of a conversation, provide structure and clarity to the memory in JSON according rules stated below.
    The conversation language is $languageCode. Make sure to use English for your response.

    It is possible that the conversation is not important, has no value or is not worth remembering, in that case, output an empty title. 
    The purpose for structuring this memory is to remember important conversations, decisions, and action items. If there's nothing like that in the transcript, output an empty title.
     
    For the title, use the main topic of the conversation.
    For the overview, use a brief overview of the conversation.
    For the action items, use a list of actionable steps or bullet points for the conversation.
    For the category, classify the conversation into one of the available categories.
        
    Here is the transcript ```${transcript.trim()}```.
    ${_getPrevMemoriesStr(previousMemories)}
    
    The output should be formatted as a JSON instance that conforms to the JSON schema below.
    
    As an example, for the schema {"properties": {"foo": {"title": "Foo", "description": "a list of strings", "type": "array", "items": {"type": "string"}}}, "required": ["foo"]}
    the object {"foo": ["bar", "baz"]} is a well-formatted instance of the schema. The object {"properties": {"foo": ["bar", "baz"]}} is not well-formatted.
    
    Here is the output schema:
    ```
    {"properties": {"title": {"title": "Title", "description": "A title/name for this conversation", "default": "", "type": "string"}, "overview": {"title": "Overview", "description": "A brief overview of the conversation", "default": "", "type": "string"}, "action_items": {"title": "Action Items", "description": "A list of action items from the conversation", "default": [], "type": "array", "items": {"type": "string"}}, "category": {"description": "A category for this memory", "default": "other", "allOf": [{"\$ref": "#/definitions/CategoryEnum"}]}, "emoji": {"title": "Emoji", "description": "An emoji to represent the memory", "default": "\ud83e\udde0", "type": "string"}}, "definitions": {"CategoryEnum": {"title": "CategoryEnum", "description": "An enumeration.", "enum": ["personal", "education", "health", "finance", "legal", "phylosophy", "spiritual", "science", "entrepreneurship", "parenting", "romantic", "travel", "inspiration", "technology", "business", "social", "work", "other"], "type": "string"}}}
    ```
    '''
          .replaceAll('     ', '')
          .replaceAll('    ', '')
          .trim();

  List<Future<String>> pluginPrompts = enabledPlugins.map((plugin) async {
    String response = await executeGptPrompt(
        '''Your are ${plugin.name}, ${plugin.prompt}, Conversation: ```${transcript.trim()} ${_getPrevMemoriesStr(previousMemories)}, you must start your output with heading as ${plugin.name}, you must only use valid english alphabets and words for your response, use pain text without markdown```. ''');
    return response;
  }).toList();

  Future<List<String>> allPluginResponses = Future.wait(pluginPrompts);
  var structuredResponse = extractJson(await executeGptPrompt(prompt));
  List<String> responses = await allPluginResponses;
  var json = jsonDecode(structuredResponse);
  return MemoryStructured.fromJson(json..['pluginsResponse'] = responses);
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

Future<List<double>> getEmbeddingsFromInput(String input) async {
  var vector = await gptApiCall(model: 'text-embedding-3-large', urlSuffix: 'embeddings', contentToEmbed: input);
  return vector.map<double>((item) => double.tryParse(item.toString()) ?? 0.0).toList();
}

// ------

Future<String?> determineRequiresContext(List<Message> messages) async {
  String message = '''
        Based on the current conversation an AI is having with a Human, determine if the AI requires more context to answer to the user.
        More context could mean, user stored old conversations, notes, or information that seems very user-specific.
        
        - First determine if the conversation requires context, in the field "requires_context".
        - If it does, provide the topic (1 or 2 words, e.g. "Startups" "Funding" "Business Meetings") that is going to be used to retrieve more context, in the field "query". Leave empty if not context is needed.
        
        Conversation:
        ${messages.map((e) => '${e.type.toString().toUpperCase()}: ${e.text}').join('\n')}\n
        
        The output should be formatted as a JSON instance that conforms to the JSON schema below.
        As an example, for the schema {"properties": {"foo": {"title": "Foo", "description": "a list of strings", "type": "array", "items": {"type": "string"}}}, "required": ["foo"]}
        the object {"foo": ["bar", "baz"]} is a well-formatted instance of the schema. The object {"properties": {"foo": ["bar", "baz"]}} is not well-formatted.

        Here is the output schema:
        ```
        {"properties": {"requires_context": {"title": "Requires context", \"description": "Based on the conversation, this tells if context is needed to answer", "default": false, "type": "bool"}, "query": {"title": "Query", "description": "If context is required, the main topic to retrieve context from", "default": "", "type": "string"}, }}
        ```
        '''
      .replaceAll('        ', '');
  debugPrint('determineRequiresContext message: $message');
  var response = await gptApiCall(model: 'gpt-4o', messages: [
    {"role": "user", "content": message}
  ]);
  debugPrint('determineRequiresContext response: $response');
  try {
    return jsonDecode(response.toString().replaceAll('```', '').replaceAll('json', '').trim())['query'];
  } catch (e) {
    return null;
  }
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

Future<void> updatePineconeMemoryId(String memoryId, int newId) {
  return pineconeApiCall(
      urlSuffix: 'vectors/update',
      body: jsonEncode({
        'id': memoryId,
        'setMetadata': {'memory_id': newId.toString()},
        'namespace': Env.pineconeIndexNamespace,
      }));
}

Future<bool> createPineconeVector(String? memoryId, List<double>? vectorList) async {
  var body = jsonEncode({
    'vectors': [
      {
        'id': memoryId,
        'values': vectorList,
        'metadata': {
          'created_at':
              DateFormat("yyyy-MM-dd HH:mm:ss.SSSSSS").parse(DateTime.now().toString()).millisecondsSinceEpoch ~/ 1000,
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

/// Queries Pinecone vectors and optionally filters results based on a date range.
/// The startTimestamp and endTimestamp should be provided as UNIX epoch timestamps in seconds.
/// For example: 1622520000 represents Jun 01 2021 10:00:00 UTC.
Future<List<String>> queryPineconeVectors(List<double>? vectorList, {int? startTimestamp, int? endTimestamp}) async {
  // Constructing the filter condition based on optional timestamp parameters
  Map<String, dynamic> filter = {
    'uid': {'\$eq': SharedPreferencesUtil().uid},
  };

  // Add date filtering if startTimestamp or endTimestamp is provided
  if (startTimestamp != null || endTimestamp != null) {
    filter['created_at'] = {};

    if (startTimestamp != null) {
      filter['created_at']['\$gte'] = startTimestamp;
    }

    if (endTimestamp != null) {
      filter['created_at']['\$lte'] = endTimestamp;
    }
  }

  var body = jsonEncode({
    'namespace': Env.pineconeIndexNamespace,
    'vector': vectorList,
    'topK': 5,
    'includeValues': false,
    'includeMetadata': true,
    'filter': filter,
  });
  var responseBody = await pineconeApiCall(urlSuffix: 'query', body: body);
  debugPrint(responseBody.toString());
  return (responseBody['matches'])?.map<String>((e) => e['metadata']['memory_id'].toString()).toList() ?? [];
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

Future<List<Plugin>> retrievePlugins() async {
  var response = await makeApiCall(
      url: 'https://raw.githubusercontent.com/BasedHardware/Friend/main/community-plugins.json',
      headers: {},
      body: '',
      method: 'GET');
  if (response?.statusCode == 200) {
    try {
      return Plugin.fromJsonList(jsonDecode(response!.body));
    } catch (e) {
      return [];
    }
  }
  return [];
}

// TODO: update vectors when fields updated

Future<List<TranscriptSegment>> transcribeAudioFile(File file, String uid) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse(
        '${Env.customTranscriptApiBaseUrl}transcribe?language=${SharedPreferencesUtil().recordingsLanguage}&uid=$uid'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));

  try {
    var startTime = DateTime.now();
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);
    debugPrint('TranscribeAudioFile took: ${DateTime.now().difference(startTime).inSeconds} seconds');
    if (response.statusCode == 200) {
      var data = jsonDecode(response.body);
      debugPrint('Response body: ${response.body}');
      return TranscriptSegment.fromJsonList(data);
    } else {
      throw Exception('Failed to upload file. Status code: ${response.statusCode} Body: ${response.body}');
    }
  } catch (e) {
    throw Exception('An error occurred transcribeAudioFile: $e');
  }
}

Future<bool> userHasSpeakerProfile(String uid) async {
  var response = await makeApiCall(
    url: '${Env.customTranscriptApiBaseUrl}profile?uid=$uid',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return false;
  debugPrint('userHasSpeakerProfile: ${response.body}');
  return jsonDecode(response.body)['has_profile'] ?? false;
}

Future<List<SpeakerIdSample>> getUserSamplesState(String uid) async {
  var response = await makeApiCall(
    url: '${Env.customTranscriptApiBaseUrl}samples?uid=$uid',
    headers: {},
    method: 'GET',
    body: '',
  );
  if (response == null) return [];
  debugPrint('getUserSamplesState: ${response.body}');
  return SpeakerIdSample.fromJsonList(jsonDecode(response.body));
}

Future<bool> uploadSample(File file, String uid) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('${Env.customTranscriptApiBaseUrl}samples/upload?uid=$uid'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', file.path, filename: basename(file.path)));

  try {
    var streamedResponse = await request.send();
    var response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      debugPrint('uploadSample Response body: ${jsonDecode(response.body)}');
      return true;
    } else {
      debugPrint('Failed to upload sample. Status code: ${response.statusCode}');
      throw Exception('Failed to upload sample. Status code: ${response.statusCode}');
    }
  } catch (e) {
    debugPrint('An error occurred uploadSample: $e');
    throw Exception('An error occurred uploadSample: $e');
  }
}
