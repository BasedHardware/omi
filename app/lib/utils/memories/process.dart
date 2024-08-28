import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/http/webhooks.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/services/notification_service.dart';
import 'package:tuple/tuple.dart';

Future<ServerMemory?> processTranscriptContent({
  required List<TranscriptSegment> segments,
  required String language,
  List<Tuple2<String, String>> photos = const [],
  bool triggerIntegrations = true,
  DateTime? startedAt,
  DateTime? finishedAt,
  Geolocation? geolocation,
  File? audioFile,
  Function(ServerMessage)? sendMessageToChat,
}) async {
  debugPrint('processTranscriptContent');
  if (segments.isEmpty && photos.isEmpty) return null;
  CreateMemoryResponse? result = await createMemoryServer(
    startedAt: startedAt ?? DateTime.now(),
    finishedAt: finishedAt ?? DateTime.now(),
    transcriptSegments: segments,
    geolocation: geolocation,
    photos: photos,
    triggerIntegrations: triggerIntegrations,
    language: language,
    audioFile: audioFile,
  );
  if (result == null || result.memory == null) return null;

  webhookOnMemoryCreatedCall(result.memory).then((s) {
    if (s.isNotEmpty) {
      NotificationService.instance
          .createNotification(title: 'Developer: On Memory Created', body: s, notificationId: 11);
    }
  });

  for (var message in result.messages) {
    String pluginId = message.pluginId ?? '';
    NotificationService.instance
        .createNotification(title: '$pluginId says', body: message.text, notificationId: pluginId.hashCode);
    if (sendMessageToChat != null) sendMessageToChat(message);
  }
  return result.memory;
}
