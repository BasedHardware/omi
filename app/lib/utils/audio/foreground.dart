import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:geolocator/geolocator.dart';

import 'package:omi/utils/logger.dart';
import 'package:omi/utils/notification_channel_strings.dart';

/// The service repeats every 5 minutes for the WAL sync wake. Location only
/// keeps the backend's 30-minute geolocation cache warm (a fallback for
/// conversations without their own snapshot), so a fix and its upload run at
/// most this often instead of on every repeat.
const Duration backgroundLocationRefreshInterval = Duration(minutes: 15);

@visibleForTesting
bool backgroundLocationRefreshDue(DateTime? lastAttempt, DateTime now) =>
    lastAttempt == null ||
    now.isBefore(lastAttempt) ||
    !now.isBefore(lastAttempt.add(backgroundLocationRefreshInterval));

/// The repeat handler's control flow. The sync wake always runs. Location
/// runs only when [backgroundLocationRefreshDue] is true, and the attempt
/// stamp is recorded before the refresh so a failed fix is not retried on
/// the next 5-minute repeat.
@visibleForTesting
Future<void> runBackgroundRepeat({
  required DateTime? lastAttempt,
  required DateTime now,
  required void Function() sendSyncWake,
  required void Function(DateTime attemptAt) recordAttempt,
  required Future<void> Function() refreshLocation,
}) async {
  sendSyncWake();
  if (!backgroundLocationRefreshDue(lastAttempt, now)) return;
  recordAttempt(now);
  await refreshLocation();
}

/// Owns the attempt stamp the production repeat handler passes in.
/// A caller that passes null instead of [attemptAt] refreshes every repeat.
@visibleForTesting
class BackgroundLocationCadence {
  DateTime? attemptAt;

  void recordStart(DateTime now) {
    attemptAt = now;
  }

  Future<void> onRepeat({
    required DateTime now,
    required void Function() sendSyncWake,
    required Future<void> Function() refreshLocation,
  }) {
    return runBackgroundRepeat(
      lastAttempt: attemptAt,
      now: now,
      sendSyncWake: sendSyncWake,
      recordAttempt: (stamp) => attemptAt = stamp,
      refreshLocation: refreshLocation,
    );
  }
}

@pragma('vm:entry-point')
void _startForegroundCallback() {
  FlutterForegroundTask.setTaskHandler(_ForegroundFirstTaskHandler());
}

class _ForegroundFirstTaskHandler extends TaskHandler {
  DateTime? _locationUpdatedAt;
  final _locationCadence = BackgroundLocationCadence();

  static const Duration _lastKnownMaxAge = Duration(minutes: 5);

  bool _isLastKnownFresh(Position position) {
    final age = DateTime.now().toUtc().difference(position.timestamp.toUtc());
    return !age.isNegative && age <= _lastKnownMaxAge;
  }

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter taskStarter) async {
    Logger.debug("Starting foreground task");
    _locationCadence.recordStart(DateTime.now());
    _locationInBackground();
  }

  Future _locationInBackground() async {
    // Periodic refresh from FOREGROUND_SERVICE_LOCATION. while-in-use is
    // enough; do not request ACCESS_BACKGROUND_LOCATION (Play Store
    // prominent-disclosure). This isolate has no Activity, so it never prompts.
    if (await Geolocator.isLocationServiceEnabled()) {
      final permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.always || permission == LocationPermission.whileInUse) {
        Position? lastKnown;
        try {
          lastKnown = await Geolocator.getLastKnownPosition() ??
              await Geolocator.getLastKnownPosition(forceAndroidLocationManager: true);
        } catch (_) {}
        late final Position locationData;
        if (lastKnown != null && _isLastKnownFresh(lastKnown)) {
          locationData = lastKnown;
        } else {
          try {
            locationData = await Geolocator.getCurrentPosition(
              locationSettings: const LocationSettings(accuracy: LocationAccuracy.medium),
            ).timeout(const Duration(seconds: 8));
          } catch (e) {
            if (lastKnown == null) {
              Object loc = {'error': 'Location fix failed: $e'};
              FlutterForegroundTask.sendDataToMain(loc);
              return;
            }
            locationData = lastKnown;
          }
        }
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
        Object loc = {'error': 'Location permission is not granted'};
        FlutterForegroundTask.sendDataToMain(loc);
      }
    } else {
      Object loc = {'error': 'Location service is not enabled'};
      FlutterForegroundTask.sendDataToMain(loc);
    }
  }

  @override
  void onReceiveData(Object data) async {
    Logger.debug('onReceiveData: $data');
    await _locationInBackground();
  }

  @override
  void onRepeatEvent(DateTime timestamp) async {
    Logger.debug("Foreground repeat event triggered");
    // The main isolate owns WAL state. A fresh headless capture engine must
    // never be booted for this opportunistic recovery pass.
    final now = DateTime.now();
    await _locationCadence.onRepeat(
      now: now,
      sendSyncWake: () {
        FlutterForegroundTask.sendDataToMain({'recordingSyncWake': true});
      },
      refreshLocation: _locationInBackground,
    );
  }

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {
    Logger.debug("Destroying foreground task");
    FlutterForegroundTask.stopService();
  }
}

