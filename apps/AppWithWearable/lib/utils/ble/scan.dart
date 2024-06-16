import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:friend_private/utils/ble/find.dart';

Future<BTDeviceStruct?> scanAndConnectDevice({bool autoConnect = true}) async {
  var deviceId = SharedPreferencesUtil().deviceId;
  for (var device in FlutterBluePlus.connectedDevices) {
    if (device.remoteId.str == deviceId) {
      return BTDeviceStruct(
        id: device.remoteId.str,
        name: device.platformName,
        rssi: await device.readRssi(),
      );
    }
  }
  while (true) {
    List<BTDeviceStruct> foundDevices = await bleFindDevices();
    for (BTDeviceStruct device in foundDevices) {
      if (deviceId == '' && device.name == 'Friend') {
        deviceId = device.id;
        SharedPreferencesUtil().deviceId = deviceId;
      }

      if (device.id == deviceId) {
        try {
          await bleConnectDevice(device.id, autoConnect: autoConnect);
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
  // var filteredDevices = foundDevices.where((device) => device.name == "Friend").toList();
  var filteredDevices = foundDevices.toList();
  return filteredDevices;
}
