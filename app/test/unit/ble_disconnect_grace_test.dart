import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/ble_disconnect_grace.dart';
import 'package:omi/utils/other/debouncer.dart';

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
    test('applies only while still disconnected after grace', () {
      expect(shouldApplyDisconnectCaptureSideEffects(stillDisconnected: true), isTrue);
      expect(shouldApplyDisconnectCaptureSideEffects(stillDisconnected: false), isFalse);
    });
  });

  group('disconnect grace debouncer reconnect cancel (#6678)', () {
    test('disconnected then connected does not invoke capture teardown', () {
      fakeAsync((async) {
        var teardownCount = 0;
        final debouncer = Debouncer(delay: kAndroidBleReconnectGrace);

        // disconnect schedules teardown after grace
        debouncer.run(() {
          if (!shouldApplyDisconnectCaptureSideEffects(stillDisconnected: true)) return;
          teardownCount++;
        });

        // reconnect before grace elapses — cancels pending teardown
        async.elapse(const Duration(milliseconds: 1000));
        debouncer.cancel();

        async.elapse(kAndroidBleReconnectGrace);
        expect(teardownCount, 0);
      });
    });

    test('teardown runs when grace elapses without reconnect', () {
      fakeAsync((async) {
        var teardownCount = 0;
        var stillDisconnected = true;
        final debouncer = Debouncer(delay: kAndroidBleReconnectGrace);

        debouncer.run(() {
          if (!shouldApplyDisconnectCaptureSideEffects(stillDisconnected: stillDisconnected)) return;
          teardownCount++;
        });

        async.elapse(kAndroidBleReconnectGrace);
        expect(teardownCount, 1);
      });
    });

    test('residual race: callback no-ops if reconnect flipped stillDisconnected', () {
      fakeAsync((async) {
        var teardownCount = 0;
        var stillDisconnected = true;
        final debouncer = Debouncer(delay: kAndroidBleReconnectGrace);

        debouncer.run(() {
          if (!shouldApplyDisconnectCaptureSideEffects(stillDisconnected: stillDisconnected)) return;
          teardownCount++;
        });

        // Simulate cancel losing the race: timer fires but reconnect already set connected.
        async.elapse(kAndroidBleReconnectGrace - const Duration(milliseconds: 1));
        stillDisconnected = false;
        async.elapse(const Duration(milliseconds: 1));
        expect(teardownCount, 0);
      });
    });
  });
}
