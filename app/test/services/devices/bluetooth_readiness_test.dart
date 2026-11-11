import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';

void main() {
  group('BluetoothReadiness', () {
    test('blocks a powered-off discovery and publishes one actionable guidance event', () async {
      final readiness = BluetoothReadiness(readState: () async => 'off', observeBridge: false);

      expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
      expect(readiness.state, BluetoothAdapterState.off);
      expect(readiness.guidance?.use, BluetoothUse.discovery);

      final firstGuidance = readiness.guidance!;
      readiness.dismissGuidance(firstGuidance.id);
      expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
      expect(readiness.guidance, isNull, reason: 'periodic scans must not reopen a dismissed prompt');
    });

    test('clears a dismissed blocked state when Bluetooth comes back on', () async {
      var nativeState = 'off';
      final readiness = BluetoothReadiness(readState: () async => nativeState, observeBridge: false);

      await readiness.ensureReady(BluetoothUse.connection);
      readiness.dismissGuidance(readiness.guidance!.id);
      readiness.onNativeStateChangedForTesting('on');
      nativeState = 'off';

      expect(await readiness.ensureReady(BluetoothUse.connection), isFalse);
      expect(readiness.guidance?.state, BluetoothAdapterState.off);
    });

    test('refreshes state after Android enable request instead of trusting its result', () async {
      var nativeState = 'off';
      final readiness = BluetoothReadiness(
        readState: () async => nativeState,
        requestEnable: () async {
          nativeState = 'on';
          return false;
        },
        observeBridge: false,
      );

      expect(await readiness.requestEnable(BluetoothUse.discovery), isTrue);
      expect(readiness.state, BluetoothAdapterState.on);
      expect(readiness.guidance, isNull);
    });

    test('does not reopen guidance when the Android enable prompt is cancelled', () async {
      final readiness = BluetoothReadiness(
        readState: () async => 'off',
        requestEnable: () async => false,
        observeBridge: false,
      );

      await readiness.ensureReady(BluetoothUse.connection);
      await readiness.requestEnable(BluetoothUse.connection);

      expect(readiness.guidance, isNull);
      expect(await readiness.ensureReady(BluetoothUse.connection), isFalse);
      expect(readiness.guidance, isNull);
    });

    test('contains a failed enable request without reopening its guidance', () async {
      final readiness = BluetoothReadiness(
        readState: () async => 'off',
        requestEnable: () async => throw StateError('platform channel unavailable'),
        observeBridge: false,
      );

      await readiness.ensureReady(BluetoothUse.connection);

      expect(await readiness.requestEnable(BluetoothUse.connection), isFalse);
      expect(readiness.guidance, isNull);
    });

    test('contains a failed state refresh after an enable request', () async {
      var reads = 0;
      final readiness = BluetoothReadiness(
        readState: () async {
          reads++;
          if (reads == 1) return 'off';
          throw StateError('platform channel unavailable');
        },
        requestEnable: () async => true,
        observeBridge: false,
      );

      await readiness.ensureReady(BluetoothUse.connection);

      expect(await readiness.requestEnable(BluetoothUse.connection), isFalse);
      expect(readiness.guidance, isNull);
    });

    test('shares one guidance event across overlapping blocked operations', () async {
      final readiness = BluetoothReadiness(readState: () async => 'off', observeBridge: false);

      await readiness.ensureReady(BluetoothUse.discovery);
      final firstGuidanceId = readiness.guidance!.id;
      await readiness.ensureReady(BluetoothUse.connection);

      expect(readiness.guidance?.id, firstGuidanceId);
    });

    test('surfaces revoked Bluetooth permission separately from adapter power', () async {
      final readiness = BluetoothReadiness(
        readState: () async => 'on',
        permissionState: (_) async => BluetoothAdapterState.unauthorized,
        observeBridge: false,
      );

      expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
      expect(readiness.state, BluetoothAdapterState.unauthorized);
      expect(readiness.guidance?.state, BluetoothAdapterState.unauthorized);
    });
  });
}
