import 'dart:convert';
import 'dart:typed_data';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/llm.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/utils/other/string_utils.dart';
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

Future<String> dailySummaryNotifications(List<Memory> memories) async {
  var msg = 'There were no memories today, don\'t forget to wear your Friend tomorrow 😁';
  if (memories.isEmpty) return msg;
  if (memories.where((m) => !m.discarded).length <= 1) return msg;
  var str = SharedPreferencesUtil().givenName.isEmpty ? 'the user' : SharedPreferencesUtil().givenName;
  var prompt = '''
  The following are a list of $str\'s memories from today, with the transcripts with its respective structuring, that $str had during his day.
  $str wants to get a summary of the key action items he has to take based on his today's memories.

  Remember $str is busy so this has to be very efficient and concise.
  Respond in at most 50 words.
  
  Output your response in plain text, without markdown.
  ```
  ${Memory.memoriesToString(memories, includeTranscript: true)}
  ```
  ''';
  debugPrint(prompt);
  var result = await executeGptPrompt(prompt);
  debugPrint('dailySummaryNotifications result: $result');
  return result.replaceAll('```', '').trim();
}

// ------

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

// TODO: another thought is to ask gpt for a list of "scenes", so each one could be stored independently in vectors
// Future<List<int>> determineImagesToKeep(List<Tuple2<Uint8List, String>> images) async {
//   // was thinking here to take all images, and based on description, filter the ones that do not have repeated descriptions.
//   String prompt = '''
//   You will be provided with a list of descriptions of images that were taken from POV, with 5 seconds difference between each photo.
//
//   Your task is to discard the repeated pictures, and output the indexes of the images that do not refer to the same scene, keeping only 1 description for the scene (so 1 index).
//
//   Images: [${images.map((e) => "\"${e.item2}\"").join(', ')}]
//
//   The output should be formatted as a JSON instance that conforms to the JSON schema below.
//
//   As an example, for the schema {"properties": {"foo": {"title": "Foo", "description": "a list of strings", "type": "array", "items": {"type": "string"}}}, "required": ["foo"]}
//   the object {"foo": ["bar", "baz"]} is a well-formatted instance of the schema. The object {"properties": {"foo": ["bar", "baz"]}} is not well-formatted.
//
//   Here is the output schema:
//   ```
//   {"properties": {"indices": {"title": "Indices", "description": "The indices of the images that are relevant", "default": [], "type": "array", "items": {"type": "integer"}}}}
//   ```
//   ''';
//   var response = await executeGptPrompt(prompt);
//   var result = jsonDecode(response.replaceAll('json', '').replaceAll('```', ''));
//   result['indices'] = result['indices'].map<int>((e) => e as int).toList();
//   print(result['indices']);
//   return result['indices'];
// }

// TODO: migrate openglass to backend
Future<SummaryResult> summarizePhotos(List<Tuple2<String, String>> images) async {
  var prompt =
      '''The user took a series of pictures from his POV, and generated a description for each photo, and wants to create a memory from them.

    For the title, use the main topic of the scenes.
    For the overview, condense the descriptions into a brief summary with the main topics discussed, make sure to capture the key points and important details.
    For the category, classify the scenes into one of the available categories.
        
    Photos Descriptions: ```${images.mapIndexed((i, e) => "${i + 1}. \"${e.item2}\"").join('\n')}```
    
    The output should be formatted as a JSON instance that conforms to the JSON schema below.

    As an example, for the schema {"properties": {"foo": {"title": "Foo", "description": "a list of strings", "type": "array", "items": {"type": "string"}}}, "required": ["foo"]}
    the object {"foo": ["bar", "baz"]} is a well-formatted instance of the schema. The object {"properties": {"foo": ["bar", "baz"]}} is not well-formatted.
    
    Here is the output schema:
    ```
    {"properties": {"title": {"title": "Title", "description": "A title/name for this conversation", "default": "", "type": "string"}, "overview": {"title": "Overview", "description": "An overview of the multiple scenes, highlighting the key details from it", "default": "", "type": "string"}, "category": {"description": "A category for this memory", "default": "other", "allOf": [{"\$ref": "#/definitions/CategoryEnum"}]}, "emoji": {"title": "Emoji", "description": "An emoji to represent the memory", "default": "\ud83e\udde0", "type": "string"}}, "definitions": {"CategoryEnum": {"title": "CategoryEnum", "description": "An enumeration.", "enum": ["personal", "education", "health", "finance", "legal", "phylosophy", "spiritual", "science", "entrepreneurship", "parenting", "romantic", "travel", "inspiration", "technology", "business", "social", "work", "other"], "type": "string"}}}
    ```
    '''
          .replaceAll('     ', '')
          .replaceAll('    ', '')
          .trim();
  debugPrint(prompt);
  var structuredResponse = extractJson(await executeGptPrompt(prompt));
  var structured = Structured.fromJson(jsonDecode(structuredResponse));
  return SummaryResult(structured, []);
}
