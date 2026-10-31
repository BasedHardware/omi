import 'package:omi/services/recap_events.dart';
import 'package:omi/env/physical_qualification.dart';
import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_timezone/flutter_timezone.dart';

import 'package:omi/backend/http/api/notifications.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/notifications/fcm_token_registration.dart';
import 'package:omi/services/notifications.dart' show NotificationUtil;
import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/services/notifications/chat_answer_notification_handler.dart';
import 'package:omi/services/notifications/important_conversation_notification_handler.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/notification_channel_strings.dart';

/// Firebase Cloud Messaging enabled notification service
/// Supports iOS, Android, macOS, web, and Linux with full FCM functionality
class _FCMNotificationService with WidgetsBindingObserver implements NotificationInterface {
  _FCMNotificationService._();

  final FirebaseMessaging _firebaseMessaging = FirebaseMessaging.instance;

  // Resolved in initialize() after NotificationChannelStrings.loadAppLocale().
  late final NotificationChannel channel;

  final AwesomeNotifications _awesomeNotifications = AwesomeNotifications();
  bool _registrationReady = false;
  bool _registrationListenersInstalled = false;
  bool _messageListenersInstalled = false;
  late final FcmTokenRegistration _registration = FcmTokenRegistration(
    capture: () {
      final owner = AuthService.instance.captureSessionSnapshot();
      // Capturing may synchronously report an account change and revoke the
      // admission flag. A refresh event must not admit that replacement user.
      return _registrationReady ? owner : null;
    },
    isCurrent: (owner) => AuthService.instance.isSessionSnapshotCurrent(owner),
    readApns: _firebaseMessaging.getAPNSToken,
    readToken: _firebaseMessaging.getToken,
    readTimeZone: getTimeZone,
    requiresApns: Platform.isIOS,
    persist: (token, zone, owner) async {
      bool current() => AuthService.instance.isSessionSnapshotCurrent(owner);
      final accepted = await saveFcmTokenServer(token: token, timeZone: zone, canSend: current);
      if (!accepted || !current()) return false;
      unawaited(Future<void>.sync(() async {
        try {
          if (current()) await IntercomManager.instance.sendTokenToIntercom(token);
        } catch (error) {
          Logger.debug('Intercom push registration deferred: ${error.runtimeType}');
        }
      }));
      return current();
    },
  );

  @override
  Future<void> initialize() async {
    await NotificationChannelStrings.loadAppLocale();
    channel = NotificationChannel(
      channelGroupKey: 'channel_group_key',
      channelKey: 'channel',
      channelName: NotificationChannelStrings.omiChannelName,
      channelDescription: NotificationChannelStrings.omiChannelDescription,
      defaultColor: const Color(0xFF9D50DD),
      ledColor: Colors.white,
    );
    await _initializeAwesomeNotifications();
    if (PhysicalQualification.enabled) return;
    if (!_registrationListenersInstalled) {
      _registrationListenersInstalled = true;
      WidgetsBinding.instance.addObserver(this);
      // Install before the first token lookup; startup/permission timing cannot
      // lose a rotation, and repeated sign-ins cannot add duplicate listeners.
      _firebaseMessaging.onTokenRefresh.listen((token) {
        if (_registrationReady) unawaited(saveFcmToken(token));
      }, onError: (Object error) {
        Logger.debug('Push token stream deferred: ${error.runtimeType}');
      });
      AuthService.instance.sessionGenerationEvents.listen((_) {
        _registrationReady = false;
        _registration.invalidateSession();
      });
    }
    listenForMessages();
  }

