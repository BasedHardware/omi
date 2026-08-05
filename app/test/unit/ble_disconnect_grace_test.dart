import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/ble_disconnect_grace.dart';

void main() {
  group('bleDisconnectCaptureGrace (#6678)', () {
    test('Android grace exceeds the 3s native reconnect delay', () {
      expect(bleDisconnectCaptureGrace(isAndroid: true), kAndroidBleReconnectGrace);
      expect(kAndroidBleReconnectGrace.inMilliseconds, greaterThan(3000));
    });

    test('iOS grace exceeds the ~200ms native reconnect delay', () {
      expect(bleDisconnectCaptureGrace(isAndroid: false), kIosBleReconnectGrace);
      expect(kIosBleReconnectGrace.inMilliseconds, greaterThan(200));
      expect(kIosBleReconnectGrace.inMilliseconds, lessThan(kAndroidBleReconnectGrace.inMilliseconds));
    });
  });

  group('shouldApplyDisconnectCaptureSideEffects (#6678)', () {
    test('defers capture teardown while inside the grace window', () {
      expect(
        shouldApplyDisconnectCaptureSideEffects(
          disconnectedFor: const Duration(milliseconds: 500),
          grace: kAndroidBleReconnectGrace,
        ),
        isFalse,
      );
      expect(
        shouldApplyDisconnectCaptureSideEffects(
          disconnectedFor: const Duration(milliseconds: 3499),
          grace: kAndroidBleReconnectGrace,
        ),
        isFalse,
      );
    });

    test('applies capture teardown once grace has elapsed', () {
      expect(
        shouldApplyDisconnectCaptureSideEffects(
          disconnectedFor: kAndroidBleReconnectGrace,
          grace: kAndroidBleReconnectGrace,
        ),
        isTrue,
      );
      expect(
        shouldApplyDisconnectCaptureSideEffects(
          disconnectedFor: const Duration(milliseconds: 4000),
          grace: kAndroidBleReconnectGrace,
        ),
        isTrue,
      );
    });

    test('never applies for negative elapsed time', () {
      expect(
        shouldApplyDisconnectCaptureSideEffects(
          disconnectedFor: const Duration(milliseconds: -1),
          grace: kIosBleReconnectGrace,
        ),
        isFalse,
      );
    });
  });
}
