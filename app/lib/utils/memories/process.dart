import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/http/webhooks.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:tuple/tuple.dart';

Future<ServerMemory?> processTranscriptContent({
  required String language,
  List<TranscriptSegment> segments = const [],
  List<Tuple2<String, String>> photos = const [],
  bool triggerIntegrations = true,
  DateTime? startedAt,
  DateTime? finishedAt,
  Geolocation? geolocation,
  File? audioFile,
  Function(ServerMessage)? sendMessageToChat,
  String? source,
  String? processingMemoryId,
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
    source: source,
    processingMemoryId: processingMemoryId,
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
    // TODO: memory created notification should be triggered from backend
    NotificationService.instance
        .createNotification(title: '$pluginId says', body: message.text, notificationId: pluginId.hashCode);
    if (sendMessageToChat != null) sendMessageToChat(message);
  }
  return result.memory;
}

Future<ServerMemory?> processMemoryContent({
  required ServerMemory memory,
  required List<ServerMessage> messages,
  Function(ServerMessage)? sendMessageToChat,
}) async {
  debugPrint('processTranscriptContent');
  webhookOnMemoryCreatedCall(memory).then((s) {
    if (s.isNotEmpty) {
      NotificationService.instance
          .createNotification(title: 'Developer: On Memory Created', body: s, notificationId: 11);
    }
  });

  for (var message in messages) {
    String pluginId = message.pluginId ?? '';
    NotificationService.instance
        .createNotification(title: '$pluginId says', body: message.text, notificationId: pluginId.hashCode);
    if (sendMessageToChat != null) sendMessageToChat(message);
  }
  return memory;
}