  Future<void> _initializeAwesomeNotifications() async {
    bool initialized = await _awesomeNotifications.initialize(
      // set the icon to null if you want to use the default app icon
      'resource://drawable/icon',
      [
        NotificationChannel(
          channelGroupKey: 'channel_group_key',
          channelKey: channel.channelKey,
          channelName: channel.channelName,
          channelDescription: channel.channelDescription,
          defaultColor: const Color(0xFF9D50DD),
          ledColor: Colors.white,
        ),
      ],
      // Channel groups are only visual and are not required
      channelGroups: [
        NotificationChannelGroup(channelGroupKey: channel.channelKey!, channelGroupName: channel.channelName!),
      ],
      debug: false,
    );

    Logger.debug('initializeNotifications: $initialized');

    // Reset badge to clear existing badge count if any
    int badgeCount = await _awesomeNotifications.getGlobalBadgeCounter();
    if (badgeCount > 0) await _awesomeNotifications.resetGlobalBadge();
  }

  @override
  Future<void> showNotification({
    required int id,
    required String title,
    required String body,
    Map<String, String?>? payload,
    bool wakeUpScreen = false,
    NotificationSchedule? schedule,
    NotificationLayout layout = NotificationLayout.Default,
  }) async {
    final allowed = await _awesomeNotifications.isNotificationAllowed();
    if (!allowed) {
      return;
    }
    try {
      await _awesomeNotifications.createNotification(
        content: NotificationContent(
          id: id,
          channelKey: channel.channelKey!,
          actionType: ActionType.Default,
          title: title,
          body: body,
          payload: payload,
          notificationLayout: layout,
        ),
      );
    } catch (e) {
      Logger.debug('Failed to create notification (channel may be disabled): $e');
    }
  }

  @override
  Future<bool> requestNotificationPermissions() async {
    bool isAllowed = await _awesomeNotifications.isNotificationAllowed();
    if (!isAllowed) {
      isAllowed = await _awesomeNotifications.requestPermissionToSendNotifications();
    }
    if (isAllowed) unawaited(register());
    return isAllowed;
  }

