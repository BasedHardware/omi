import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sync_health_watchdog.dart';

/// The sync health watchdog (#15501): a full day of silence across every
/// activity signal raises one local notification, at most once a day, never
/// at night, and never for a device type whose sync cadence it does not own.

typedef AlertSink = Future<void> Function({
  required String title,
  required String body,
  int? notificationId,
  Map<String, String?>? payload,
});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late DateTime now;
  late List<({String title, String body, int? id, Map<String, String?>? payload})> alerts;
  late List<SyncHealthEvaluation> evaluations;

  AlertSink sink() => ({required title, required body, notificationId, payload}) async {
        alerts.add((title: title, body: body, id: notificationId, payload: payload));
      };

  SyncHealthWatchdog makeWatchdog() => SyncHealthWatchdog.forTesting(now: () => now);

  Future<void> setupPreferences({
    DeviceType deviceType = DeviceType.omi,
    String deviceId = 'omi-test-device-1',
    int lastSyncTimestamp = 0,
    int lastSyncAlertTimestamp = 0,
    bool syncAlertsEnabled = true,
  }) async {
    final deviceJson = deviceId.isEmpty
        ? ''
        : jsonEncode(
            BtDevice(id: deviceId, name: 'Omi DevKit', type: deviceType, rssi: -55).toJson(),
          );
    SharedPreferences.setMockInitialValues({
      'btDevice': deviceJson,
      'lastSyncTimestamp': lastSyncTimestamp,
      'lastSyncAlertTimestamp': lastSyncAlertTimestamp,
      'syncAlertsEnabled': syncAlertsEnabled,
    });
    await SharedPreferencesUtil.init();
  }

  setUp(() {
    // A weekday noon, safely outside quiet hours (22:00–08:00).
    now = DateTime(2026, 9, 23, 12, 0);
    alerts = [];
    evaluations = [];
  });

  group('device gating', () {
    test('no paired device means no verdict and no alert', () async {
      await setupPreferences(deviceId: '');
      final watchdog = makeWatchdog();
      watchdog.onEvaluation = evaluations.add;

      final evaluation = watchdog.evaluateSyncHealth(onTriggerNotification: sink());

      expect(evaluation.status, SyncHealthStatus.noDevice);
      expect(evaluation.isStalled, isFalse);
      expect(evaluation.alertDispatched, isFalse);
      expect(alerts, isEmpty);
      expect(evaluations.single.status, SyncHealthStatus.noDevice);
    });

    test('a non-pendant device type is not under the watchdog contract', () async {
      await setupPreferences(deviceType: DeviceType.raybanMeta);
      final watchdog = makeWatchdog();

      final evaluation = watchdog.evaluateSyncHealth(onTriggerNotification: sink());

      expect(evaluation.status, SyncHealthStatus.noDevice);
      expect(alerts, isEmpty);
    });

    test('a friend pendant is under the watchdog contract', () async {
      final pairedSince = now.subtract(const Duration(hours: 30));
      await setupPreferences(
          deviceType: DeviceType.friendPendant, lastSyncTimestamp: pairedSince.millisecondsSinceEpoch);
      final watchdog = makeWatchdog();

      final evaluation = watchdog.evaluateSyncHealth(onTriggerNotification: sink());

      expect(evaluation.status, SyncHealthStatus.stalled);
    });
  });

  group('stall evaluation', () {
    test('first run seeds the silence clock and reads healthy', () async {
      await setupPreferences(lastSyncTimestamp: 0);
      final watchdog = makeWatchdog();

      final evaluation = watchdog.evaluateSyncHealth(onTriggerNotification: sink());

      expect(evaluation.status, SyncHealthStatus.healthy);
      expect(evaluation.timeSinceLastSync, Duration.zero);
      expect(SharedPreferencesUtil().lastSyncTimestamp, now.millisecondsSinceEpoch);
      expect(alerts, isEmpty);
    });

    test('an overnight-charge-length gap stays healthy under the 24h threshold', () async {
      // The threshold must clear the longest normal daily gap: a pendant
      // taken off in the evening and charged overnight (~12h silent).
      final lastActivity = now.subtract(const Duration(hours: 12));
      await setupPreferences(lastSyncTimestamp: lastActivity.millisecondsSinceEpoch);
      final watchdog = makeWatchdog();

      final evaluation = watchdog.evaluateSyncHealth(onTriggerNotification: sink());

      expect(evaluation.status, SyncHealthStatus.healthy);
      expect(evaluation.isStalled, isFalse);
      expect(alerts, isEmpty);
    });

    test('a full day of silence declares the stall and dispatches the alert', () async {
      final lastActivity = now.subtract(const Duration(hours: 26));
      await setupPreferences(lastSyncTimestamp: lastActivity.millisecondsSinceEpoch);
      final watchdog = makeWatchdog();

      final evaluation = watchdog.evaluateSyncHealth(onTriggerNotification: sink());

      expect(evaluation.status, SyncHealthStatus.stalled);
      expect(evaluation.timeSinceLastSync, const Duration(hours: 26));
      expect(evaluation.alertDispatched, isTrue);
      expect(alerts, hasLength(1));
      expect(alerts.single.id, SyncHealthWatchdog.syncStallNotificationId);
      expect(alerts.single.payload?['navigate_to'], '/settings/device');
      expect(alerts.single.payload?['type'], SyncHealthWatchdog.syncStallAlertType);
      expect(alerts.single.body, contains('26 hours'));
      expect(SharedPreferencesUtil().lastSyncAlertTimestamp, now.millisecondsSinceEpoch);
    });

    test('the daily alert cooldown holds while the stall persists', () async {
      final lastActivity = now.subtract(const Duration(hours: 30));
      await setupPreferences(
        lastSyncTimestamp: lastActivity.millisecondsSinceEpoch,
        lastSyncAlertTimestamp: now.millisecondsSinceEpoch, // alerted moments ago
      );
      final watchdog = makeWatchdog();

      final withinCooldown = watchdog.evaluateSyncHealth(onTriggerNotification: sink());
      expect(withinCooldown.status, SyncHealthStatus.stalled);
      expect(withinCooldown.alertDispatched, isFalse, reason: 'one reminder per day, not per evaluation');
      expect(alerts, isEmpty);

      now = now.add(const Duration(hours: 24, minutes: 1));
      final pastCooldown = watchdog.evaluateSyncHealth(onTriggerNotification: sink());
      expect(pastCooldown.status, SyncHealthStatus.stalled);
      expect(pastCooldown.alertDispatched, isTrue);
      expect(alerts, hasLength(1));
    });

    test('quiet hours suppress the alert without spending the cooldown', () async {
      now = DateTime(2026, 9, 23, 23, 0); // 11 PM
      final lastActivity = now.subtract(const Duration(hours: 26));
      await setupPreferences(lastSyncTimestamp: lastActivity.millisecondsSinceEpoch);
      final watchdog = makeWatchdog();

      final evaluation = watchdog.evaluateSyncHealth(onTriggerNotification: sink());

      expect(evaluation.status, SyncHealthStatus.stalled, reason: 'the in-app row still shows the state');
      expect(evaluation.alertDispatched, isFalse);
      expect(alerts, isEmpty);
      expect(SharedPreferencesUtil().lastSyncAlertTimestamp, 0, reason: 'fires once quiet hours end');
    });

    test('the settings toggle silences the alert but not the verdict', () async {
      final lastActivity = now.subtract(const Duration(hours: 26));
      await setupPreferences(
        lastSyncTimestamp: lastActivity.millisecondsSinceEpoch,
        syncAlertsEnabled: false,
      );
      final watchdog = makeWatchdog();

      final evaluation = watchdog.evaluateSyncHealth(onTriggerNotification: sink());

      expect(evaluation.status, SyncHealthStatus.stalled);
      expect(evaluation.alertDispatched, isFalse);
      expect(alerts, isEmpty);
    });
  });

  group('activity recording', () {
    test('throttles to one persist per minute and never rewinds the clock', () async {
      await setupPreferences(lastSyncTimestamp: 0);
      final watchdog = makeWatchdog();

      watchdog.recordSyncActivity(source: 'ble_audio', timestamp: now);
      expect(SharedPreferencesUtil().lastSyncTimestamp, now.millisecondsSinceEpoch);

      final thirtySecondsLater = now.add(const Duration(seconds: 30));
      watchdog.recordSyncActivity(source: 'ble_audio', timestamp: thirtySecondsLater);
      expect(SharedPreferencesUtil().lastSyncTimestamp, now.millisecondsSinceEpoch);

      final staleSource = now.subtract(const Duration(minutes: 5));
      watchdog.recordSyncActivity(source: 'late_frame', timestamp: staleSource);
      expect(SharedPreferencesUtil().lastSyncTimestamp, now.millisecondsSinceEpoch,
          reason: 'a stale source cannot rewind the clock');

      final aMinuteLater = now.add(const Duration(seconds: 70));
      watchdog.recordSyncActivity(source: 'wal_synced', timestamp: aMinuteLater);
      expect(SharedPreferencesUtil().lastSyncTimestamp, aMinuteLater.millisecondsSinceEpoch);
    });

    test('recorded activity clears an existing stall on the next evaluation', () async {
      final lastActivity = now.subtract(const Duration(hours: 26));
      await setupPreferences(lastSyncTimestamp: lastActivity.millisecondsSinceEpoch);
      final watchdog = makeWatchdog();
      expect(watchdog.evaluateSyncHealth(onTriggerNotification: sink()).isStalled, isTrue);

      watchdog.recordSyncActivity(source: 'device_connected', timestamp: now.add(const Duration(minutes: 2)));
      final evaluation = watchdog.evaluateSyncHealth(onTriggerNotification: sink());
      expect(evaluation.status, SyncHealthStatus.healthy);
    });
  });

  group('timer lifecycle', () {
    test('start begins the periodic loop and stop ends it', () async {
      await setupPreferences(deviceId: '');
      final watchdog = SyncHealthWatchdog.instance;
      watchdog.resetForTesting();
      addTearDown(watchdog.resetForTesting);

      expect(watchdog.isRunning, isFalse);
      watchdog.startWatchdog(interval: const Duration(minutes: 15));
      expect(watchdog.isRunning, isTrue);
      watchdog.stopWatchdog();
      expect(watchdog.isRunning, isFalse);
    });
  });
}
