import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '/backend/schema/structs/index.dart';

Future<List<BTDeviceStruct>> bleFindDevices() async {
  List<BTDeviceStruct> devices = [];
  FlutterBluePlus.scanResults.listen((results) {
    List<ScanResult> scannedDevices = [];
    for (ScanResult r in results) {
      if (r.device.platformName.isNotEmpty) {
        scannedDevices.add(r);
      }
    }
    scannedDevices.sort((a, b) => b.rssi.compareTo(a.rssi));
    devices.clear();
    for (var deviceResult in scannedDevices) {
      devices.add(BTDeviceStruct(
        name: deviceResult.device.platformName,
        id: deviceResult.device.remoteId.str,
        rssi: deviceResult.rssi,
      ));
    }
  });
  final isScanning = FlutterBluePlus.isScanningNow;
  if (!isScanning) {
    await FlutterBluePlus.startScan(
      timeout: const Duration(seconds: 5),
    );
  }

  return devices;
}
