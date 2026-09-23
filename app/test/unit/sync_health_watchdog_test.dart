import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sync_health_watchdog.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final watchdog = SyncHealthWatchdog.instance;

  Future<void> setupPreferences({
    String deviceId = 'omi-test-device-1',
    int lastSyncTimestamp = 0,
    int lastSyncAlertTimestamp = 0,
    bool syncAlertsEnabled = true,
  }) async {
    watchdog.resetForTesting();
    final deviceJson = jsonEncode(
      BtDevice(
        id: deviceId,
        name: 'Omi DevKit',
        type: DeviceType.omi,
        rssi: -55,
      ).toJson(),
    );

    SharedPreferences.setMockInitialValues({
      'btDevice': deviceId.isEmpty ? '' : deviceJson,
      'lastSyncTimestamp': lastSyncTimestamp,
      'lastSyncAlertTimestamp': lastSyncAlertTimestamp,
      'syncAlertsEnabled': syncAlertsEnabled,
    });
    await SharedPreferencesUtil.init();
  }

  group('SyncHealthWatchdog — evaluation gates & notifications (#15501)', () {
    test('returns noDevice when no device is paired', () async {
      await setupPreferences(deviceId: '');

      final evaluation = watchdog.evaluateSyncHealth();
      expect(evaluation.status, SyncHealthStatus.noDevice);
      expect(evaluation.isStalled, isFalse);
      expect(evaluation.alertDispatched, isFalse);
    });

    test('seeds lastSyncTimestamp on first run and returns healthy', () async {
      final now = DateTime.utc(2026, 9, 23, 14, 0); // 2:00 PM
      await setupPreferences(lastSyncTimestamp: 0);

      final evaluation = watchdog.evaluateSyncHealth(now: now);
      expect(evaluation.status, SyncHealthStatus.healthy);
      expect(evaluation.isStalled, isFalse);
      expect(evaluation.alertDispatched, isFalse);
      expect(SharedPreferencesUtil().lastSyncTimestamp, now.millisecondsSinceEpoch);
    });

    test('returns healthy when elapsed sync time is under 4 hours', () async {
      final now = DateTime.utc(2026, 9, 23, 14, 0);
      final twoHoursAgo = now.subtract(const Duration(hours: 2));
      await setupPreferences(lastSyncTimestamp: twoHoursAgo.millisecondsSinceEpoch);

      final evaluation = watchdog.evaluateSyncHealth(now: now);
      expect(evaluation.status, SyncHealthStatus.healthy);
      expect(evaluation.isStalled, isFalse);
      expect(evaluation.alertDispatched, isFalse);
      expect(evaluation.timeSinceLastSync, const Duration(hours: 2));
    });

    test('flags stalled and dispatches alert when elapsed exceeds 4 hours during daytime', () async {
      final now = DateTime(2026, 9, 23, 15, 30); // 3:30 PM (daytime)
      final fiveHoursAgo = now.subtract(const Duration(hours: 5));
      await setupPreferences(lastSyncTimestamp: fiveHoursAgo.millisecondsSinceEpoch);

      String? notifiedTitle;
      String? notifiedBody;
      int? notifiedId;
      Map<String, String?>? notifiedPayload;

      final evaluation = watchdog.evaluateSyncHealth(
        now: now,
        onTriggerNotification: ({
          required String title,
          required String body,
          int? notificationId,
          Map<String, String?>? payload,
        }) async {
          notifiedTitle = title;
          notifiedBody = body;
          notifiedId = notificationId;
          notifiedPayload = payload;
        },
      );

      expect(evaluation.status, SyncHealthStatus.stalled);
      expect(evaluation.isStalled, isTrue);
      expect(evaluation.alertDispatched, isTrue);
      expect(notifiedTitle, 'Omi Not Syncing');
      expect(notifiedBody, contains('5 hours'));
      expect(notifiedId, 15501);
      expect(notifiedPayload?['navigate_to'], '/home');
      expect(notifiedPayload?['type'], 'sync_stalled_alert');
      expect(SharedPreferencesUtil().lastSyncAlertTimestamp, now.millisecondsSinceEpoch);
    });

    test('enforces 6-hour alert cooldown', () async {
      final baseTime = DateTime(2026, 9, 23, 12, 0); // 12:00 PM
      final syncTime = baseTime.subtract(const Duration(hours: 5)); // synced at 7:00 AM
      await setupPreferences(
        lastSyncTimestamp: syncTime.millisecondsSinceEpoch,
        lastSyncAlertTimestamp: baseTime.millisecondsSinceEpoch, // alert already sent at 12:00 PM
      );

      bool notified = false;
      // Evaluate 2 hours later at 14:00 (2h < 6h cooldown)
      final evaluation1 = watchdog.evaluateSyncHealth(
        now: baseTime.add(const Duration(hours: 2)),
        onTriggerNotification: ({
          required String title,
          required String body,
          int? notificationId,
          Map<String, String?>? payload,
        }) async {
          notified = true;
        },
      );

      expect(evaluation1.status, SyncHealthStatus.stalled);
      expect(evaluation1.isStalled, isTrue);
      expect(evaluation1.alertDispatched, isFalse);
      expect(notified, isFalse);

      // Evaluate 6.5 hours later at 18:30 (past 6h cooldown)
      final evaluation2 = watchdog.evaluateSyncHealth(
        now: baseTime.add(const Duration(hours: 6, minutes: 30)),
        onTriggerNotification: ({
          required String title,
          required String body,
          int? notificationId,
          Map<String, String?>? payload,
        }) async {
          notified = true;
        },
      );

      expect(evaluation2.status, SyncHealthStatus.stalled);
      expect(evaluation2.isStalled, isTrue);
      expect(evaluation2.alertDispatched, isTrue);
      expect(notified, isTrue);
    });

    test('suppresses notification during quiet night hours (22:00 - 08:00)', () async {
      // 23:00 (11:00 PM) - quiet hours
      final nightTime = DateTime(2026, 9, 23, 23, 0);
      final sixHoursAgo = nightTime.subtract(const Duration(hours: 6));
      await setupPreferences(lastSyncTimestamp: sixHoursAgo.millisecondsSinceEpoch);

      bool notified = false;
      final evaluation = watchdog.evaluateSyncHealth(
        now: nightTime,
        onTriggerNotification: ({
          required String title,
          required String body,
          int? notificationId,
          Map<String, String?>? payload,
        }) async {
          notified = true;
        },
      );

      // Status is still stalled so in-app surfaces reflect state, but no audible/shade alert
      expect(evaluation.status, SyncHealthStatus.stalled);
      expect(evaluation.isStalled, isTrue);
      expect(evaluation.alertDispatched, isFalse);
      expect(notified, isFalse);
      // Alert timestamp not advanced so it will fire once quiet hours end
      expect(SharedPreferencesUtil().lastSyncAlertTimestamp, 0);
    });

    test('suppresses notification when user disabled sync alerts in settings', () async {
      final now = DateTime(2026, 9, 23, 14, 0);
      final fiveHoursAgo = now.subtract(const Duration(hours: 5));
      await setupPreferences(
        lastSyncTimestamp: fiveHoursAgo.millisecondsSinceEpoch,
        syncAlertsEnabled: false,
      );

      bool notified = false;
      final evaluation = watchdog.evaluateSyncHealth(
        now: now,
        onTriggerNotification: ({
          required String title,
          required String body,
          int? notificationId,
          Map<String, String?>? payload,
        }) async {
          notified = true;
        },
      );

      expect(evaluation.status, SyncHealthStatus.stalled);
      expect(evaluation.isStalled, isTrue);
      expect(evaluation.alertDispatched, isFalse);
      expect(notified, isFalse);
    });

    test('throttles recordSyncActivity in memory to avoid hammering disk', () async {
      final time1 = DateTime.utc(2026, 9, 23, 10, 0, 0);
      await setupPreferences(lastSyncTimestamp: time1.millisecondsSinceEpoch);

      // Call immediately at time1
      watchdog.recordSyncActivity(source: 'ble_audio', timestamp: time1);
      expect(SharedPreferencesUtil().lastSyncTimestamp, time1.millisecondsSinceEpoch);

      // Call 30 seconds later -> throttled
      final time2 = time1.add(const Duration(seconds: 30));
      watchdog.recordSyncActivity(source: 'ble_audio', timestamp: time2);
      expect(SharedPreferencesUtil().lastSyncTimestamp, time1.millisecondsSinceEpoch);

      // Call 70 seconds later -> persisted
      final time3 = time1.add(const Duration(seconds: 70));
      watchdog.recordSyncActivity(source: 'ble_audio', timestamp: time3);
      expect(SharedPreferencesUtil().lastSyncTimestamp, time3.millisecondsSinceEpoch);
    });

    test('timer lifecycle start and stop', () async {
      await setupPreferences();

      expect(watchdog.isRunning, isFalse);
      watchdog.startWatchdog(interval: const Duration(minutes: 15));
      expect(watchdog.isRunning, isTrue);
      watchdog.stopWatchdog();
      expect(watchdog.isRunning, isFalse);
    });
  });
}
