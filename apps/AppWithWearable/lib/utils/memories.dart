import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

// Perform actions periodically
Future<Memory?> processTranscriptContent(
  BuildContext context,
  String content,
  String? recordingFilePath, {
  bool retrievedFromCache = false,
  DateTime? startedAt,
  DateTime? finishedAt,
}) async {
  if (content.isNotEmpty) {
    Memory? memory = await memoryCreationBlock(
      context,
      content,
      recordingFilePath,
      retrievedFromCache,
      startedAt,
      finishedAt,
    );
    devModeWebhookCall(memory);
    return memory;
  }
  return null;
}

// Process the creation of memory records
Future<Memory?> memoryCreationBlock(
  BuildContext context,
  String transcript,
  String? recordingFilePath,
  bool retrievedFromCache,
  DateTime? startedAt,
  DateTime? finishedAt,
) async {
  MemoryStructured structuredMemory;
  try {
    structuredMemory = await generateTitleAndSummaryForMemory(transcript, []); // recentMemories
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
    var created = await saveFailureMemory(transcript, structuredMemory, startedAt, finishedAt);
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
    return created;
  } else {
    Memory memory = await finalizeMemoryRecord(transcript, structuredMemory, recordingFilePath, startedAt, finishedAt);
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
}

// Save failure memory when structured memory contains empty string
Future<Memory> saveFailureMemory(
  String transcript,
  MemoryStructured structuredMemory,
  DateTime? startedAt,
  DateTime? finishedAt,
) async {
  Structured structured = Structured(
    structuredMemory.title,
    structuredMemory.overview,
    emoji: structuredMemory.emoji,
    category: structuredMemory.category,
  );
  Memory memory = Memory(DateTime.now(), transcript, true, startedAt: startedAt, finishedAt: finishedAt);
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
  DateTime? startedAt,
  DateTime? finishedAt,
) async {
  Structured structured = Structured(
    structuredMemory.title,
    structuredMemory.overview,
    emoji: structuredMemory.emoji,
    category: structuredMemory.category,
  );
  for (var actionItem in structuredMemory.actionItems) {
    structured.actionItems.add(ActionItem(actionItem));
  }
  var memory = Memory(DateTime.now(), transcript, false,
      recordingFilePath: recordingFilePath, startedAt: startedAt, finishedAt: finishedAt);
  memory.structured.target = structured;
  for (var r in structuredMemory.pluginsResponse) {
    memory.pluginsResponse.add(PluginResponse(r));
  }

  await MemoryProvider().saveMemory(memory);

  getEmbeddingsFromInput(structuredMemory.toString()).then((vector) {
    createPineconeVector(memory.id.toString(), vector);
  });
  return memory;
}
