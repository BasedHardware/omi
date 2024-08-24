import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/connect.dart';
import 'package:friend_private/utils/ble/find.dart';

Future<BTDeviceStruct?> scanAndConnectDevice({bool autoConnect = true, bool timeout = false}) async {
  print('scanAndConnectDevice');
  var deviceId = SharedPreferencesUtil().btDeviceStruct.id;
  print('scanAndConnectDevice ${deviceId}');
  for (var device in FlutterBluePlus.connectedDevices) {
    if (device.remoteId.str == deviceId) {
      return BTDeviceStruct(
        id: device.remoteId.str,
        name: device.platformName,
        rssi: await device.readRssi(),
      );
    }
  }
  int timeoutCounter = 0;
  while (true) {
    if (timeout && timeoutCounter >= 10) return null;
    List<BTDeviceStruct> foundDevices = await bleFindDevices();
    for (BTDeviceStruct device in foundDevices) {
      // Remember the first connected device.
      // Technically, there should be only one
      if (deviceId == '') {
        deviceId = device.id;
        SharedPreferencesUtil().btDeviceStruct = device;
        SharedPreferencesUtil().deviceName = device.name;
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
    timeoutCounter += 2;
  }
}
