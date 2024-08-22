import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/devices/device.dart';
import 'package:friend_private/devices/deviceType.dart';


Future<Device?> scanAndConnectDevice({bool autoConnect = true, bool timeout = false}) async {
  print('scanAndConnectDevice');
  var deviceId = SharedPreferencesUtil().btDeviceStruct?.id;
  print('scanAndConnectDevice ${deviceId}');
  for (var device in FlutterBluePlus.connectedDevices) {
    if (device.remoteId.str == deviceId) {
      return AnyDeviceType().createDeviceFromScan(device.platformName, device.remoteId.str, await device.readRssi());
    }
  }
  int timeoutCounter = 0;
  while (true) {
    if (timeout && timeoutCounter >= 10) return null;
    List<Device> foundDevices = await AnyDeviceType().findDevices();
    for (Device device in foundDevices) {
      // Remember the first connected device.
      // Technically, there should be only one
      if (deviceId == null || deviceId == '') {
        deviceId = device.id;
        SharedPreferencesUtil().btDeviceStruct = device;
        SharedPreferencesUtil().deviceName = device.name;
      }

      if (device.id == deviceId) {
        try {
          await device.connectDevice(autoConnect: autoConnect);
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
