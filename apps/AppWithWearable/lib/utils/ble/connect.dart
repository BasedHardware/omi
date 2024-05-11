import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/structs/b_t_device_struct.dart';

Future<bool> bleConnectDevice(BTDeviceStruct btDevice) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  try {
    await device.connect();
  } catch (e) {
    debugPrint(e.toString());
  }
  var hasWriteCharacteristic = false;
  final services = await device.discoverServices();
  for (BluetoothService service in services) {
    for (BluetoothCharacteristic characteristic in service.characteristics) {
      final isWrite = characteristic.properties.write;
      if (isWrite) {
        debugPrint('Found write characteristic: ${characteristic.uuid}, ${characteristic.properties}');
        hasWriteCharacteristic = true;
      }
    }
  }
  return hasWriteCharacteristic;
}

Future bleDisconnectDevice(BTDeviceStruct btDevice) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  try {
    await device.disconnect();
  } catch (e) {
    debugPrint(e.toString());
  }
}
