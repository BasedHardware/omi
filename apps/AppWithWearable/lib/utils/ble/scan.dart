import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:friend_private/utils/ble/find.dart';
import 'package:friend_private/backend/preferences.dart';

Future<BTDeviceStruct?> scanAndConnectDevice() async {
  while (true) {
    List<BTDeviceStruct> foundDevices = await bleFindDevices();
    for (BTDeviceStruct device in foundDevices) {
      if (device.id == SharedPreferencesUtil().deviceId) {
        try {
          await bleConnectDevice(device.id);
          return device;
        } catch (e) {
          print(e);
        }
      }
    }
    // If the device is not found, wait for a bit before retrying.
    await Future.delayed(const Duration(seconds: 2));
  }
}


Future<List<BTDeviceStruct?>> scanDevices() async {
    List<BTDeviceStruct> foundDevices = await bleFindDevices();
    return foundDevices;
}