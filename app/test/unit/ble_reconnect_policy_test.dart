import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices/ble_reconnect_policy.dart';

void main() {
  group('bleReconnectDelayMs', () {
    test('first reconnect is a parked connect with no delay', () {
      expect(
        bleReconnectDelayMs(attempt: 0, isBackground: true, isTimeoutOrFailToConnect: true),
        0,
      );
    });

    test('inactive and background are both backgrounded for backoff', () {
      expect(isBleReconnectBackgrounded(isActive: true), isFalse);
      expect(isBleReconnectBackgrounded(isActive: false), isTrue);
    });

    test('overdue delayed reconnects fire after a CoreBluetooth wake', () {
      final scheduledAt = DateTime.utc(2026, 8, 14, 12);
      expect(
        isBleReconnectDelayElapsed(
          scheduledAt: scheduledAt,
          delayMs: 2000,
          now: scheduledAt.add(const Duration(milliseconds: 1999)),
        ),
        isFalse,
      );
      expect(
        isBleReconnectDelayElapsed(
          scheduledAt: scheduledAt,
          delayMs: 2000,
          now: scheduledAt.add(const Duration(milliseconds: 2000)),
        ),
        isTrue,
      );
    });

    test('foreground never backs off', () {
      for (final attempt in [1, 2, 8]) {
        expect(
          bleReconnectDelayMs(attempt: attempt, isBackground: false, isTimeoutOrFailToConnect: true),
          0,
          reason: 'attempt $attempt',
        );
      }
    });

    test('non-timeout disconnects stay immediate even in background', () {
      expect(
        bleReconnectDelayMs(attempt: 3, isBackground: true, isTimeoutOrFailToConnect: false),
        0,
      );
    });

    test('background timeout/fail uses 200ms → 2s → 10s → 30s then cap 60s', () {
      expect(bleReconnectDelayMs(attempt: 1, isBackground: true, isTimeoutOrFailToConnect: true), 200);
      expect(bleReconnectDelayMs(attempt: 2, isBackground: true, isTimeoutOrFailToConnect: true), 2000);
      expect(bleReconnectDelayMs(attempt: 3, isBackground: true, isTimeoutOrFailToConnect: true), 10000);
      expect(bleReconnectDelayMs(attempt: 4, isBackground: true, isTimeoutOrFailToConnect: true), 30000);
      expect(bleReconnectDelayMs(attempt: 5, isBackground: true, isTimeoutOrFailToConnect: true), 60000);
      expect(bleReconnectDelayMs(attempt: 9, isBackground: true, isTimeoutOrFailToConnect: true), 60000);
    });
  });

  group('shouldPersistBleBatteryReading', () {
    final t0 = DateTime.utc(2026, 8, 14, 12);

    test('persists the first sample', () {
      expect(
        shouldPersistBleBatteryReading(
          previousLevel: null,
          lastPersistedAt: null,
          newLevel: 87,
          now: t0,
        ),
        isTrue,
      );
    });

    test('skips a 1% change inside 15 minutes', () {
      expect(
        shouldPersistBleBatteryReading(
          previousLevel: 87,
          lastPersistedAt: t0,
          newLevel: 86,
          now: t0.add(const Duration(minutes: 5)),
        ),
        isFalse,
      );
    });

    test('persists a 5% change', () {
      expect(
        shouldPersistBleBatteryReading(
          previousLevel: 87,
          lastPersistedAt: t0,
          newLevel: 82,
          now: t0.add(const Duration(seconds: 5)),
        ),
        isTrue,
      );
    });

    test('persists after 15 minutes even with no change', () {
      expect(
        shouldPersistBleBatteryReading(
          previousLevel: 50,
          lastPersistedAt: t0,
          newLevel: 50,
          now: t0.add(const Duration(minutes: 15)),
        ),
        isTrue,
      );
    });

    test('persists crossing the 20% threshold in both directions', () {
      expect(
        shouldPersistBleBatteryReading(
          previousLevel: 21,
          lastPersistedAt: t0,
          newLevel: 19,
          now: t0.add(const Duration(seconds: 1)),
        ),
        isTrue,
      );
      expect(
        shouldPersistBleBatteryReading(
          previousLevel: 19,
          lastPersistedAt: t0,
          newLevel: 20,
          now: t0.add(const Duration(seconds: 1)),
        ),
        isTrue,
      );
    });
  });
}
