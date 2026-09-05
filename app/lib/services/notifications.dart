import 'dart:async';
import 'dart:isolate';
import 'dart:ui';

import 'package:flutter/material.dart';

import 'package:awesome_notifications/awesome_notifications.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:url_launcher/url_launcher.dart';

// Re-export the main notification service for backward compatibility
// All notification functionality is now handled by the platform-aware service

export 'package:omi/services/notifications/notification_service.dart';

class NotificationUtil {
  static ReceivePort? receivePort;

  static Future<void> initializeNotificationsEventListeners() async {
    // Only after at least the action method is set, the notification events are delivered
    AwesomeNotifications().setListeners(onActionReceivedMethod: NotificationUtil.onActionReceivedMethod);
  }

  static Future<void> initializeIsolateReceivePort() async {
    receivePort = ReceivePort('Notification action port in main isolate');
    receivePort!.listen((serializedData) {
      final receivedAction = ReceivedAction().fromMap(serializedData);
      onActionReceivedMethodImpl(receivedAction);
    });

    // This initialization only happens on main isolate
    IsolateNameServer.registerPortWithName(receivePort!.sendPort, 'notification_action_port');
  }

  /// Use this method to detect when the user taps on a notification or action button
  @pragma("vm:entry-point")
  static Future<void> onActionReceivedMethod(ReceivedAction receivedAction) async {
    if (receivePort != null) {
      await onActionReceivedMethodImpl(receivedAction);
    } else {
      print(
        'onActionReceivedMethod was called inside a parallel dart isolate, where receivePort was never initialized.',
      );
      SendPort? sendPort = IsolateNameServer.lookupPortByName('notification_action_port');

      if (sendPort != null) {
        print('Redirecting the execution to main isolate process in listening...');
        dynamic serializedData = receivedAction.toMap();
        sendPort.send(serializedData);
      }
    }
  }

  static Future<void> onActionReceivedMethodImpl(ReceivedAction receivedAction) async {
    // A payloadless notification is still a tap. Returning early here would drop
    // it from the open count entirely, so pass an empty payload through and let
    // the handler emit the event and then no-op on routing (#12645).
    await _handleAppLinkOrDeepLink(receivedAction.payload ?? const <String, dynamic>{});
  }

  /// Public entry for FCM background/terminated notification taps (#5126).
  ///
  /// Takes the whole FCM `data` map rather than just the route: the tap event
  /// reads keys beyond `navigate_to` — notably `campaign_id` — and forwarding
  /// only the route dropped them before they reached analytics (#12645).
  static void handleFcmTap(Map<String, dynamic> data) {
    // Fire-and-forget: waits for navigator readiness before pushing (terminated cold start).
    unawaited(_handleAppLinkOrDeepLink(Map<String, dynamic>.from(data)));
  }

  /// Properties for the single `Notification Opened` event emitted per tap.
  ///
  /// Senders put `campaign_id` on the FCM `data` map, which reaches the client
  /// untouched, so an open can be tied back to the send that caused it. Keys
  /// absent from the payload are omitted rather than sent as null, so a query
  /// filtering on `campaign_id` sees only real campaign traffic (#12645).
  @visibleForTesting
  static Map<String, dynamic> notificationOpenedProperties(Map<String, dynamic> payload) {
    final properties = <String, dynamic>{};

    void put(String key, dynamic value) {
      if (value is String && value.isNotEmpty) {
        properties[key] = value;
      }
    }

    put('campaign_id', payload['campaign_id']);
    put('navigate_to', payload['navigate_to']);
    // Senders set one or the other; `notification_type` is the newer spelling.
    // `??` alone would keep an empty `notification_type` and lose a valid legacy
    // `type`, since an empty string is not null but is dropped by `put`.
    final notificationType = payload['notification_type'];
    final hasNotificationType = notificationType is String && notificationType.isNotEmpty;
    put('notification_type', hasNotificationType ? notificationType : payload['type']);
    return properties;
  }

