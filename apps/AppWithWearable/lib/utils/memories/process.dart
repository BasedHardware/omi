import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:friend_private/utils/memories/integrations.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';

// Perform actions periodically
Future<Memory?> processTranscriptContent(
  BuildContext context,
  String transcript,
  List<TranscriptSegment> transcriptSegments,
  String? recordingFilePath, {
  bool retrievedFromCache = false,
  DateTime? startedAt,
  DateTime? finishedAt,
  Geolocation? geolocation,
  List<Tuple2<String, String>> photos = const [],
  Function(Message, Memory?)? sendMessageToChat,
}) async {
  if (transcript.isNotEmpty || photos.isNotEmpty) {
    Memory? memory = await memoryCreationBlock(
      context,
      transcript,
      transcriptSegments,
      recordingFilePath,
      retrievedFromCache,
      startedAt,
      finishedAt,
      geolocation,
      photos,
    );
    MemoryProvider().saveMemory(memory);
    triggerMemoryCreatedEvents(memory, sendMessageToChat: sendMessageToChat);
    return memory;
  }
  return null;
}

Future<SummaryResult?> _retrieveStructure(
  BuildContext context,
  String transcript,
  List<Tuple2<String, String>> photos,
  bool retrievedFromCache, {
  bool ignoreCache = false,
}) async {
  SummaryResult summary;
  try {
    if (photos.isNotEmpty) {
      summary = await summarizePhotos(photos);
    } else {
      summary = await summarizeMemory(transcript, [], ignoreCache: ignoreCache);
    }
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
  return summary;
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
  Geolocation? geolocation,
  List<Tuple2<String, String>> photos,
) async {
  SummaryResult? summarizeResult = await _retrieveStructure(context, transcript, photos, retrievedFromCache);
  bool failed = false;
  if (summarizeResult == null) {
    summarizeResult = await _retrieveStructure(context, transcript, photos, retrievedFromCache, ignoreCache: true);
    if (summarizeResult == null) {
      failed = true;
      summarizeResult = SummaryResult(Structured('', '', emoji: '😢', category: 'failed'), []);
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
  Structured structured = summarizeResult.structured;

  if (SharedPreferencesUtil().calendarEnabled &&
      SharedPreferencesUtil().deviceId.isNotEmpty &&
      SharedPreferencesUtil().calendarType == 'auto') {
    for (var event in structured.events) {
      event.created =
          await CalendarUtil().createEvent(event.title, event.startsAt, event.duration, description: event.description);
    }
  }

  Memory memory = await finalizeMemoryRecord(
    transcript,
    transcriptSegments,
    structured,
    summarizeResult.pluginsResponse,
    recordingFilePath,
    startedAt,
    finishedAt,
    structured.title.isEmpty,
    geolocation,
    photos,
  );
  debugPrint('Memory created: ${memory.id}');

  if (!retrievedFromCache) {
    if (structured.title.isEmpty && !failed) {
      ScaffoldMessenger.of(context).removeCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text(
          'Memory stored as discarded! Nothing useful. 😄',
          style: TextStyle(color: Colors.white),
        ),
        duration: Duration(seconds: 4),
      ));
    } else if (structured.title.isNotEmpty) {
      ScaffoldMessenger.of(context).removeCurrentSnackBar();
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('New memory created! 🚀', style: TextStyle(color: Colors.white)),
        duration: Duration(seconds: 4),
      ));
    }
  }
  return memory;
}

// Finalize memory record after processing feedback
Future<Memory> finalizeMemoryRecord(
  String transcript,
  List<TranscriptSegment> transcriptSegments,
  Structured structured,
  List<Tuple2<Plugin, String>> pluginsResponse,
  String? recordingFilePath,
  DateTime? startedAt,
  DateTime? finishedAt,
  bool discarded,
  Geolocation? geolocation,
  List<Tuple2<String, String>> photos,
) async {
  var memory = Memory(
    DateTime.now(),
    transcript,
    discarded,
    recordingFilePath: recordingFilePath,
    startedAt: startedAt,
    finishedAt: finishedAt,
  );
  if (geolocation != null) {
    memory.geolocation.target = geolocation;
  }
  memory.transcriptSegments.addAll(transcriptSegments);
  memory.structured.target = structured;

  for (var r in pluginsResponse) {
    memory.pluginsResponse.add(PluginResponse(r.item2, pluginId: r.item1.id));
  }

  for (var image in photos) {
    memory.photos.add(MemoryPhoto(image.item1, image.item2));
  }

  MemoryProvider().saveMemory(memory);
  if (!discarded) {
    getEmbeddingsFromInput(structured.toString()).then((vector) {
      upsertPineconeVector(memory.id.toString(), vector, memory.createdAt);
    });
  }
  MixpanelManager().memoryCreated(memory);
  return memory;
}
