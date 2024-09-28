import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/webhooks.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/services/notifications.dart';

Future<ServerMemory?> processMemoryContent({
  required ServerMemory memory,
  required List<ServerMessage> messages,
  Function(ServerMessage)? sendMessageToChat,
}) async {
  debugPrint('processTranscriptContent');
  webhookOnMemoryCreatedCall(memory).then((s) {
    if (s.isNotEmpty) {
      NotificationService.instance.createNotification(
        title: 'Developer: On Memory Created',
        body: s,
        notificationId: 11,
      );
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
