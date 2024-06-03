// import 'dart:io';
// import 'dart:isolate';
//
// import 'package:flutter/material.dart';
// import 'package:flutter_foreground_task/flutter_foreground_task.dart';
//
// // The callback function should always be a top-level function.
// @pragma('vm:entry-point')
// void startCallback() {
//   print('startCallback');
//   // The setTaskHandler function must be called to handle the task in the background.
//   FlutterForegroundTask.setTaskHandler(FirstTaskHandler());
// }
//
// class FirstTaskHandler extends TaskHandler {
//   int _eventCount = 0;
//
//   @override
//   void onStart(DateTime timestamp, SendPort? sendPort) async {}
//
//   @override
//   void onRepeatEvent(DateTime timestamp, SendPort? sendPort) async {
//     debugPrint('FirstTaskHandler ~ onRepeatEvent: $_eventCount');
//     sendPort?.send(_eventCount); // send data to main isolate
//     _eventCount++;
//   }
//
//   // }
//
//   @override
//   void onDestroy(DateTime timestamp, SendPort? sendPort) async {}
// }
//
// class ForegroundUtil {
//   ReceivePort? _receivePort;
//
//   Future<void> requestPermissionForAndroid() async {
//     if (!Platform.isAndroid) {
//       return;
//     }
//     if (!await FlutterForegroundTask.canDrawOverlays) {
//       await FlutterForegroundTask.openSystemAlertWindowSettings();
//     }
//     if (!await FlutterForegroundTask.isIgnoringBatteryOptimizations) {
//       await FlutterForegroundTask.requestIgnoreBatteryOptimization();
//     }
//     final NotificationPermission notificationPermissionStatus =
//         await FlutterForegroundTask.checkNotificationPermission();
//     if (notificationPermissionStatus != NotificationPermission.granted) {
//       await FlutterForegroundTask.requestNotificationPermission();
//     }
//   }
//
//   void initForegroundTask() {
//     // if (await FlutterForegroundTask.isRunningService) return;
//     print('initForegroundTask');
//     FlutterForegroundTask.init(
//       androidNotificationOptions: AndroidNotificationOptions(
//         foregroundServiceType: AndroidForegroundServiceType.CONNECTED_DEVICE,
//         channelId: 'foreground_service',
//         channelName: 'Foreground Service Notification',
//         channelDescription: 'This notification appears when the foreground service is running.',
//         channelImportance: NotificationChannelImportance.LOW,
//         priority: NotificationPriority.HIGH,
//         iconData: const NotificationIconData(
//           resType: ResourceType.mipmap,
//           resPrefix: ResourcePrefix.ic,
//           name: 'launcher',
//         ),
//       ),
//       iosNotificationOptions: const IOSNotificationOptions(
//         showNotification: true,
//         playSound: false,
//       ),
//       foregroundTaskOptions: const ForegroundTaskOptions(
//         interval: 5000,
//         isOnceEvent: false,
//         autoRunOnBoot: false,
//         allowWakeLock: false,
//         allowWifiLock: false,
//       ),
//     );
//   }
//
//   Future<bool> startForegroundTask() async {
//     print('startForegroundTask');
//     // You can save data using the saveData function.
//     // await FlutterForegroundTask.saveData(key: 'customData', value: 'hello');
//
//     // Register the receivePort before starting the service.
//     final ReceivePort? receivePort = FlutterForegroundTask.receivePort;
//     final bool isRegistered = _registerReceivePort(receivePort);
//     if (!isRegistered) {
//       print('Failed to register receivePort!');
//       return false;
//     }
//
//     if (await FlutterForegroundTask.isRunningService) {
//       return FlutterForegroundTask.restartService();
//     } else {
//       return FlutterForegroundTask.startService(
//         notificationTitle: 'Your Friend Device is active',
//         notificationText: 'Tap to open the app',
//         callback: startCallback,
//       );
//     }
//   }
//
//   void stopForegroundTask() {
//     print('stopForegroundTask');
//     FlutterForegroundTask.stopService();
//   }
//
//   bool _registerReceivePort(ReceivePort? newReceivePort) {
//     if (newReceivePort == null) {
//       return false;
//     }
//
//     _closeReceivePort();
//
//     _receivePort = newReceivePort;
//     _receivePort?.listen((data) {
//       if (data is int) {
//         print('eventCount: $data');
//       } else if (data is String) {
//         // if (data == 'onNotificationPressed') {
//         //   Navigator.of(context).pushNamed('/resume-route');
//         // }
//       } else if (data is DateTime) {
//         print('timestamp: ${data.toString()}');
//       }
//     });
//
//     return _receivePort != null;
//   }
//
//   void _closeReceivePort() {
//     _receivePort?.close();
//     _receivePort = null;
//   }
//
//   _handleReceivePort() async {
//     if (await FlutterForegroundTask.isRunningService) {
//       final newReceivePort = FlutterForegroundTask.receivePort;
//       _registerReceivePort(newReceivePort);
//     }
//   }
// }
