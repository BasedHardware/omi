import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device.dart';

Future<List<BTDeviceStruct>> bleFindDevices() async {
  List<BTDeviceStruct> devices = [];
  StreamSubscription<List<ScanResult>>? scanSubscription;

  try {
    if ((await FlutterBluePlus.isSupported) == false) return [];

    // Listen to scan results
    scanSubscription = FlutterBluePlus.scanResults.listen(
      (results) {
        List<ScanResult> scannedDevices = results.where((r) => r.device.platformName.isNotEmpty).toList();
        scannedDevices.sort((a, b) => b.rssi.compareTo(a.rssi));

        devices = scannedDevices.map((deviceResult) {
          return BTDeviceStruct(
            name: deviceResult.device.platformName,
            id: deviceResult.device.remoteId.str,
            rssi: deviceResult.rssi,
          );
        }).toList();
      },
      onError: (e) {
        debugPrint('bleFindDevices error: $e');
      },
    );

    // Start scanning if not already scanning
    // Only look for devices that implement Friend main service
    if (!FlutterBluePlus.isScanningNow) {
      await FlutterBluePlus.startScan(
        timeout: const Duration(seconds: 5),
        withServices: [Guid("19b10000-e8f2-537e-4f6c-d104768a1214")],
      );
    }
  } finally {
    // Cancel subscription to avoid memory leaks
    await scanSubscription?.cancel();
  }

  return devices;
}
