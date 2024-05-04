// Automatic FlutterFlow imports
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '/backend/schema/structs/index.dart';

Future<List<int>?> bleReceiveWavTest(BTDeviceStruct btDevice) async {
  final device = BluetoothDevice.fromId(btDevice.id);

  try {
    await device.connect();
    List<BluetoothService> services = await device.discoverServices();

    for (BluetoothService service in services) {
      for (BluetoothCharacteristic characteristic in service.characteristics) {
        final isNotify = characteristic.properties.notify;
        if (isNotify) {
          await characteristic.setNotifyValue(true);
          List<int> wavData = [];

          characteristic.value.listen((value) {
            wavData.addAll(value);
          });

          // Wait for a short duration to receive data
          await Future.delayed(Duration(seconds: 5));

          await characteristic.setNotifyValue(false);
          await device.disconnect();

          return wavData;
        }
      }
    }
  } catch (e) {
    print('Error receiving data: $e');
  } finally {
    await device.disconnect();
  }

  return null;
}
