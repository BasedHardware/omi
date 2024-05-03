import 'package:flutter/material.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:uuid/uuid.dart';
import '/backend/api_requests/api_calls.dart';
import '/flutter_flow/flutter_flow_util.dart';

// Perform actions periodically
Future<void> processRecentWords() async {
  String lastWords = getLastWords();
  if (lastWords.isNotEmpty) {
    FFAppState().lastMemory = lastWords; // why not .update(() => ...
    await memoryCreationBlock();
  }
}

String getLastWords() {
  String lastTranscript = FFAppState().lastTranscript;
  String newestTranscript = FFAppState().stt;

  FFAppState().update(() {
    FFAppState().lastTranscript = newestTranscript;
  });

  int charCount = lastTranscript.length;
  String lastWords = '';
  if (newestTranscript.length > charCount) {
    lastWords = newestTranscript.substring(charCount).trim();
  }

  debugPrint("[LAST WORDS]: $lastWords");
  debugPrint("[LAST TRANSCRIPT]: $lastTranscript");
  debugPrint("[NEWEST TRANSCRIPT]: $newestTranscript");
  return lastWords;
}

// Process the creation of memory records
Future<void> memoryCreationBlock() async {
  changeAppStateMemoryCreating();
  var structuredMemory = await structureMemory();
  debugPrint('Structured Memory: $structuredMemory');
  if (structuredMemory.contains("N/A")) {
    await saveFailureMemory(structuredMemory);
  } else {
    await finalizeMemoryRecord(structuredMemory);
  }
}

// Call to the API to get structured memory
Future<String> structureMemory() async {
  return await generateTitleAndSummaryForMemory(FFAppState().lastMemory);
}

// Save failure memory when structured memory contains NA
Future<void> saveFailureMemory(String structuredMemory) async {
  MemoryRecord memory = MemoryRecord(
      id: const Uuid().v4(),
      date: DateTime.now(),
      rawMemory: FFAppState().lastMemory,
      structuredMemory: structuredMemory,
      isEmpty: FFAppState().lastMemory == '',
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
Future<void> finalizeMemoryRecord(String structuredMemory) async {
  await createMemoryRecord(structuredMemory);
  changeAppStateMemoryCreating();
}

// Create memory record
Future<MemoryRecord> createMemoryRecord(String structuredMemory) async {
  var memory = MemoryRecord(
      id: const Uuid().v4(),
      date: DateTime.now(),
      rawMemory: FFAppState().lastMemory,
      structuredMemory: structuredMemory,
      isEmpty: FFAppState().lastMemory == '',
      isUseless: false);
  MemoryStorage.addMemory(memory);
  return memory;
}
