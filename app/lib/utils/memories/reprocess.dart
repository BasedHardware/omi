import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<Memory?> reProcessMemory(
  BuildContext context,
  Memory memory,
  Function onFailedProcessing,
  Function changeLoadingState,
) async {
  debugPrint('_reProcessMemory');
  changeLoadingState();
  SummaryResult summaryResult;
  try {
    summaryResult = await summarizeMemory(
      memory.transcript,
      [],
      forceProcess: true,
      conversationDate: memory.createdAt,
    );
  } catch (err, stacktrace) {
    print(err);
    var memoryReporting = MixpanelManager().getMemoryEventProperties(memory);
    CrashReporting.reportHandledCrash(err, stacktrace, level: NonFatalExceptionLevel.critical, userAttributes: {
      'memory_transcript_length': memoryReporting['transcript_length'].toString(),
      'memory_transcript_word_count': memoryReporting['transcript_word_count'].toString(),
      // 'memory_transcript_language': memoryReporting['transcript_language'], // TODO: this is incorrect
    });
    onFailedProcessing();
    changeLoadingState();
    return null;
  }
  // TODO: move this to a method from structured?
  Structured structured = memory.structured.target!;
  Structured newStructured = summaryResult.structured;
  structured.title = newStructured.title;
  structured.overview = newStructured.overview;
  structured.emoji = newStructured.emoji;
  structured.category = newStructured.category;

  structured.actionItems.clear();
  structured.actionItems.addAll(newStructured.actionItems.map<ActionItem>((i) => ActionItem(i.description)).toList());

  structured.events.clear();
  for (var event in newStructured.events) {
    structured.events.add(Event(event.title, event.startsAt, event.duration, description: event.description));
  }

  memory.structured.target = structured;
  memory.discarded = false;
  memory.pluginsResponse.clear();
  memory.pluginsResponse.addAll(
    summaryResult.pluginsResponse.map<PluginResponse>((e) => PluginResponse(e.item2, pluginId: e.item1.id)).toList(),
  );

  // Add Calendar Events

  getEmbeddingsFromInput(structured.toString()).then((vector) {
    // TODO: update instead if it wasn't "discarded"
    upsertPineconeVector(memory.id.toString(), vector, memory.createdAt);
  });

  MemoryProvider().updateMemoryStructured(structured);
  MemoryProvider().updateMemory(memory);
  debugPrint('MemoryProvider().updateMemory');
  changeLoadingState();
  MixpanelManager().reProcessMemory(memory);
  return memory;
}
