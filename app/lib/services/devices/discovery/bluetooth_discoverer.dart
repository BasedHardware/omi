import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:collection/collection.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/bluetooth/bluetooth_adapter.dart';
import 'package:omi/utils/logger.dart';
import 'device_discoverer.dart';

class BluetoothDeviceDiscoverer extends DeviceDiscoverer {
  @override
  String get name => 'Bluetooth';

  @override
  bool get isSupported => true;

  @override
  Future<DeviceDiscoveryResult> discover({int timeout = 5}) async {
    if (!(await BluetoothAdapter.isSupported)) {
      Logger.debug('Bluetooth not supported, skipping discovery');
      return const DeviceDiscoveryResult(devices: []);
    }

    final List<ScanResult> bleResults = [];
    late final StreamSubscription sub;

    sub = BluetoothAdapter.scanResults.listen((results) {
      final list = results.cast<ScanResult>().where((r) => r.device.platformName.isNotEmpty).toList();
      bleResults
        ..clear()
        ..addAll(list);
    }, onError: (e) {
      Logger.debug('BLE discovery error: $e');
    });

    try {
      await BluetoothAdapter.adapterState.where((v) => v == BluetoothAdapterStateHelper.on).first;

      await BluetoothAdapter.startScan(
        timeout: Duration(seconds: timeout),
      );

      // Give listener time to receive scan results within timeout
      await Future.delayed(Duration(seconds: timeout));

      final List<BtDevice> devices = bleResults
          .where((r) => BtDevice.isSupportedDevice(r))
          .sorted((a, b) => b.rssi.compareTo(a.rssi))
          .map<BtDevice>((r) => BtDevice.fromScanResult(r))
          .toList();

      return DeviceDiscoveryResult(
        devices: devices,
        metadata: {
          'bleResults': bleResults,
        },
      );
    } finally {
      await sub.cancel();
    }
  }

  @override
  Future<void> stop() async {
    if (BluetoothAdapter.isScanningNow) {
      await BluetoothAdapter.stopScan();
    }
  }
}
