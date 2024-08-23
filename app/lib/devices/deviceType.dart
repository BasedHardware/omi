import 'dart:async';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/devices/btleDevice.dart';
import 'package:friend_private/devices/device.dart';
import 'package:friend_private/devices/friend/friendDeviceType.dart';
import 'package:friend_private/devices/friend/openGlassDeviceType.dart';
import 'frame/frameDeviceType.dart';

abstract class DeviceType {
  String get manufacturerName;
  String get deviceNameForMatching;
  Type get deviceType;

  Device createDeviceFromScan(String name, String id, int? rssi);
  Future<List<Device>> findDevices();

  static final Map<String, Device> _deviceInstances = {};

  Device getOrCreate(String name, String id, int? rssi) {
    if (_deviceInstances.containsKey(id) && _deviceInstances[id] != null) {
      if (rssi != null && _deviceInstances[id] is BtleDevice) {
        (_deviceInstances[id] as BtleDevice).rssi = rssi;
      }
      return _deviceInstances[id]!;
    }
    final newDevice = createDeviceFromScan(name, id, rssi); 
    _deviceInstances[id] = newDevice;
    return newDevice;
  }
}

abstract class BtleDeviceType extends DeviceType {
  List<Guid> get serviceGuids;

  Future<List<Device>> bleFindDevices() async {
    List<Device> devices = [];
    StreamSubscription<List<ScanResult>>? scanSubscription;

    try {
      if ((await FlutterBluePlus.isSupported) == false) return [];

      // Listen to scan results
      scanSubscription = FlutterBluePlus.scanResults.listen(
        (results) {
          List<ScanResult> scannedDevices =
              results.where((r) => r.device.platformName.isNotEmpty).toList();
          scannedDevices.sort((a, b) => b.rssi.compareTo(a.rssi));

          devices = scannedDevices.map((deviceResult) {
            return getOrCreate(
              deviceResult.device.platformName,
              deviceResult.device.remoteId.str,
              deviceResult.rssi,
            );
          }).toList();
        },
        onError: (e) {
          print('bleFindDevices error: $e');
        },
      );

      // Start scanning if not already scanning
      // Only look for devices that implement Friend main service
      if (!FlutterBluePlus.isScanningNow) {
        await FlutterBluePlus.startScan(
          timeout: const Duration(seconds: 5),
          withServices: serviceGuids,
        );
      }
    } finally {
      // Cancel subscription to avoid memory leaks
      await scanSubscription?.cancel();
    }

    return devices;
  }

  @override
  Future<List<Device>> findDevices() async {
    return await bleFindDevices();
  }
}

class AnyDeviceType extends BtleDeviceType {
  @override
  String get manufacturerName => 'Unknown';
  @override
  String get deviceNameForMatching => 'Unknown';

  @override
  Type get deviceType => Device;
  List<DeviceType> get deviceTypes => [FriendDeviceType(), FrameDeviceType(), OpenGlassDeviceType()];

  @override
  Device createDeviceFromScan(String name, String id, int? rssi) {
    print('createDeviceFromScan: $name');
    for (var deviceType in deviceTypes) {
      if (name.startsWith(deviceType.deviceNameForMatching)) {
        return deviceType.getOrCreate(name, id, rssi);
      }
    }
    throw Exception('Device type not found: $name');
  }

  @override
  List<Guid> get serviceGuids {
    List<Guid> serviceGuids = [];
    for (var deviceType in deviceTypes) {
      if (deviceType is BtleDeviceType) {
        serviceGuids.addAll(deviceType.serviceGuids);
      }
    }
    return serviceGuids;
  }
}
