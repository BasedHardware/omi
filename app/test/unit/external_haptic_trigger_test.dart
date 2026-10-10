import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/external_haptic_trigger.dart';

void main() {
  ExternalHapticRateLimiter freshLimiter() => ExternalHapticRateLimiter();

  group('runExternalHapticTrigger', () {
    test('dispatches supported production, dev, and beta links', () async {
      for (final scheme in ['omi', 'omi-dev', 'omi-beta']) {
        String? observedDeviceId;
        int? observedLevel;

        final result = await runExternalHapticTrigger(
          Uri.parse('$scheme://device/haptic?level=2'),
          deviceId: 'device-123',
          rateLimiter: freshLimiter(),
          playHaptic: (deviceId, level) async {
            observedDeviceId = deviceId;
            observedLevel = level;
            return true;
          },
        );

        expect(result, ExternalHapticTriggerResult.played);
        expect(observedDeviceId, 'device-123');
        expect(observedLevel, 2);
      }
    });

    test('rejects HTTPS universal links', () async {
      var called = false;

      final result = await runExternalHapticTrigger(
        Uri.parse('https://device/haptic?level=2'),
        deviceId: 'device-123',
        rateLimiter: freshLimiter(),
        playHaptic: (_, __) async {
          called = true;
          return true;
        },
      );

      expect(result, ExternalHapticTriggerResult.notHandled);
      expect(called, isFalse);
    });

    test('rejects non-canonical or repeated haptic levels', () async {
      for (final uri in [
        Uri.parse('omi://device/haptic?level=0'),
        Uri.parse('omi://device/haptic?level=4'),
        Uri.parse('omi://device/haptic?level=fast'),
        Uri.parse('omi://device/haptic?level='),
        Uri.parse('omi://device/haptic?level=0x2'),
        Uri.parse('omi://device/haptic?level=02'),
        Uri.parse('omi://device/haptic?level=%2B2'),
        Uri.parse('omi://device/haptic?level=2&level=3'),
      ]) {
        var called = false;

        final result = await runExternalHapticTrigger(
          uri,
          deviceId: 'device-123',
          rateLimiter: freshLimiter(),
          playHaptic: (_, __) async {
            called = true;
            return true;
          },
        );

        expect(result, ExternalHapticTriggerResult.notHandled, reason: '$uri should be rejected');
        expect(called, isFalse);
      }
    });

    test('does not connect when no paired device is configured', () async {
      var called = false;

      final result = await runExternalHapticTrigger(
        Uri.parse('omi://device/haptic?level=1'),
        deviceId: '',
        rateLimiter: freshLimiter(),
        playHaptic: (_, __) async {
          called = true;
          return true;
        },
      );

      expect(result, ExternalHapticTriggerResult.noPairedDevice);
      expect(called, isFalse);
    });

    test('surfaces an unavailable device or unsupported haptic transport', () async {
      final result = await runExternalHapticTrigger(
        Uri.parse('omi://device/haptic?level=3'),
        deviceId: 'device-123',
        rateLimiter: freshLimiter(),
        playHaptic: (_, __) async => false,
      );

      expect(result, ExternalHapticTriggerResult.unavailable);
    });

    test('keeps a device single-flight after cooldown while dispatch is pending', () async {
      var elapsed = Duration.zero;
      final limiter = ExternalHapticRateLimiter(
        cooldown: const Duration(seconds: 2),
        elapsed: () => elapsed,
      );
      final firstDispatch = Completer<bool>();
      var calls = 0;

      Future<bool> player(String _, int __) {
        calls++;
        if (calls == 1) return firstDispatch.future;
        return Future.value(true);
      }

      final first = runExternalHapticTrigger(
        Uri.parse('omi://device/haptic?level=3'),
        deviceId: 'device-123',
        rateLimiter: limiter,
        playHaptic: player,
      );

      // Even after the admission cooldown has fully elapsed, an unresolved
      // reconnect/write remains single-flight for this device.
      elapsed = const Duration(seconds: 2);
      final whilePending = await runExternalHapticTrigger(
        Uri.parse('omi://device/haptic?level=3'),
        deviceId: 'device-123',
        rateLimiter: limiter,
        playHaptic: player,
      );
      expect(whilePending, ExternalHapticTriggerResult.rateLimited);
      expect(calls, 1);

      firstDispatch.complete(true);
      expect(await first, ExternalHapticTriggerResult.played);

      // The original admission was two seconds ago, so once the in-flight
      // operation releases, the next dispatch may use the new slot.
      final afterCompletion = await runExternalHapticTrigger(
        Uri.parse('omi://device/haptic?level=3'),
        deviceId: 'device-123',
        rateLimiter: limiter,
        playHaptic: player,
      );
      expect(afterCompletion, ExternalHapticTriggerResult.played);
      expect(calls, 2);
    });

    test('failed dispatch still consumes cooldown and bounds reconnect attempts', () async {
      var elapsed = Duration.zero;
      final limiter = ExternalHapticRateLimiter(
        cooldown: const Duration(seconds: 2),
        elapsed: () => elapsed,
      );
      var calls = 0;

      Future<bool> unavailable(String _, int __) async {
        calls++;
        return false;
      }

      final first = await runExternalHapticTrigger(
        Uri.parse('omi://device/haptic?level=1'),
        deviceId: 'device-123',
        rateLimiter: limiter,
        playHaptic: unavailable,
      );
      final immediateRetry = await runExternalHapticTrigger(
        Uri.parse('omi://device/haptic?level=1'),
        deviceId: 'device-123',
        rateLimiter: limiter,
        playHaptic: unavailable,
      );

      expect(first, ExternalHapticTriggerResult.unavailable);
      expect(immediateRetry, ExternalHapticTriggerResult.rateLimited);
      expect(calls, 1);

      elapsed = const Duration(seconds: 2);
      final laterRetry = await runExternalHapticTrigger(
        Uri.parse('omi://device/haptic?level=1'),
        deviceId: 'device-123',
        rateLimiter: limiter,
        playHaptic: unavailable,
      );
      expect(laterRetry, ExternalHapticTriggerResult.unavailable);
      expect(calls, 2);
    });

    test('a thrown player error releases single-flight but preserves cooldown', () async {
      var elapsed = Duration.zero;
      final limiter = ExternalHapticRateLimiter(
        cooldown: const Duration(seconds: 2),
        elapsed: () => elapsed,
      );
      var calls = 0;

      Future<bool> throwingPlayer(String _, int __) async {
        calls++;
        throw StateError('dispatch failed');
      }

      await expectLater(
        runExternalHapticTrigger(
          Uri.parse('omi://device/haptic?level=2'),
          deviceId: 'device-123',
          rateLimiter: limiter,
          playHaptic: throwingPlayer,
        ),
        throwsStateError,
      );

      final duringCooldown = await runExternalHapticTrigger(
        Uri.parse('omi://device/haptic?level=2'),
        deviceId: 'device-123',
        rateLimiter: limiter,
        playHaptic: throwingPlayer,
      );
      expect(duringCooldown, ExternalHapticTriggerResult.rateLimited);
      expect(calls, 1);

      elapsed = const Duration(seconds: 2);
      await expectLater(
        runExternalHapticTrigger(
          Uri.parse('omi://device/haptic?level=2'),
          deviceId: 'device-123',
          rateLimiter: limiter,
          playHaptic: throwingPlayer,
        ),
        throwsStateError,
      );
      expect(calls, 2);
    });
  });
}
