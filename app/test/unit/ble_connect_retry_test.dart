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

  group('shouldInvalidatePendingRetryForDifferentTarget (#6610 review)', () {
    test('invalidates a pending retry when force-connecting to a different device', () {
      expect(
        shouldInvalidatePendingRetryForDifferentTarget(
          pendingRetryDeviceId: 'old-device',
          targetDeviceId: 'new-device',
          force: true,
        ),
        isTrue,
      );
    });

    test('does not invalidate when there is no pending retry', () {
      expect(
        shouldInvalidatePendingRetryForDifferentTarget(
          pendingRetryDeviceId: null,
          targetDeviceId: 'new-device',
          force: true,
        ),
        isFalse,
      );
    });

    test('does not invalidate the retry\'s own device or a non-forced call', () {
      expect(
        shouldInvalidatePendingRetryForDifferentTarget(
          pendingRetryDeviceId: 'same-device',
          targetDeviceId: 'same-device',
          force: true,
        ),
        isFalse,
      );
      expect(
        shouldInvalidatePendingRetryForDifferentTarget(
          pendingRetryDeviceId: 'old-device',
          targetDeviceId: 'new-device',
          force: false,
        ),
        isFalse,
      );
    });
  });

  group('shouldProceedWithScheduledSoftRetry (#6721 cubic)', () {
    test('proceeds only when the scheduled generation is still current', () {
      expect(shouldProceedWithScheduledSoftRetry(scheduledGeneration: 3, currentGeneration: 3), isTrue);
      expect(shouldProceedWithScheduledSoftRetry(scheduledGeneration: 3, currentGeneration: 4), isFalse);
      expect(shouldProceedWithScheduledSoftRetry(scheduledGeneration: 0, currentGeneration: 1), isFalse);
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

  group('shouldAttemptBleReconnectOnResume (#6721)', () {
    test('kicks reconnect when paired but disconnected and not manually stopped', () {
      expect(
        shouldAttemptBleReconnectOnResume(
          hasPairedDevice: true,
          isConnected: false,
          isConnecting: false,
          userDisconnected: false,
        ),
        isTrue,
      );
    });

    test('skips when already connected, connecting, unpaired, or user disconnected', () {
      expect(
        shouldAttemptBleReconnectOnResume(
          hasPairedDevice: true,
          isConnected: true,
          isConnecting: false,
          userDisconnected: false,
        ),
        isFalse,
      );
      expect(
        shouldAttemptBleReconnectOnResume(
          hasPairedDevice: true,
          isConnected: false,
          isConnecting: true,
          userDisconnected: false,
        ),
        isFalse,
      );
      expect(
        shouldAttemptBleReconnectOnResume(
          hasPairedDevice: false,
          isConnected: false,
          isConnecting: false,
          userDisconnected: false,
        ),
        isFalse,
      );
      expect(
        shouldAttemptBleReconnectOnResume(
          hasPairedDevice: true,
          isConnected: false,
          isConnecting: false,
          userDisconnected: true,
        ),
        isFalse,
      );
    });
  });
}
