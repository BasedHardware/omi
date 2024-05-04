// Automatic FlutterFlow imports
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '/backend/schema/structs/index.dart';

Future ble0sendData(BTDeviceStruct btdevice, String data) async {
  final device = BluetoothDevice.fromId(btdevice.id);
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
