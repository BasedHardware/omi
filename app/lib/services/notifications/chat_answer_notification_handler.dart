import 'package:awesome_notifications/awesome_notifications.dart';

import 'package:omi/utils/logger.dart';

/// Local BigText notifications for click-to-talk / chat answer pushes (#4375).
///
/// Android system FCM trays collapse long bodies without BigTextStyle. Chat
/// answers are therefore delivered as data-oriented pushes and rendered here
/// so the shade shows more of the answer and the tap payload includes
/// `navigate_to` for deep-linking into the matching chat.
class ChatAnswerNotificationHandler {
  static final _awesomeNotifications = AwesomeNotifications();

  /// True when this FCM data map is a chat/plugin answer that should use the
  /// shared BigText + deep-link path.
  static bool isChatAnswerData(Map<String, dynamic> data) {
    if (data['push_type']?.toString() == 'chat_answer') return true;
    final notificationType = data['notification_type']?.toString();
    final navigateTo = data['navigate_to']?.toString() ?? '';
    return notificationType == 'plugin' && navigateTo.startsWith('/chat/');
  }

  static Future<void> handle(
    Map<String, dynamic> data,
    String channelKey, {
    bool isAppInForeground = true,
  }) async {
    final title = (data['title']?.toString().isNotEmpty == true)
        ? data['title'].toString()
        : 'omi says';
    final body = _resolveBody(data);
    if (body.isEmpty) {
      Logger.debug('[ChatAnswerNotification] Skipping empty body');
      return;
    }

    final navigateTo = data['navigate_to']?.toString();
    final messageId = data['id']?.toString();
    final notificationId = (messageId ?? body).hashCode & 0x7fffffff;

    final payload = <String, String?>{};
    if (navigateTo != null && navigateTo.isNotEmpty) {
      payload['navigate_to'] = navigateTo;
    }
    if (messageId != null && messageId.isNotEmpty) {
      payload['message_id'] = messageId;
    }

    try {
      await _awesomeNotifications.createNotification(
        content: NotificationContent(
          id: notificationId,
          channelKey: channelKey,
          actionType: ActionType.Default,
          title: title,
          body: body,
          payload: payload,
          notificationLayout: NotificationLayout.BigText,
          wakeUpScreen: !isAppInForeground,
        ),
      );
      Logger.debug(
        '[ChatAnswerNotification] Showed BigText notification '
        'id=$notificationId navigate_to=$navigateTo foreground=$isAppInForeground',
      );
    } catch (e) {
      Logger.debug('[ChatAnswerNotification] Failed to show notification: $e');
    }
  }

  static String _resolveBody(Map<String, dynamic> data) {
    final body = data['body']?.toString();
    if (body != null && body.isNotEmpty) return body;
    final text = data['text']?.toString();
    if (text != null && text.isNotEmpty) return text;
    return '';
  }
}
