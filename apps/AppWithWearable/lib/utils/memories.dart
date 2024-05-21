import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/vector_db.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:uuid/uuid.dart';
import '/backend/api_requests/api_calls.dart';
import '/flutter_flow/flutter_flow_util.dart';

// Perform actions periodically
Future<void> processTranscriptContent(BuildContext context, String content, String? audioFileName) async {
  if (content.isNotEmpty) await memoryCreationBlock(context, content, audioFileName);
}

// Process the creation of memory records
Future<void> memoryCreationBlock(BuildContext context, String rawMemory, String? audioFileName) async {
  List<MemoryRecord> recentMemories = await MemoryStorage.retrieveRecentMemoriesWithinMinutes(minutes: 10);
  String structuredMemory;
  try {
    structuredMemory = await generateTitleAndSummaryForMemory(rawMemory, recentMemories);
  } catch (e) {
    debugPrint('Error: $e');
    ScaffoldMessenger.of(context).removeCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('There was an error creating your memory, please check your open AI API keys.')));
    return;
  }
  debugPrint('Structured Memory: $structuredMemory');
  if (structuredMemory.contains("N/A")) {
    await saveFailureMemory(rawMemory, structuredMemory);
    ScaffoldMessenger.of(context).removeCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
      content: Text(
        'Recent Memory Discarded! Nothing useful. 😄',
        style: TextStyle(color: Colors.white),
      ),
      duration: Duration(seconds: 4),
    ));
  } else {
    await finalizeMemoryRecord(rawMemory, structuredMemory, audioFileName);
    ScaffoldMessenger.of(context).removeCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
      content: Text('New Memory Created! 🚀', style: TextStyle(color: Colors.white)),
      duration: Duration(seconds: 4),
    ));
  }
}

// Save failure memory when structured memory contains NA
Future<void> saveFailureMemory(String rawMemory, String structuredMemory) async {
  MemoryRecord memory = MemoryRecord(
      id: const Uuid().v4(),
      date: DateTime.now(),
      rawMemory: rawMemory,
      structuredMemory: structuredMemory,
      isEmpty: rawMemory == '',
      isUseless: true);
  MemoryStorage.addMemory(memory);
}

// Finalize memory record after processing feedback
Future<void> finalizeMemoryRecord(String rawMemory, String structuredMemory, String? audioFilePath) async {
  MemoryRecord createdMemory = await createMemoryRecord(rawMemory, structuredMemory, audioFilePath);
  getEmbeddingsFromInput(structuredMemory).then((vector) => storeMemoryVector(createdMemory, vector));
  // storeMemoryVector
}

// Create memory record
Future<MemoryRecord> createMemoryRecord(String rawMemory, String structuredMemory, String? audioFileName) async {
  var memory = MemoryRecord(
      id: const Uuid().v4(),
      date: DateTime.now(),
      rawMemory: rawMemory,
      structuredMemory: structuredMemory,
      isEmpty: rawMemory == '',
      isUseless: false,
      audioFileName: audioFileName);
  MemoryStorage.addMemory(memory);
  debugPrint('createMemoryRecord added memory: ${memory.id}');
  return memory;
}
