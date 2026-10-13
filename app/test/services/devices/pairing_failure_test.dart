import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/pairing_failure.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

void main() {
  test('pairing blocks split Android location, Nearby devices, Bluetooth, and radio-off', () {
    expect(
      pairingBlockBeforeScan(
        isAndroid: true,
        androidSdk: 30,
        bluetoothGranted: true,
        locationGranted: false,
        adapterOff: false,
      ),
      DevicePairingBlockedReason.locationPermissionMissing,
    );
    expect(
      pairingBlockBeforeScan(
        isAndroid: true,
        androidSdk: 31,
        bluetoothGranted: false,
        locationGranted: true,
        adapterOff: false,
      ),
      DevicePairingBlockedReason.nearbyDevicesDenied,
    );
    expect(
      pairingBlockBeforeScan(
        isAndroid: false,
        androidSdk: 0,
        bluetoothGranted: false,
        locationGranted: true,
        adapterOff: false,
      ),
      DevicePairingBlockedReason.bluetoothPermissionDenied,
    );
    expect(
      pairingBlockBeforeScan(
        isAndroid: true,
        androidSdk: 30,
        bluetoothGranted: true,
        locationGranted: true,
        adapterOff: true,
      ),
      DevicePairingBlockedReason.bluetoothOff,
    );
    expect(
      pairingBlockBeforeScan(
        isAndroid: false,
        androidSdk: 0,
        bluetoothGranted: true,
        locationGranted: true,
        adapterOff: false,
      ),
      isNull,
    );
  });

  test('native quiet scan returns fold into the same closed reasons', () {
    expect(pairingBlockFromNativeScan('nearby_devices_denied'), DevicePairingBlockedReason.nearbyDevicesDenied);
    expect(pairingBlockFromNativeScan('bluetooth_off'), DevicePairingBlockedReason.bluetoothOff);
    expect(pairingBlockFromNativeScan('no_adapter'), DevicePairingBlockedReason.bluetoothOff);
    expect(pairingBlockFromNativeScan('scanner_unavailable'), DevicePairingBlockedReason.bluetoothOff);
    expect(pairingBlockFromNativeScan('something_else'), isNull);
  });

  test('ios major version and empty-scan timing are closed integers', () {
    expect(iosMajorVersion('18.1.2'), 18);
    expect(iosMajorVersion(''), 0);
    expect(deviceScanEmptyAfterSeconds, 10);
    expect(shouldReportEmptyDeviceScan(deviceCount: 0), isTrue);
    expect(shouldReportEmptyDeviceScan(deviceCount: 1), isFalse);
  });

  test('connect failures use a closed error class', () {
    expect(classifyDeviceConnectError(StateError('init')), DeviceConnectFailedErrorClass.initializationFailed);
    expect(classifyDeviceConnectError(Exception('connection timeout')), DeviceConnectFailedErrorClass.timeout);
    expect(classifyDeviceConnectError(Exception('bluetooth adapter off')), DeviceConnectFailedErrorClass.bluetoothOff);
    expect(classifyDeviceConnectError(Exception('permission denied')), DeviceConnectFailedErrorClass.permissionDenied);
    expect(classifyDeviceConnectError(Exception('device not found')), DeviceConnectFailedErrorClass.notFound);
    expect(classifyDeviceConnectError(Exception('boom')), DeviceConnectFailedErrorClass.unknown);
  });

  test('BleBridge delivers Android scan-blocked reasons and drops removed listeners', () {
    final reasons = <String>[];
    final remove = BleBridge.instance.addScanBlockedListener(reasons.add);
    BleBridge.instance.onScanBlocked('bluetooth_off');
    remove();
    BleBridge.instance.onScanBlocked('no_adapter');
    expect(reasons, ['bluetooth_off']);
  });
}
