// Automatic FlutterFlow imports
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

Future<List<BTDeviceStruct>> ble0findDevices() async {
  List<BTDeviceStruct> devices = [];
  var subscription = FlutterBluePlus.scanResults.listen((results) {
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
        id: deviceResult.device.remoteId.toString(),
        rssi: deviceResult.rssi,
      ));
    }
  });
  FlutterBluePlus.cancelWhenScanComplete(subscription);

  await FlutterBluePlus.adapterState
      .where((val) => val == BluetoothAdapterState.on)
      .first;

  final isScanning = FlutterBluePlus.isScanningNow;
  if (!isScanning) {
    await FlutterBluePlus.startScan(
        timeout: const Duration(seconds: 5), androidUsesFineLocation: true);
  }

  await FlutterBluePlus.isScanning.where((val) => val == false).first;

  return devices;
}
