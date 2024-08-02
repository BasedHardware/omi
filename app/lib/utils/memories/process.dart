import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/memories.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/server/memory.dart';
import 'package:friend_private/utils/memories/integrations.dart';
import 'package:tuple/tuple.dart';

// Perform actions periodically
Future<ServerMemory?> processTranscriptContent(
  BuildContext context,
  String transcript,
  List<TranscriptSegment> transcriptSegments,
  String? recordingFilePath, {
  bool retrievedFromCache = false,
  DateTime? startedAt,
  DateTime? finishedAt,
  Geolocation? geolocation,
  List<Tuple2<String, String>> photos = const [],
  Function(Message, ServerMemory?)? sendMessageToChat,
}) async {
  debugPrint('processTranscriptContent');
  if (transcript.isEmpty && photos.isEmpty) return null;
  // TODO: handle connection errors, or anything
  // store locally first, with a flag of send to server once the app connects again to the internet.
  CreateMemoryResponse? result = await createMemoryServer(
    startedAt: startedAt ?? DateTime.now(),
    finishedAt: finishedAt ?? DateTime.now(),
    transcriptSegments: transcriptSegments,
    geolocation: geolocation,
  );
  if (result == null) return null;
  ServerMemory? memory = result.memory;
  if (memory == null) return null;

  // TODO: include photos
  triggerMemoryCreatedEvents(memory);
  // TODO: use result.messages to add them to the chat manually
  return memory;
}
