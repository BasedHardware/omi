import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:geolocator/geolocator.dart';

@pragma('vm:entry-point')
void _startForegroundCallback() {
  FlutterForegroundTask.setTaskHandler(_ForegroundFirstTaskHandler());
}

class _ForegroundFirstTaskHandler extends TaskHandler {
  DateTime? _locationUpdatedAt;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter taskStarter) async {
    debugPrint("Starting foreground task");
    _locationInBackground();
  }

  Future _locationInBackground() async {
    if (await Geolocator.isLocationServiceEnabled()) {
      if (await Geolocator.checkPermission() == LocationPermission.always) {
        var locationData = await Geolocator.getCurrentPosition();
        if (_locationUpdatedAt == null ||
            _locationUpdatedAt!.isBefore(DateTime.now().subtract(const Duration(minutes: 5)))) {
          Object loc = {
            "latitude": locationData.latitude,
            "longitude": locationData.longitude,
            'altitude': locationData.altitude,
            'accuracy': locationData.accuracy,
            'time': locationData.timestamp.toUtc().toIso8601String(),
          };
          FlutterForegroundTask.sendDataToMain(loc);
          _locationUpdatedAt = DateTime.now();
        }
      } else {
        Object loc = {'error': 'Always location permission is not granted'};
        FlutterForegroundTask.sendDataToMain(loc);
      }
    } else {
      Object loc = {'error': 'Location service is not enabled'};
      FlutterForegroundTask.sendDataToMain(loc);
    }
  }

  @override
  void onReceiveData(Object data) async {
    debugPrint('onReceiveData: $data');
    await _locationInBackground();
  }

  @override
  void onRepeatEvent(DateTime timestamp) async {
    debugPrint("Foreground repeat event triggered");
    await _locationInBackground();
  }

  @override
  Future<void> onDestroy(DateTime timestamp) async {
    debugPrint("Destroying foreground task");
    FlutterForegroundTask.stopService();
  }
}

class ForegroundUtil {
  static Future<void> requestPermissions() async {
    // Android 13+, you need to allow notification permission to display foreground service notification.
    //
    // iOS: If you need notification, ask for permission.
    final NotificationPermission notificationPermissionStatus =
        await FlutterForegroundTask.checkNotificationPermission();
    if (notificationPermissionStatus != NotificationPermission.granted) {
      await FlutterForegroundTask.requestNotificationPermission();
    }

    if (Platform.isAndroid) {
      // if (!await FlutterForegroundTask.canDrawOverlays) {
      //   await FlutterForegroundTask.openSystemAlertWindowSettings();
      // }
      if (!await FlutterForegroundTask.isIgnoringBatteryOptimizations) {
        await FlutterForegroundTask.requestIgnoreBatteryOptimization();
      }
    }
  }

  Future<bool> get isIgnoringBatteryOptimizations async => await FlutterForegroundTask.isIgnoringBatteryOptimizations;

  static Future<void> initializeForegroundService() async {
    if (await FlutterForegroundTask.isRunningService) return;
    debugPrint('initializeForegroundService');
    // await Location().requestPermission();
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'foreground_service',
        channelName: 'Foreground Service Notification',
        channelDescription: 'Transcription service is running in the background.',
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.HIGH,
        // iconData: const NotificationIconData(
        //   resType: ResourceType.mipmap,
        //   resPrefix: ResourcePrefix.ic,
        //   name: 'launcher',
        // ),
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
        playSound: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        // Warn: 5m, for location tracking. If we want to support other services, we use the differenct interval,
        // such as 1m + self-validation in each service.
        eventAction: ForegroundTaskEventAction.repeat(60 * 1000 * 5),
        autoRunOnBoot: false,
        allowWakeLock: true,
        allowWifiLock: true,
      ),
    );
  }

  static Future<ServiceRequestResult> startForegroundTask() async {
    debugPrint('startForegroundTask');
    if (await FlutterForegroundTask.isRunningService) {
      return FlutterForegroundTask.restartService();
    } else {
      return await FlutterForegroundTask.startService(
        notificationTitle: 'Your Friend Device is connected.',
        notificationText: 'Transcription service is running in the background.',
        callback: _startForegroundCallback,
      );
    }
  }

  static Future<void> stopForegroundTask() async {
    debugPrint('stopForegroundTask');
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }
}
