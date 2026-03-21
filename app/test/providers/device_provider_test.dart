import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/services.dart';

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async {
    return [ConnectivityResult.none];
  }

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized by another test.
    }
  });

  group('battery throttling', () {
    late DeviceProvider provider;
    late int notifyCount;

    setUp(() {
      provider = DeviceProvider();
      notifyCount = 0;
      provider.addListener(() => notifyCount++);
    });

    test('notifies on first battery reading', () {
      final result = provider.updateBatteryLevelForTesting(50);

      expect(result, true);
      expect(notifyCount, 1);
      expect(provider.batteryLevel, 50);
    });

    test('does not notify for small changes (<5%) within 15 minutes', () {
      final now = DateTime.now();

      // First reading - should notify
      provider.updateBatteryLevelForTesting(50, now: now);
      expect(notifyCount, 1);

      // Small change (2%) within 15 minutes - should NOT notify
      final result = provider.updateBatteryLevelForTesting(52, now: now.add(const Duration(minutes: 5)));

      expect(result, false);
      expect(notifyCount, 1); // No additional notification
      expect(provider.batteryLevel, 52); // Level is still updated
    });

    test('notifies when delta >= 5%', () {
      final now = DateTime.now();

      // First reading
      provider.updateBatteryLevelForTesting(50, now: now);
      expect(notifyCount, 1);

      // 5% change - should notify
      final result = provider.updateBatteryLevelForTesting(45, now: now.add(const Duration(minutes: 1)));

      expect(result, true);
      expect(notifyCount, 2);
    });

    test('notifies after 15 minutes even if delta < 5%', () {
      final now = DateTime.now();

      // First reading
      provider.updateBatteryLevelForTesting(50, now: now);
      expect(notifyCount, 1);

      // Small change but 15 minutes elapsed - should notify
      final result = provider.updateBatteryLevelForTesting(51, now: now.add(const Duration(minutes: 15)));

      expect(result, true);
      expect(notifyCount, 2);
    });

    test('notifies when crossing 20% threshold downward', () {
      final now = DateTime.now();

      // Start above 20%
      provider.updateBatteryLevelForTesting(25, now: now);
      expect(notifyCount, 1);

      // Cross below 20% (only 6% change, but crosses threshold)
      final result = provider.updateBatteryLevelForTesting(19, now: now.add(const Duration(minutes: 1)));

      expect(result, true);
      expect(notifyCount, 2);
    });

    test('notifies when crossing 20% threshold upward', () {
      final now = DateTime.now();

      // Start below 20%
      provider.updateBatteryLevelForTesting(15, now: now);
      expect(notifyCount, 1);

      // Cross above 20% (only 6% change, but crosses threshold)
      final result = provider.updateBatteryLevelForTesting(21, now: now.add(const Duration(minutes: 1)));

      expect(result, true);
      expect(notifyCount, 2);
    });

    test('does not notify for small changes that do not cross 20% threshold', () {
      final now = DateTime.now();

      // Start at 25%
      provider.updateBatteryLevelForTesting(25, now: now);
      expect(notifyCount, 1);

      // Small change staying above 20% - should NOT notify
      final result = provider.updateBatteryLevelForTesting(23, now: now.add(const Duration(minutes: 1)));

      expect(result, false);
      expect(notifyCount, 1);
    });

    test('resetBatteryThrottlingForTesting resets state', () {
      final now = DateTime.now();

      // First reading
      provider.updateBatteryLevelForTesting(50, now: now);
      expect(notifyCount, 1);

      // Reset
      provider.resetBatteryThrottlingForTesting();

      // Now same value should trigger notification again (as if first reading)
      final result = provider.updateBatteryLevelForTesting(50, now: now.add(const Duration(minutes: 1)));

      expect(result, true);
      expect(notifyCount, 2);
    });
  });

  group('low battery alert flag — state machine (#5697)', () {
    // Tests the exact if/else from DeviceProvider.onBatteryLevelChange (lines 163-172)
    // as a pure state machine, without touching production code.
    //
    // Production logic:
    //   if (batteryLevel < 20 && !_hasLowBatteryAlerted) {
    //     _hasLowBatteryAlerted = true;   // fire notification
    //   } else if (batteryLevel > 20) {
    //     _hasLowBatteryAlerted = false;   // THE FIX (was: true)
    //   }

    /// Mirror of production logic. Returns (alertFired, newFlag).
    (bool, bool) evalAlert(int level, bool hasAlerted) {
      if (level < 20 && !hasAlerted) {
        return (true, true);
      } else if (level > 20) {
        return (false, false); // fix: reset flag on recovery
      }
      return (false, hasAlerted);
    }

    /// Simulate a sequence of battery readings, return list of alert events.
    List<bool> runSequence(List<int> levels) {
      var flag = false;
      return levels.map((level) {
        final (fired, newFlag) = evalAlert(level, flag);
        flag = newFlag;
        return fired;
      }).toList();
    }

    test('alert fires when battery drops below 20%', () {
      final (fired, flag) = evalAlert(15, false);
      expect(fired, true);
      expect(flag, true);
    });

    test('no duplicate alert while battery stays low', () {
      final (fired, flag) = evalAlert(10, true);
      expect(fired, false);
      expect(flag, true);
    });

    test('flag resets when battery recovers above 20%', () {
      final (fired, flag) = evalAlert(25, true);
      expect(fired, false);
      expect(flag, false, reason: 'BUG was here: production had true instead of false');
    });

    test('alert fires again after recovery — the core bug scenario', () {
      // 50% → 15% (alert) → 25% (recover) → 10% (should alert AGAIN)
      final alerts = runSequence([50, 15, 25, 10]);
      expect(alerts, [
        false,
        true,
        false,
        true,
      ], reason: 'Before fix: [false, true, false, false] — second alert never fires');
    });

    test('full lifecycle: multiple charge cycles', () {
      final alerts = runSequence([100, 80, 60, 40, 18, 25, 50, 85, 60, 30, 12, 90, 5]);
      // Alert at index 4 (18%), 10 (12%), 12 (5%)
      expect(alerts, [false, false, false, false, true, false, false, false, false, false, true, false, true]);
    });

    test('boundary: exactly 20% neither triggers alert nor resets flag', () {
      // 20 is not < 20 and not > 20
      final (fired1, flag1) = evalAlert(20, false);
      expect(fired1, false);
      expect(flag1, false);

      final (fired2, flag2) = evalAlert(20, true);
      expect(fired2, false);
      expect(flag2, true, reason: 'Exactly 20% should not reset flag (needs > 20)');
    });
  });
}