  @override
  Future<void> register() async {
    if (PhysicalQualification.enabled) return;
    // Existing sign-in/restored-shell/permission entry points admit the owner.
    // Settle a newly observed auth generation before enabling token callbacks.
    final owner = AuthService.instance.captureSessionSnapshot();
    if (owner == null) {
      _registrationReady = false;
      _registration.invalidateSession();
      return;
    }
    _registrationReady = true;
    await _registration.refresh();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _registrationReady) unawaited(register());
  }

  @override
  Future<String> getTimeZone() async {
    final timezone = await FlutterTimezone.getLocalTimezone();
    return timezone.identifier;
  }

  @override
  Future<void> saveFcmToken(String? token) async {
    if (PhysicalQualification.enabled || !_registrationReady || token == null || token.isEmpty) return;
    await _registration.refresh(token: token);
  }

  @override
  void saveNotificationToken() async {
    await register();
  }

  @override
  Future<bool> hasNotificationPermissions() async {
    return await _awesomeNotifications.isNotificationAllowed();
  }

  @override
  Future<bool> createNotification({
    String title = '',
    String body = '',
    int notificationId = 1,
    Map<String, String?>? payload,
  }) async {
    var allowed = await _awesomeNotifications.isNotificationAllowed();
    Logger.debug('createNotification: $allowed');
    if (!allowed) return false;
    Logger.debug('createNotification ~ Creating notification: $title');
    showNotification(id: notificationId, title: title, body: body, wakeUpScreen: true, payload: payload);
    return true;
  }

  @override
  void clearNotification(int id) => _awesomeNotifications.cancel(id);

  bool _shouldShowForegroundNotificationOnFCMMessageReceived() {
    return Platform.isAndroid;
  }

  @override
  Future<void> listenForMessages() async {
    if (PhysicalQualification.enabled) return;
    if (_messageListenersInstalled) return;
    _messageListenersInstalled = true;
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      final data = message.data;
      final noti = message.notification;

      // Plugin
      if (data.isNotEmpty) {
        final Map<String, String> payload = <String, String>{
          for (final entry in data.entries)
            if (entry.value != null) entry.key: '${entry.value}',
        };

        // Handle action item data messages
        final messageType = data['type'];
        if (messageType == 'apple_reminders_sync') {
          // Handled natively by AppDelegate; foreground resume catches missed FCM
          return;
        } else if (messageType == 'action_item_reminder') {
          ActionItemNotificationHandler.handleReminderMessage(data, channel.channelKey!);
          return;
        } else if (messageType == 'action_item_update') {
          ActionItemNotificationHandler.handleUpdateMessage(data, channel.channelKey!);
          return;
        } else if (messageType == 'action_item_delete') {
          ActionItemNotificationHandler.handleDeletionMessage(data);
          return;
        } else if (messageType == 'action_item_batch_delete') {
          ActionItemNotificationHandler.handleBatchDeletionMessage(data);
          return;
        } else if (messageType == 'merge_completed') {
          MergeNotificationHandler.handleMergeCompleted(data, channel.channelKey!, isAppInForeground: true);
          return;
        } else if (messageType == 'important_conversation') {
          ImportantConversationNotificationHandler.handleImportantConversation(
            data,
            channel.channelKey!,
            isAppInForeground: true,
          );
          return;
        }

        // plugin, daily summary
        final notificationType = data['notification_type'];
        if (notificationType == 'plugin' || notificationType == 'daily_summary') {
          data['from_integration'] = data['from_integration'] == 'true';
          _serverMessageStreamController.add(ServerMessage.fromJson(data));
          if (notificationType == 'daily_summary') announceRecapArrived();
        }

        // Click-to-talk / chat answers: BigText + navigate_to payload (#4375).
        // Keep ServerMessage emission above so in-app consumers still receive it.
        // Match the legacy foreground path: suppress shade noise while Omi speaks.
        if (ChatAnswerNotificationHandler.isChatAnswerData(data) && !OmiVoicePlaybackService.instance.isSpeaking) {
          ChatAnswerNotificationHandler.handle(data, channel.channelKey!, isAppInForeground: true);
          return;
        }

        if (noti != null && _shouldShowForegroundNotificationOnFCMMessageReceived()) {
          if (!OmiVoicePlaybackService.instance.isSpeaking) {
            final route = payload['navigate_to'] ?? '';
            final layout = route.startsWith('/chat/') ? NotificationLayout.BigText : NotificationLayout.Default;
            _showForegroundNotification(noti: noti, layout: layout, payload: payload);
          }
        }
        return;
      }

      // Announcement likes
      if (noti != null && _shouldShowForegroundNotificationOnFCMMessageReceived()) {
        if (!OmiVoicePlaybackService.instance.isSpeaking) {
          _showForegroundNotification(noti: noti, layout: NotificationLayout.BigText);
        }
        return;
      }
    });

    Future<void> handleNotificationTap(RemoteMessage? message) async {
      if (message == null) return;
      final objectId = _notificationObjectId(message.data);
      await NotificationUtil.handleFcmDataTap(message.data, objectId: objectId);
    }

    // Background: app is backgrounded and the user taps a push notification (#5126).
    FirebaseMessaging.onMessageOpenedApp.listen(handleNotificationTap);

    // Terminated: app was killed and opened via notification tap (#5126).
    FirebaseMessaging.instance.getInitialMessage().then(handleNotificationTap);
  }

  RecordReference? _notificationObjectId(Map<String, dynamic> data) {
    for (final key in const ['conversation_id', 'summary_id', 'message_id']) {
      final value = data[key];
      if (value is! String || value.isEmpty) continue;
      try {
        return RecordReference.fromId(value);
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  final _serverMessageStreamController = StreamController<ServerMessage>.broadcast();

  @override
  Stream<ServerMessage> get listenForServerMessages => _serverMessageStreamController.stream;

  Future<void> _showForegroundNotification({
    required RemoteNotification noti,
    NotificationLayout layout = NotificationLayout.Default,
    Map<String, String?>? payload,
  }) async {
    if (noti.title == null || noti.body == null) return;
    final id = Random().nextInt(10000);
    showNotification(id: id, title: noti.title!, body: noti.body!, layout: layout, payload: payload);
  }
}

/// Factory function to create the FCM notification service
NotificationInterface createNotificationService() => _FCMNotificationService._();
