import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:flutter_timezone/flutter_timezone.dart';
import 'package:unifiedpush/unifiedpush.dart';

import 'package:omi/backend/http/api/notifications.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/services/notifications/important_conversation_notification_handler.dart';
import 'package:omi/services/notifications/merge_notification_handler.dart';
import 'package:omi/services/notifications/notification_interface.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/notification_channel_strings.dart';

/// Self-hosted push via UnifiedPush (ADR-0011 on-prem push), no Google.
///
/// The app registers with an on-device UnifiedPush distributor (e.g. the ntfy app), receives an
/// endpoint URL, and saves it to the backend. The backend POSTs the same FCM-shaped JSON payload
/// ({notification?, data, tag, priority, is_background}) to that endpoint; here we decode it and run
/// the SAME inbound dispatch the FCM service does. Local display reuses awesome_notifications exactly
/// like the basic service. iOS/desktop have no UnifiedPush distributor and fall back to `local`.
class _UnifiedPushNotificationService implements NotificationInterface {
  _UnifiedPushNotificationService._();

  static const String _instanceName = 'default';

  // Resolved in initialize() after NotificationChannelStrings.loadAppLocale().
  late final NotificationChannel channel;

  final AwesomeNotifications _awesomeNotifications = AwesomeNotifications();

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
    await UnifiedPush.initialize(
      onNewEndpoint: _onNewEndpoint,
      onRegistrationFailed: _onRegistrationFailed,
      onUnregistered: _onUnregistered,
      onMessage: _onMessage,
    );
    Logger.debug('UnifiedPush notification service initialized');
  }

  Future<void> _initializeAwesomeNotifications() async {
    bool initialized = await _awesomeNotifications.initialize(
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
      channelGroups: [
        NotificationChannelGroup(channelGroupKey: channel.channelKey!, channelGroupName: channel.channelName!),
      ],
      debug: false,
    );
    Logger.debug('initializeNotifications: $initialized');
  }

  // --- UnifiedPush registration -------------------------------------------------------------------

  @override
  Future<void> register() async {
    final distributors = await UnifiedPush.getDistributors();
    if (distributors.isEmpty) {
      Logger.debug('UnifiedPush: no distributor installed (install e.g. the ntfy app)');
      return;
    }
    // Pick the currently-saved distributor, else the first available (typically the only one).
    final current = await UnifiedPush.getDistributor();
    if (current == null || current.isEmpty) {
      await UnifiedPush.saveDistributor(distributors.first);
    }
    await UnifiedPush.registerApp(_instanceName);
  }

  @override
  void saveNotificationToken() {
    // UnifiedPush equivalent of fetching+saving a token: (re)register with the distributor, which
    // fires onNewEndpoint and saves the endpoint to the backend.
    register();
  }

  @override
  Future<void> saveFcmToken(String? token) async {
    // No FCM tokens in UnifiedPush mode.
    Logger.debug('FCM token save skipped - UnifiedPush backend active');
  }

  Future<void> _onNewEndpoint(String endpoint, String instance) async {
    Logger.debug('UnifiedPush onNewEndpoint: $endpoint');
    final timeZone = await getTimeZone();
    await saveUnifiedPushEndpointServer(endpoint: endpoint, timeZone: timeZone);
  }

  void _onRegistrationFailed(String instance) {
    Logger.debug('UnifiedPush registration failed for instance: $instance');
  }

  void _onUnregistered(String instance) {
    Logger.debug('UnifiedPush unregistered: $instance');
  }

  // --- Inbound messages ---------------------------------------------------------------------------

  void _onMessage(Uint8List message, String instance) {
    Map<String, dynamic> decoded;
    try {
      decoded = jsonDecode(utf8.decode(message)) as Map<String, dynamic>;
    } catch (e) {
      Logger.debug('UnifiedPush: could not decode message: $e');
      return;
    }
    final data = _stringMap(decoded['data']);
    final notification = decoded['notification'] as Map<String, dynamic>?;
    _dispatch(data, notification);
  }

  /// Mirror of the FCM service's inbound dispatch, driven by the decoded JSON payload rather than a
  /// RemoteMessage. Action-item / merge / important-conversation handlers are transport-agnostic.
  void _dispatch(Map<String, String> data, Map<String, dynamic>? notification) {
    if (data.isNotEmpty) {
      final Map<String, String> payload = <String, String>{};
      final navigateTo = data['navigate_to'];
      if (navigateTo != null && navigateTo.isNotEmpty) {
        payload['navigate_to'] = navigateTo;
      }

      final messageType = data['type'];
      if (messageType == 'apple_reminders_sync') {
        return; // handled natively on iOS; irrelevant on Android UnifiedPush
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

      final notificationType = data['notification_type'];
      if (notificationType == 'plugin' || notificationType == 'daily_summary') {
        final serverData = Map<String, dynamic>.from(data);
        serverData['from_integration'] = data['from_integration'] == 'true';
        _serverMessageStreamController.add(ServerMessage.fromJson(serverData));
      }
      if (notification != null) {
        _showRemoteNotification(notification, payload: payload);
      }
      return;
    }

    if (notification != null) {
      _showRemoteNotification(notification, layout: NotificationLayout.BigText);
    }
  }

  void _showRemoteNotification(
    Map<String, dynamic> notification, {
    NotificationLayout layout = NotificationLayout.Default,
    Map<String, String?>? payload,
  }) {
    final title = notification['title'] as String?;
    final body = notification['body'] as String?;
    if (title == null || body == null) return;
    showNotification(id: Random().nextInt(10000), title: title, body: body, layout: layout, payload: payload);
  }

  // --- Local display (identical to the basic service) ---------------------------------------------

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
    if (isAllowed) {
      await register();
    }
    return isAllowed;
  }

  @override
  Future<String> getTimeZone() async {
    return await FlutterTimezone.getLocalTimezone();
  }

  @override
  Future<bool> hasNotificationPermissions() async {
    return await _awesomeNotifications.isNotificationAllowed();
  }

  @override
  Future<void> createNotification({
    String title = '',
    String body = '',
    int notificationId = 1,
    Map<String, String?>? payload,
  }) async {
    var allowed = await _awesomeNotifications.isNotificationAllowed();
    if (!allowed) return;
    showNotification(id: notificationId, title: title, body: body, wakeUpScreen: true, payload: payload);
  }

  @override
  void clearNotification(int id) => _awesomeNotifications.cancel(id);

  @override
  Future<void> listenForMessages() async {
    // Inbound delivery is wired through UnifiedPush.initialize's onMessage callback.
  }

  final _serverMessageStreamController = StreamController<ServerMessage>.broadcast();

  @override
  Stream<ServerMessage> get listenForServerMessages => _serverMessageStreamController.stream;

  Map<String, String> _stringMap(dynamic raw) {
    if (raw is Map) {
      return raw.map((key, value) => MapEntry(key.toString(), value?.toString() ?? ''));
    }
    return <String, String>{};
  }
}

/// Factory function to create the UnifiedPush notification service
NotificationInterface createNotificationService() => _UnifiedPushNotificationService._();
