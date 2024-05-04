// Automatic FlutterFlow imports
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '/backend/schema/structs/index.dart';

Future<List<BTDeviceStruct>> ble0getConnectedDevices() async {
  final connectedDevices = await FlutterBluePlus.connectedDevices;
  List<BTDeviceStruct> devices = [];

  for (int i = 0; i < connectedDevices.length; i++) {
    final deviceResult = connectedDevices[i];
    final deviceState = deviceResult.state;

    if (deviceState == BluetoothDeviceState.connected) {
      final deviceRssi = await deviceResult.readRssi();
      devices.add(BTDeviceStruct(
        name: deviceResult.name,
        id: deviceResult.id.toString(),
        rssi: deviceRssi,
      ));
    }
  }

  return devices;
}
