import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/ble_connect_retry.dart';

void main() {
  group('nextBleConnectRetryDelay (#6610)', () {
    test('uses escalating backoff then caps at 60s', () {
      expect(nextBleConnectRetryDelay(0), const Duration(seconds: 2));
      expect(nextBleConnectRetryDelay(1), const Duration(seconds: 5));
      expect(nextBleConnectRetryDelay(2), const Duration(seconds: 10));
      expect(nextBleConnectRetryDelay(3), const Duration(seconds: 30));
      expect(nextBleConnectRetryDelay(4), const Duration(seconds: 60));
      expect(nextBleConnectRetryDelay(9), const Duration(seconds: 60));
    });
  });

  group('shouldScheduleBleConnectRetry (#6610)', () {
    test('schedules after connecting → timeout → disconnected when paired', () {
      expect(
        shouldScheduleBleConnectRetry(
          serviceReady: true,
          hasPairedDevice: true,
          userDisconnected: false,
          alreadyConnected: false,
          retryAlreadyScheduled: false,
        ),
        isTrue,
      );
    });

    test('does not schedule when user disconnected, already connected, or unpaired', () {
      expect(
        shouldScheduleBleConnectRetry(
          serviceReady: true,
          hasPairedDevice: true,
          userDisconnected: true,
          alreadyConnected: false,
          retryAlreadyScheduled: false,
        ),
        isFalse,
      );
      expect(
        shouldScheduleBleConnectRetry(
          serviceReady: true,
          hasPairedDevice: true,
          userDisconnected: false,
          alreadyConnected: true,
          retryAlreadyScheduled: false,
        ),
        isFalse,
      );
      expect(
        shouldScheduleBleConnectRetry(
          serviceReady: true,
          hasPairedDevice: false,
          userDisconnected: false,
          alreadyConnected: false,
          retryAlreadyScheduled: false,
        ),
        isFalse,
      );
      expect(
        shouldScheduleBleConnectRetry(
          serviceReady: true,
          hasPairedDevice: true,
          userDisconnected: false,
          alreadyConnected: false,
          retryAlreadyScheduled: true,
        ),
        isFalse,
      );
    });
  });

  group('shouldSoftRetryExistingConnection', () {
    test('reuses transport for the same device on force retry', () {
      expect(shouldSoftRetryExistingConnection(existingDeviceId: 'abc', targetDeviceId: 'abc', force: true), isTrue);
      expect(shouldSoftRetryExistingConnection(existingDeviceId: 'abc', targetDeviceId: 'abc', force: false), isFalse);
      expect(shouldSoftRetryExistingConnection(existingDeviceId: 'abc', targetDeviceId: 'xyz', force: true), isFalse);
    });
  });

  group('shouldKickStuckConnectingAttempt', () {
    test('kicks only after sustained .connecting without manual disconnect', () {
      expect(
        shouldKickStuckConnectingAttempt(
          isConnecting: true,
          manuallyDisconnected: false,
          elapsed: const Duration(seconds: 65),
        ),
        isTrue,
      );
      expect(
        shouldKickStuckConnectingAttempt(
          isConnecting: true,
          manuallyDisconnected: false,
          elapsed: const Duration(seconds: 30),
        ),
        isFalse,
      );
      expect(
        shouldKickStuckConnectingAttempt(
          isConnecting: true,
          manuallyDisconnected: true,
          elapsed: const Duration(seconds: 90),
        ),
        isFalse,
      );
    });
  });
}
