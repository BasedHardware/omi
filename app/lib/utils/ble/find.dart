import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/gatt_utils.dart';

Future<List<BTDeviceStruct>> bleFindDevices() async {
  List<BTDeviceStruct> devices = [];
  StreamSubscription<List<ScanResult>>? scanSubscription;

  try {
    if ((await FlutterBluePlus.isSupported) == false) return [];

    // Listen to scan results
    scanSubscription = FlutterBluePlus.scanResults.listen(
      (results) async {
        List<ScanResult> scannedDevices =
            results.where((r) => r.device.platformName.isNotEmpty).toList();
        scannedDevices.sort((a, b) => b.rssi.compareTo(a.rssi));

        devices = await Future.wait(scannedDevices.map((deviceResult) async {
          DeviceType? deviceType;
          if (deviceResult.advertisementData.serviceUuids
              .contains(Guid(friendServiceUuid))) {
            deviceType = DeviceType.friend;
          } else if (deviceResult.advertisementData.serviceUuids
              .contains(Guid(frameServiceUuid))) {
            deviceType = DeviceType.frame;
          }
          if (deviceType != null) {
            deviceTypeMap[deviceResult.device.remoteId.toString()] = deviceType;
          } else if (deviceTypeMap
              .containsKey(deviceResult.device.remoteId.toString())) {
            deviceType = deviceTypeMap[deviceResult.device.remoteId.toString()];
          }
          return BTDeviceStruct(
            name: deviceResult.device.platformName,
            id: deviceResult.device.remoteId.str,
            rssi: deviceResult.rssi,
            type: deviceType,
          );
        }));
      },
      onError: (e) {
        debugPrint('bleFindDevices error: $e');
      },
    );

    // Start scanning if not already scanning
    // Only look for devices that implement Friend or Frame main service
    if (!FlutterBluePlus.isScanningNow) {
      await FlutterBluePlus.startScan(
        timeout: const Duration(seconds: 5),
        withServices: [Guid(friendServiceUuid), Guid(frameServiceUuid)],
      );
    }
  } finally {
    // Cancel subscription to avoid memory leaks
    await scanSubscription?.cancel();
  }

  return devices;
}
