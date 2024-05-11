import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '/backend/schema/structs/index.dart';

Future<String?> bleReceiveData(BTDeviceStruct btdevice) async {
  final device = BluetoothDevice.fromId(btdevice.id);
  final services = await device.discoverServices();
  for (BluetoothService service in services) {
    for (BluetoothCharacteristic characteristic in service.characteristics) {
      final isRead = characteristic.properties.read;
      final isNotify = characteristic.properties.notify;
      if (isRead && isNotify) {
        final value = await characteristic.read();
        return String.fromCharCodes(value);
      }
    }
  }
  return null;
}

Future bleSendData(BTDeviceStruct btDevice, String data) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  final services = await device.discoverServices();
  for (BluetoothService service in services) {
    for (BluetoothCharacteristic characteristic in service.characteristics) {
      final isWrite = characteristic.properties.write;
      if (isWrite) {
        await characteristic.write(data.codeUnits);
      }
    }
  }
}