  /// The external destination [navigateTo] addresses, or null for an in-app route.
  ///
  /// Campaign CTAs point at an absolute URL — the desktop download route carrying
  /// the campaign id — so that tap has to leave the app rather than be pushed onto
  /// the navigator as a route name, which lands on a dead route (#12645).
  ///
  /// Only http and https qualify. A notification payload is attacker-influenced
  /// input, and handing an arbitrary scheme to the platform launcher would let one
  /// address anything the OS knows how to open.
  @visibleForTesting
  static Uri? externalTargetFor(String navigateTo) {
    final uri = Uri.tryParse(navigateTo);
    if (uri == null || !uri.hasScheme || !uri.hasAuthority) return null;
    if (uri.scheme != 'http' && uri.scheme != 'https') return null;
    return uri;
  }

  /// Extract a chat/conversation deep-link from an FCM data map.
  /// Returns null when `navigate_to` is missing, empty, or not a String.
  static String? navigateToFromFcmData(Map<String, dynamic> data) {
    final navigateTo = data['navigate_to'];
    if (navigateTo is String && navigateTo.isNotEmpty) {
      return navigateTo;
    }
    return null;
  }

  /// Poll until [read] returns non-null, or [timeout] elapses.
  ///
  /// Used so terminated-state FCM taps (`getInitialMessage`) that resolve before
  /// `runApp` attach the navigator do not silently no-op (#5126; same class of
  /// race as app_links cold-start in `app_shell` / #4763).
  @visibleForTesting
  static Future<T?> waitUntilNonNull<T>(
    T? Function() read, {
    Duration timeout = const Duration(seconds: 15),
    Duration pollInterval = const Duration(milliseconds: 16),
  }) async {
    final existing = read();
    if (existing != null) return existing;

    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(pollInterval);
      final value = read();
      if (value != null) return value;
    }
    return null;
  }

  static Future<void> _handleAppLinkOrDeepLink(Map<String, dynamic> payload) async {
    WidgetsFlutterBinding.ensureInitialized();

    // Exactly one event per tap: both entry points — Awesome Notifications
    // actions and FCM background/terminated taps — funnel through here. Emitted
    // before the route check, so a push whose payload carries no `navigate_to`
    // is still counted; PostHog's `$push_notification_opened` is Android
    // autocapture only, so until now iOS opens were invisible (#12645).
    AnalyticsManager().track('Notification Opened', properties: notificationOpenedProperties(payload));

    final navigateTo = navigateToFromFcmData(payload);
    if (navigateTo == null) {
      Logger.debug('Navigate To is null');
      return;
    }

    // A campaign CTA points outside the app — the download route carrying the
    // campaign id. Handled before the navigator wait: an external target needs no
    // navigator, and waiting would stall the launch for up to 15s on a cold start.
    final externalTarget = externalTargetFor(navigateTo);
    if (externalTarget != null) {
      try {
        // launchUrl reports "no handler" by returning false, not by throwing, so
        // the result has to be checked or a CTA that never opened looks succeeded.
        final launched = await launchUrl(externalTarget, mode: LaunchMode.externalApplication);
        if (!launched) {
          Logger.debug('No handler opened external navigate_to=$navigateTo');
        }
      } catch (e) {
        Logger.debug('Failed to open external navigate_to=$navigateTo: $e');
      }
      return;
    }

    final navigator = await waitUntilNonNull(() => globalNavigatorKey.currentState);
    if (navigator == null) {
      Logger.debug('Navigator unavailable; dropping navigate_to=$navigateTo');
      return;
    }

    navigator.pushReplacement(
      MaterialPageRoute(builder: (context) => HomePageWrapper(navigateToRoute: navigateTo)),
    );
  }

  static Future<void> triggerFallNotification() async {
    final allowed = await AwesomeNotifications().isNotificationAllowed();
    if (!allowed) return;

    final ctx = globalNavigatorKey.currentContext;
    await AwesomeNotifications().createNotification(
      content: NotificationContent(
        id: 6,
        channelKey: 'channel',
        actionType: ActionType.Default,
        title: ctx?.l10n.fallNotificationTitle ?? 'Ouch',
        body: ctx?.l10n.fallNotificationBody ?? 'Did you fall?',
        wakeUpScreen: true,
      ),
    );
  }
}
