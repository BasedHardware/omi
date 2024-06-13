import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

import '/backend/api_requests/api_calls.dart';

// Perform actions periodically
Future<Memory?> processTranscriptContent(
    BuildContext context, String content, String? audioFileName, String? recordingFilePath,
    {bool retrievedFromCache = false}) async {
  if (content.isNotEmpty) {
    return await memoryCreationBlock(
      context,
      content,
      recordingFilePath,
      retrievedFromCache,
    );
  }
  return null;
}

// Process the creation of memory records
Future<Memory?> memoryCreationBlock(
  BuildContext context,
  String transcript,
  String? recordingFilePath,
  bool retrievedFromCache,
) async {
  List<Memory> recentMemories = await MemoryProvider().retrieveRecentMemoriesWithinMinutes(minutes: 10);
  MemoryStructured structuredMemory;
  try {
    structuredMemory = await generateTitleAndSummaryForMemory(transcript, recentMemories);
  } catch (e) {
    debugPrint('Error: $e');
    InstabugLog.logError(e.toString());
    if (!retrievedFromCache) {
      ScaffoldMessenger.of(context).removeCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('There was an error creating your memory, please check your open AI API keys.')));
    }
    return null;
  }
  debugPrint('Structured Memory: $structuredMemory');

  if (structuredMemory.title.isEmpty) {
    await saveFailureMemory(transcript, structuredMemory);
    if (!retrievedFromCache) {
      ScaffoldMessenger.of(context).removeCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text(
          'Memory stored as discarded! Nothing useful. 😄',
          style: TextStyle(color: Colors.white),
        ),
        duration: Duration(seconds: 4),
      ));
    }
  } else {
    Memory memory = await finalizeMemoryRecord(transcript, structuredMemory, recordingFilePath);
    debugPrint('Memory created: ${memory.id}');
    if (!retrievedFromCache) {
      ScaffoldMessenger.of(context).removeCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('New memory created! 🚀', style: TextStyle(color: Colors.white)),
        duration: Duration(seconds: 4),
      ));
    }
    return memory;
  }
  return null;
}

// Save failure memory when structured memory contains empty string
Future<Memory> saveFailureMemory(String transcript, MemoryStructured structuredMemory) async {
  Structured structured = Structured(
    structuredMemory.title,
    structuredMemory.overview,
    emoji: structuredMemory.emoji,
    category: structuredMemory.category,
  );
  Memory memory = Memory(DateTime.now(), transcript, true);
  memory.structured.target = structured;
  MemoryProvider().saveMemory(memory);
  MixpanelManager().memoryCreated(memory);
  return memory;
}

// Finalize memory record after processing feedback
Future<Memory> finalizeMemoryRecord(
  String transcript,
  MemoryStructured structuredMemory,
  String? recordingFilePath,
) async {
  Structured structured = Structured(
    structuredMemory.title,
    structuredMemory.overview,
    emoji: structuredMemory.emoji,
    category: structuredMemory.category,
  );
  var memory = Memory(DateTime.now(), transcript, false, recordingFilePath: recordingFilePath);
  memory.structured.target = structured;

  await MemoryProvider().saveMemory(memory);

  getEmbeddingsFromInput(structuredMemory.toString()).then((vector) {
    createPineconeVector(memory.id.toString(), vector);
  });
  return memory;
}
