import 'dart:async';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:flutter/material.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

/// Event data for important conversation completion
class ImportantConversationEvent {
  final String conversationId;
  final String navigateTo;

  ImportantConversationEvent({
    required this.conversationId,
    required this.navigateTo,
  });
}

/// Handler for important conversation FCM notifications
/// Triggered when a conversation >30 minutes completes processing
class ImportantConversationNotificationHandler {
  static final _awesomeNotifications = AwesomeNotifications();

  /// Stream controller for important conversation events
  static final StreamController<ImportantConversationEvent> _importantConversationController =
      StreamController<ImportantConversationEvent>.broadcast();

  /// Stream to listen for important conversation events
  static Stream<ImportantConversationEvent> get onImportantConversation => _importantConversationController.stream;

  /// Handle important_conversation FCM data message
  ///
  /// The app receives this when a long conversation (>30 min) completes processing.
  /// - Foreground: Provider can show toast, then user can tap notification
  /// - Background: Shows a local notification that navigates to conversation detail with share sheet
  static Future<void> handleImportantConversation(
    Map<String, dynamic> data,
    String channelKey, {
    bool isAppInForeground = true,
  }) async {
    final conversationId = data['conversation_id'];
    final navigateTo = data['navigate_to'] as String?;

    if (conversationId == null) {
      debugPrint('[ImportantConversationNotification] Invalid data: missing conversation_id');
      return;
    }

    debugPrint('[ImportantConversationNotification] Important conversation completed: $conversationId');
    debugPrint('[ImportantConversationNotification] Navigate to: $navigateTo');

    // Track notification received
    MixpanelManager().importantConversationNotificationReceived(conversationId);

    // Broadcast the event so providers can update their state
    _importantConversationController.add(ImportantConversationEvent(
      conversationId: conversationId,
      navigateTo: navigateTo ?? '/conversation/$conversationId?share=1',
    ));

    // Always show notification (foreground and background) so user can tap to share
    await _showImportantConversationNotification(
      channelKey: channelKey,
      conversationId: conversationId,
      navigateTo: navigateTo ?? '/conversation/$conversationId?share=1',
    );
  }

  /// Show local notification for important conversation
  static Future<void> _showImportantConversationNotification({
    required String channelKey,
    required String conversationId,
    required String navigateTo,
  }) async {
    try {
      final notificationId = conversationId.hashCode;

      await _awesomeNotifications.createNotification(
        content: NotificationContent(
          id: notificationId,
          channelKey: channelKey,
          title: 'Important Conversation',
          body: 'You just had an important convo. Tap to share the summary with others.',
          payload: {
            'conversation_id': conversationId,
            'navigate_to': navigateTo,
          },
          notificationLayout: NotificationLayout.Default,
          category: NotificationCategory.Social,
        ),
      );

      debugPrint('[ImportantConversationNotification] Showed notification for conversation: $conversationId');
    } catch (e) {
      debugPrint('[ImportantConversationNotification] Error showing notification: $e');
    }
  }
}
