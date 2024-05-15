import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/vector_db.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:uuid/uuid.dart';
import '/backend/api_requests/api_calls.dart';
import '/flutter_flow/flutter_flow_util.dart';

// Perform actions periodically
Future<void> processTranscriptContent(String content, String? audioFileName) async {
  if (content.isNotEmpty) await memoryCreationBlock(content, audioFileName);
}

// Process the creation of memory records
Future<void> memoryCreationBlock(String rawMemory, String? audioFileName) async {
  changeAppStateMemoryCreating();
  List<MemoryRecord> recentMemories = await MemoryStorage.retrieveRecentMemoriesWithinMinutes(minutes: 10);
  var structuredMemory = await generateTitleAndSummaryForMemory(rawMemory, recentMemories);
  debugPrint('Structured Memory: $structuredMemory');
  if (structuredMemory.contains("N/A")) {
    await saveFailureMemory(rawMemory, structuredMemory);
    changeAppStateMemoryCreating();
  } else {
    await finalizeMemoryRecord(rawMemory, structuredMemory, audioFileName);
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

// Update app state when starting memory processing
void changeAppStateMemoryCreating() {
  FFAppState().update(() {
    FFAppState().memoryCreationProcessing = !FFAppState().memoryCreationProcessing;
  });
}

// Finalize memory record after processing feedback
Future<void> finalizeMemoryRecord(String rawMemory, String structuredMemory, String? audioFilePath) async {
  MemoryRecord createdMemory = await createMemoryRecord(rawMemory, structuredMemory, audioFilePath);
  changeAppStateMemoryCreating();
  List<double> vector = await getEmbeddingsFromInput(structuredMemory);
  storeMemoryVector(createdMemory, vector);
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
