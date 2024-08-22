import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/devices/device.dart';
import 'package:friend_private/devices/deviceType.dart';

Future<Device?> getConnectedDevice() async {
  var deviceId = SharedPreferencesUtil().btDeviceStruct?.id;
  for (var device in FlutterBluePlus.connectedDevices) {
    if (device.remoteId.str == deviceId) {
      return AnyDeviceType().createDeviceFromScan(device.platformName, device.remoteId.str, await device.readRssi());
    }
  }
  debugPrint('getConnectedDevice: device not found');
  return null;
}

StreamSubscription<OnConnectionStateChangedEvent>? getConnectionStateListener({
  required String deviceId,
  required Function onDisconnected,
  required Function(Device) onConnected,
}) {
  return FlutterBluePlus.events.onConnectionStateChanged.listen((event) async {
    debugPrint('onConnectionStateChanged: ${event.device.remoteId.str} ${event.connectionState}');
    if (event.device.remoteId.str == deviceId) {
      if (event.connectionState == BluetoothConnectionState.disconnected) {
        onDisconnected();
      } else if (event.connectionState == BluetoothConnectionState.connected) {
        print('Connected to ${event.device.platformName}');
        onConnected(AnyDeviceType().createDeviceFromScan(event.device.platformName, event.device.remoteId.str, await event.device.readRssi()));
      }
    }
  });
}
