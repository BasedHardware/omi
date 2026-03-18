import 'dart:async';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/logger.dart';
import 'device_discoverer.dart';

/// iOS-only BLE discoverer that uses native CoreBluetooth via Pigeon.
/// Replaces [BluetoothDeviceDiscoverer] on iOS — no flutter_blue_plus dependency.
class NativeBluetoothDiscoverer extends DeviceDiscoverer {
  final BleHostApi _hostApi = BleHostApi();

  @override
  String get name => 'NativeBluetooth';

  @override
  bool get isSupported => true;

  @override
  Future<DeviceDiscoveryResult> discover({int timeout = 5}) async {
    final List<BlePeripheral> results = [];
    final completer = Completer<void>();

    final previousCallback = BleBridge.instance.peripheralDiscoveredCallback;

    BleBridge.instance.peripheralDiscoveredCallback = (BlePeripheral peripheral) {
      if (peripheral.name.isNotEmpty) {
        // Deduplicate by UUID
        results.removeWhere((p) => p.uuid == peripheral.uuid);
        results.add(peripheral);
      }
    };

    try {
      _hostApi.startScan(timeout, []);

      // Wait for scan to complete
      Timer(Duration(seconds: timeout), () {
        if (!completer.isCompleted) completer.complete();
      });
      await completer.future;

      _hostApi.stopScan();

      final devices = results
          .where(_isSupportedPeripheral)
          .map(_peripheralToDevice)
          .toList()
        ..sort((a, b) => b.rssi.compareTo(a.rssi));

      return DeviceDiscoveryResult(devices: devices);
    } finally {
      BleBridge.instance.peripheralDiscoveredCallback = previousCallback;
    }
  }

  @override
  Future<void> stop() async {
    try {
      _hostApi.stopScan();
    } catch (e) {
      Logger.debug('NativeBluetoothDiscoverer: stop scan error: $e');
    }
  }

  // MARK: - Device type detection (mirrors BtDevice.isSupportedDevice without ScanResult)

  static bool _isSupportedPeripheral(BlePeripheral p) {
    return _isBee(p) || _isPlaud(p) || _isFieldy(p) || _isFriendPendant(p) || _isLimitless(p) || _isOmi(p) || _isFrame(p);
  }

  static bool _isBee(BlePeripheral p) {
    return p.name.toLowerCase().contains('bee');
  }

  static bool _isPlaud(BlePeripheral p) {
    return p.name.toUpperCase().startsWith('PLAUD');
  }

  static bool _isFieldy(BlePeripheral p) {
    final name = p.name.toLowerCase();
    return name == 'compass' || name == 'fieldy' || _hasService(p, fieldyServiceUuid);
  }

  static bool _isFriendPendant(BlePeripheral p) {
    return p.name.toLowerCase().startsWith('friend_') || _hasService(p, friendPendantServiceUuid);
  }

  static bool _isLimitless(BlePeripheral p) {
    final name = p.name.toLowerCase();
    return name.contains('limitless') || name.contains('pendant') || _hasService(p, limitlessServiceUuid);
  }

  static bool _isOmi(BlePeripheral p) {
    return _hasService(p, omiServiceUuid);
  }

  static bool _isFrame(BlePeripheral p) {
    return _hasService(p, frameServiceUuid);
  }

  static bool _hasService(BlePeripheral p, String serviceUuid) {
    final target = serviceUuid.toLowerCase();
    return p.serviceUuids.any((uuid) => uuid.toLowerCase() == target);
  }

  static BtDevice _peripheralToDevice(BlePeripheral p) {
    DeviceType type;
    if (_isBee(p)) {
      type = DeviceType.bee;
    } else if (_isPlaud(p)) {
      type = DeviceType.plaud;
    } else if (_isFieldy(p)) {
      type = DeviceType.fieldy;
    } else if (_isFriendPendant(p)) {
      type = DeviceType.friendPendant;
    } else if (_isLimitless(p)) {
      type = DeviceType.limitless;
    } else if (_isOmi(p)) {
      type = DeviceType.omi;
    } else if (_isFrame(p)) {
      type = DeviceType.frame;
    } else {
      type = DeviceType.omi;
    }

    return BtDevice(
      name: p.name,
      id: p.uuid,
      type: type,
      rssi: p.rssi,
      locator: DeviceLocator.bluetooth(deviceId: p.uuid),
    );
  }
}
