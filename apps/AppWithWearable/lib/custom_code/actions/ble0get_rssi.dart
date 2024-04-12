// Automatic FlutterFlow imports
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '/backend/schema/structs/index.dart';

Future<int> ble0getRssi(BTDeviceStruct btdevice) async {
  final device = BluetoothDevice.fromId(btdevice.id);
  return await device.readRssi();
}
