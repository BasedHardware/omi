import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

// Perform actions periodically
Future<Memory?> processTranscriptContent(
  BuildContext context,
  String transcript,
  List<TranscriptSegment> transcriptSegments,
  String? recordingFilePath, {
  bool retrievedFromCache = false,
  DateTime? startedAt,
  DateTime? finishedAt,
}) async {
  if (transcript.isNotEmpty) {
    Memory? memory = await memoryCreationBlock(
      context,
      transcript,
      transcriptSegments,
      recordingFilePath,
      retrievedFromCache,
      startedAt,
      finishedAt,
    );
    devModeWebhookCall(memory);
    MemoryProvider().saveMemory(memory);
    return memory;
  }
  return null;
}

Future<MemoryStructured?> _retrieveStructure(
  BuildContext context,
  String transcript,
  bool retrievedFromCache, {
  bool ignoreCache = false,
}) async {
  MemoryStructured structuredMemory;
  try {
    structuredMemory = await generateTitleAndSummaryForMemory(transcript, [], ignoreCache: ignoreCache);
  } catch (e, stacktrace) {
    debugPrint('Error: $e');
    CrashReporting.reportHandledCrash(e, stacktrace, level: NonFatalExceptionLevel.error, userAttributes: {
      'transcript_length': transcript.length.toString(),
      'transcript_words': transcript.split(' ').length.toString(),
      'language': SharedPreferencesUtil().recordingsLanguage,
      'developer_mode_enabled': SharedPreferencesUtil().devModeEnabled.toString(),
      'dev_mode_has_api_key': (SharedPreferencesUtil().openAIApiKey != '').toString(),
    });
    return null;
  }
  return structuredMemory;
}

// Process the creation of memory records
Future<Memory> memoryCreationBlock(
  BuildContext context,
  String transcript,
  List<TranscriptSegment> transcriptSegments,
  String? recordingFilePath,
  bool retrievedFromCache,
  DateTime? startedAt,
  DateTime? finishedAt,
) async {
  MemoryStructured? structuredMemory = await _retrieveStructure(context, transcript, retrievedFromCache);
  bool failed = false;
  if (structuredMemory == null) {
    structuredMemory = await _retrieveStructure(context, transcript, retrievedFromCache, ignoreCache: true);
    if (structuredMemory == null) {
      failed = true;
      structuredMemory = MemoryStructured(actionItems: [], pluginsResponse: [], category: 'failed', emoji: '😢');
      if (!retrievedFromCache) {
        InstabugLog.logError('Unable to create memory structure.');
        ScaffoldMessenger.of(context).removeCurrentSnackBar();
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text(
            'Unexpected error creating your memory. Please check your discarded memories.',
            style: TextStyle(color: Colors.white),
          ),
          duration: Duration(seconds: 4),
        ));
      }
    }
  }
  debugPrint('Structured Memory: $structuredMemory');

  if (structuredMemory.title.isEmpty && !retrievedFromCache && !failed) {
    ScaffoldMessenger.of(context).removeCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
      content: Text(
        'Memory stored as discarded! Nothing useful. 😄',
        style: TextStyle(color: Colors.white),
      ),
      duration: Duration(seconds: 4),
    ));
  }

  Memory memory = await finalizeMemoryRecord(
    transcript,
    transcriptSegments,
    structuredMemory,
    recordingFilePath,
    startedAt,
    finishedAt,
    structuredMemory.title.isEmpty,
  );
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

// Finalize memory record after processing feedback
Future<Memory> finalizeMemoryRecord(
  String transcript,
  List<TranscriptSegment> transcriptSegments,
  MemoryStructured structuredMemory,
  String? recordingFilePath,
  DateTime? startedAt,
  DateTime? finishedAt,
  bool discarded,
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
  var memory = Memory(
    DateTime.now(),
    transcript,
    discarded,
    recordingFilePath: recordingFilePath,
    startedAt: startedAt,
    finishedAt: finishedAt,
  );
  memory.transcriptSegments.addAll(transcriptSegments);
  memory.structured.target = structured;

  for (var r in structuredMemory.pluginsResponse) {
    memory.pluginsResponse.add(PluginResponse(r.item2, pluginId: r.item1.id));
  }

  MemoryProvider().saveMemory(memory);
  if (!discarded) {
    getEmbeddingsFromInput(structuredMemory.toString()).then((vector) {
      createPineconeVector(memory.id.toString(), vector, memory.createdAt);
    });
  }
  return memory;
}