class ForegroundUtil {
  static bool _isInitialized = false;
  static bool _isStarting = false;

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
    if (_isInitialized) {
      Logger.debug('ForegroundService already initialized, skipping');
      return;
    }

    if (await FlutterForegroundTask.isRunningService) {
      _isInitialized = true;
      return;
    }

    Logger.debug('initializeForegroundService');

    try {
      await NotificationChannelStrings.loadAppLocale();
      FlutterForegroundTask.init(
        androidNotificationOptions: AndroidNotificationOptions(
          channelId: 'foreground_service',
          channelName: NotificationChannelStrings.foregroundServiceChannelName,
          channelDescription: NotificationChannelStrings.foregroundServiceChannelDescription,
          channelImportance: NotificationChannelImportance.LOW,
          priority: NotificationPriority.HIGH,
          // iconData: const NotificationIconData(
          //   resType: ResourceType.mipmap,
          //   resPrefix: ResourcePrefix.ic,
          //   name: 'launcher',
          // ),
        ),
        iosNotificationOptions: const IOSNotificationOptions(showNotification: false, playSound: false),
        foregroundTaskOptions: ForegroundTaskOptions(
          // Warn: 5m, for location tracking. If we want to support other services, we use the differenct interval,
          // such as 1m + self-validation in each service.
          eventAction: ForegroundTaskEventAction.repeat(60 * 1000 * 5),
          autoRunOnBoot: false,
          allowWakeLock: false,
          allowWifiLock: false,
        ),
      );
      _isInitialized = true;
      Logger.debug('ForegroundService initialized successfully');
    } catch (e) {
      Logger.debug('ForegroundService initialization failed: $e');
      _isInitialized = false;
    }
  }

  static Future<ServiceRequestResult> startForegroundTask() async {
    if (_isStarting) {
      Logger.debug('ForegroundTask already starting, skipping');
      return const ServiceRequestSuccess();
    }

    _isStarting = true;
    Logger.debug('startForegroundTask');

    try {
      // restartService() calls startForegroundService() again. A stop that
      // lands before the new startForeground() crashes Android 14+ with
      // ForegroundServiceDidNotStartInTimeException. An already-running
      // service has already promoted; leave it alone.
      if (await FlutterForegroundTask.isRunningService) {
        Logger.debug('ForegroundTask already running');
        return const ServiceRequestSuccess();
      }
      final ServiceRequestResult result = await FlutterForegroundTask.startService(
        // Explicit location. The manifest also lists shortService as the
        // timeout fallback; omitting serviceTypes makes the plugin pass
        // FOREGROUND_SERVICE_TYPE_MANIFEST and adopt both, which imposes
        // the 3-minute shortService limit on this task.
        serviceTypes: const [ForegroundServiceTypes.location],
        notificationTitle: 'Your Omi Device is connected.',
        notificationText: 'Transcription service is running in the background.',
        callback: _startForegroundCallback,
      );
      Logger.debug('ForegroundTask started successfully');
      return result;
    } catch (e) {
      Logger.debug('ForegroundTask start failed: $e');
      return ServiceRequestFailure(error: e.toString());
    } finally {
      _isStarting = false;
    }
  }

  static Future<void> stopForegroundTask() async {
    Logger.debug('stopForegroundTask');

    try {
      if (await FlutterForegroundTask.isRunningService) {
        await FlutterForegroundTask.stopService();
        _isInitialized = false;
      }
    } catch (e) {
      Logger.debug('ForegroundTask stop failed: $e');
    }
  }
}
