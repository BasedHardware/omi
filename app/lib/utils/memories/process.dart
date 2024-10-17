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
  for (var message in messages) {
    String appId = message.appId ?? '';
    NotificationService.instance
        .createNotification(title: '$appId says', body: message.text, notificationId: appId.hashCode);
    if (sendMessageToChat != null) sendMessageToChat(message);
  }
  webhookOnMemoryCreatedCall(memory).then((s) {
    if (s.isNotEmpty) {
      NotificationService.instance.createNotification(
        title: 'Developer: On Memory Created',
        body: s,
        notificationId: 11,
      );
    }
  });

  return memory;
}
