import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api/memories.dart';
import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/server/memory.dart';
import 'package:friend_private/backend/server/message.dart';
import 'package:friend_private/utils/other/notifications.dart';
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
  Function(ServerMessage, ServerMemory?)? sendMessageToChat,
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
    photos: photos,
  );
  if (result == null) return null;
  ServerMemory? memory = result.memory;
  if (memory == null) return null;

  // EVENTS
  webhookOnMemoryCreatedCall(memory).then((s) {
    if (s.isNotEmpty) createNotification(title: 'Developer: On Memory Created', body: s, notificationId: 11);
  });

  for (var message in result.messages) {
    String pluginId = message.pluginId ?? '';
    createNotification(title: '$pluginId says', body: message.text, notificationId: pluginId.hashCode);
    if (sendMessageToChat != null) sendMessageToChat(message, memory);
  }
  return memory;
}
