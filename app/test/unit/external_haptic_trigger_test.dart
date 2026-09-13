import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/external_haptic_trigger.dart';

void main() {
  group('runExternalHapticTrigger', () {
    test('dispatches supported production, dev, and beta links', () async {
      for (final scheme in ['omi', 'omi-dev', 'omi-beta']) {
        String? observedDeviceId;
        int? observedLevel;

        final result = await runExternalHapticTrigger(
          Uri.parse('$scheme://device/haptic?level=2'),
          deviceId: 'device-123',
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
        Uri.parse('https://h.omi.me/device/haptic?level=2'),
        deviceId: 'device-123',
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
        playHaptic: (_, __) async => false,
      );

      expect(result, ExternalHapticTriggerResult.unavailable);
    });
  });
}
