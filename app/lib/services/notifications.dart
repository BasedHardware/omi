// Re-export the main notification service for backward compatibility
// All notification functionality is now handled by the platform-aware service

import 'dart:isolate';
import 'dart:ui';

import 'package:awesome_notifications/awesome_notifications.dart';
import 'package:flutter/material.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/home/page.dart';

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
          'onActionReceivedMethod was called inside a parallel dart isolate, where receivePort was never initialized.');
      SendPort? sendPort = IsolateNameServer.lookupPortByName('notification_action_port');

      if (sendPort != null) {
        print('Redirecting the execution to main isolate process in listening...');
        dynamic serializedData = receivedAction.toMap();
        sendPort.send(serializedData);
      }
    }
  }

  static Future<void> onActionReceivedMethodImpl(ReceivedAction receivedAction) async {
    if (receivedAction.payload == null || receivedAction.payload!.isEmpty) {
      return;
    }
    _handleAppLinkOrDeepLink(receivedAction.payload!);
  }

  static void _handleAppLinkOrDeepLink(Map<String, dynamic> payload) async {
    // Always ensure that all plugins was initialized
    // TODO: for what?
    WidgetsFlutterBinding.ensureInitialized();

    String? navigateTo;
    if (payload.containsKey('navigate_to')) {
      navigateTo = payload['navigate_to'];
    }
    if (navigateTo == null) {
      debugPrint("Navigate To is null");
      return;
    }

    MyApp.navigatorKey.currentState
        ?.pushReplacement(MaterialPageRoute(builder: (context) => HomePageWrapper(navigateToRoute: navigateTo)));
  }
}
