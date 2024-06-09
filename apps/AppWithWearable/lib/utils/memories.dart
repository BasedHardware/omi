import 'package:flutter/material.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:uuid/uuid.dart';
import '/backend/api_requests/api_calls.dart';

// Perform actions periodically
Future<MemoryRecord?> processTranscriptContent(
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
Future<MemoryRecord?> memoryCreationBlock(
  BuildContext context,
  String transcript,
  String? recordingFilePath,
  bool retrievedFromCache,
) async {
  List<MemoryRecord> recentMemories = await MemoryStorage.retrieveRecentMemoriesWithinMinutes(minutes: 10);
  Structured structuredMemory;
  try {
    structuredMemory = await generateTitleAndSummaryForMemory(transcript, recentMemories);
  } catch (e) {
    debugPrint('Error: $e');
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
    MemoryRecord memory = await finalizeMemoryRecord(transcript, structuredMemory, recordingFilePath);
    MixpanelManager().memoryCreated(memory);
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
Future<MemoryRecord> saveFailureMemory(String transcript, Structured structuredMemory) async {
  MemoryRecord memory = MemoryRecord(
      id: const Uuid().v4(),
      createdAt: DateTime.now(),
      transcript: transcript,
      structured: structuredMemory,
      discarded: true);
  MemoryStorage.addMemory(memory);
  MixpanelManager().memoryCreated(memory);
  return memory;
}

// Finalize memory record after processing feedback
Future<MemoryRecord> finalizeMemoryRecord(
    String transcript, Structured structuredMemory, String? recordingFilePath) async {
  MemoryRecord createdMemory = await createMemoryRecord(transcript, structuredMemory, recordingFilePath);
  getEmbeddingsFromInput(structuredMemory.toString()).then((vector) {
    createPineconeVector(createdMemory.id, vector);
  });
  return createdMemory;
  // storeMemoryVector
}

// Create memory record
Future<MemoryRecord> createMemoryRecord(String transcript, Structured structured, String? recordingFilePath) async {
  var memory = MemoryRecord(
      id: const Uuid().v4(),
      createdAt: DateTime.now(),
      transcript: transcript,
      structured: structured,
      discarded: false,
      recordingFilePath: recordingFilePath);
  MemoryStorage.addMemory(memory);
  debugPrint('createMemoryRecord added memory: ${memory.id}');
  return memory;
}
