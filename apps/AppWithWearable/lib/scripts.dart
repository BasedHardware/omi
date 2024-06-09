import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';

migrateMemoriesCategoriesAndEmojis() async {
  if (!SharedPreferencesUtil().scriptCategoriesAndEmojisExecuted) return;
  debugPrint('migrateMemoriesCategoriesAndEmojis');
  var memories = await MemoryStorage.getAllMemories();
  // var filteredMemories = await MemoryStorage.getAllMemories();
  var filteredMemories = memories.where((m) => m.structured.category.isEmpty || m.structured.emoji.isEmpty).toList();
  var str = jsonEncode(
      filteredMemories.map((m) => '${m.createdAt}\n${m.structured.title}\n${m.structured.overview}').toList());
  var prompt = '''
  From the following user memories, extract the information requested below. 
  ```$str```
  
  The output should be formatted as a JSON instance that conforms to the JSON schema below.

  As an example, for the schema {"properties": {"foo": {"title": "Foo", "description": "a list of strings", "type": "array", "items": {"type": "string"}}}, "required": ["foo"]}
  the object {"foo": ["bar", "baz"]} is a well-formatted instance of the schema. The object {"properties": {"foo": ["bar", "baz"]}} is not well-formatted.
  
  Here is the output schema:
  ```
  {"properties": {"parsed": {"title": "Parsed", "type": "array", "items": {"\$ref": "#/definitions/StructuredMemory"}}}, "required": ["parsed"], "definitions": {"CategoryEnum": {"title": "CategoryEnum", "description": "An enumeration.", "enum": ["personal", "education", "health", "finance", "legal", "phylosophy", "spiritual", "science", "entrepreneurship", "parenting", "romantic", "travel", "inspiration", "technology", "business", "social", "work", "other"], "type": "string"}, "StructuredMemory": {"title": "StructuredMemory", "type": "object", "properties": {"category": {"description": "A category for this memory", "default": "other", "allOf": [{"\$ref": "#/definitions/CategoryEnum"}]}, "emoji": {"title": "Emoji", "description": "An emoji to represent the memory", "default": "🧠", "type": "string"}}}}}
  ```
  '''
      .replaceAll('  ', '')
      .trim();

  String response = await executeGptPrompt(prompt);
  var structured = jsonDecode(response.replaceAll('```', '').replaceAll('json', '').trim())['parsed'];
  for (int i = 0; i < filteredMemories.length; i++) {
    String category = structured[i]['category'];
    MemoryRecord memory = filteredMemories[i];
    memory.structured.category = category;
    memory.structured.emoji = structured[i]['emoji'];
    MemoryStorage.updateWholeMemory(memory);
  }
  debugPrint('migrateMemoriesCategoriesAndEmojis completed');
  SharedPreferencesUtil().scriptCategoriesAndEmojisExecuted = true;
}
