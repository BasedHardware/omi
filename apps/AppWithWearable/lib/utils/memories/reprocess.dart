import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

Future<Memory?> reProcessMemory(
  BuildContext context,
  StateSetter setModalState,
  Memory memory,
  Function onFailedProcessing,
  Function changeLoadingState,
) async {
  debugPrint('_reProcessMemory');
  changeLoadingState();
  MemoryStructured structured;
  try {
    structured = await generateTitleAndSummaryForMemory(memory.transcript, [], forceProcess: true);
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
  Structured current = memory.structured.target!;
  current.title = structured.title;
  current.overview = structured.overview;
  current.emoji = structured.emoji;
  current.category = structured.category;
  current.actionItems.clear();
  current.actionItems.addAll(structured.actionItems.map<ActionItem>((e) => ActionItem(e)).toList());

  memory.structured.target = current;
  memory.discarded = false;
  memory.pluginsResponse.clear();
  memory.pluginsResponse.addAll(
    structured.pluginsResponse.map<PluginResponse>((e) => PluginResponse(e.item2, pluginId: e.item1.id)).toList(),
  );

  // Add Calendar Events
  current.events.clear();
  for (var event in structured.events) {
    current.events.add(
      CalendarEvent(
          title: event.title, description: event.description, startsAt: event.startsAt, duration: event.duration),
    );
  }
  getEmbeddingsFromInput(structured.toString()).then((vector) {
    // TODO: update instead if it wasn't "discarded"
    createPineconeVector(memory.id.toString(), vector, memory.createdAt);
  });

  MemoryProvider().updateMemoryStructured(current);
  MemoryProvider().updateMemory(memory);
  debugPrint('MemoryProvider().updateMemory');
  changeLoadingState();
  MixpanelManager().reProcessMemory(memory);
  return memory;
}
