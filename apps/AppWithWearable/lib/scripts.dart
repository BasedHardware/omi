import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';

import 'backend/database/memory.dart';

migrateMemoriesCategoriesAndEmojis() async {
  if (SharedPreferencesUtil().scriptCategoriesAndEmojisExecuted) return;
  debugPrint('migrateMemoriesCategoriesAndEmojis');
  var memories = await MemoryStorage.getAllMemories();
  // var filteredMemories = await MemoryStorage.getAllMemories();
  var filteredMemories = memories.where((m) => m.structured.category.isEmpty || m.structured.emoji.isEmpty).toList();
  if (filteredMemories.isEmpty) {
    SharedPreferencesUtil().scriptCategoriesAndEmojisExecuted = true;
    return;
  }
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

migrateMemoriesToObjectBox() async {
  if (SharedPreferencesUtil().scriptMemoriesToObjectBoxExecuted) return;
  debugPrint('migrateMemoriesToObjectBox');
  var time = DateTime.now();
  var memories = (await MemoryStorage.getAllMemories(includeDiscarded: true)).reversed.toList();
  // var mem = await MemoryProvider().getMemoriesOrdered(includeDiscarded: true);
  // mem.forEach((m)=> debugPrint('${m.id.toString()}: ${m.createdAt}: ${m.structured.target!.title}'));
  MemoryProvider().removeAllMemories();
  List<Memory> memoriesOB = [];
  for (var memory in memories) {
    debugPrint('Migrating memory: ${memory.id}');
    var structured = Structured(memory.structured.title, memory.structured.overview,
        emoji: memory.structured.emoji, category: memory.structured.category);

    for (var actionItem in memory.structured.actionItems) {
      structured.actionItems.add(ActionItem(actionItem));
    }
    Memory memoryOB = Memory(memory.createdAt, memory.transcript, memory.discarded);
    memoryOB.structured.target = structured;

    for (var pluginResponse in memory.structured.pluginsResponse) {
      memoryOB.pluginsResponse.add(PluginResponse(pluginResponse));
    }
    memoriesOB.add(memoryOB);
  }
  MemoryProvider().storeMemories(memoriesOB);
  debugPrint('migrateMemoriesToObjectBox completed in ${DateTime.now().difference(time).inMilliseconds} milliseconds');
  SharedPreferencesUtil().scriptMemoriesToObjectBoxExecuted = true;

  // updatePineconeMemoryId
  for (var i = 0; i < memories.length; i++) {
    var original = memories[i];
    var memory = memoriesOB[i];
    var f = updatePineconeMemoryId(original.id, memory.id);
    if (i % 10 == 0) {
      await f;
      await Future.delayed(const Duration(seconds: 1));
    }
  }
}
