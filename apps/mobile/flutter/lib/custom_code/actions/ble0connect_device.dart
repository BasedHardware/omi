// Automatic FlutterFlow imports
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '/backend/schema/structs/index.dart';

Future<bool> ble0connectDevice(BTDeviceStruct btdevice) async {
  final device = BluetoothDevice.fromId(btdevice.id);
  try {
    await device.connect();
  } catch (e) {
    print(e);
  }
  var hasWriteCharacteristic = false;
  final services = await device.discoverServices();
  for (BluetoothService service in services) {
    for (BluetoothCharacteristic characteristic in service.characteristics) {
      final isWrite = characteristic.properties.write;
      if (isWrite) {
        debugPrint(
            'Found write characteristic: ${characteristic.uuid}, ${characteristic.properties}');
        hasWriteCharacteristic = true;
      }
    }
  }
  return hasWriteCharacteristic;
}
