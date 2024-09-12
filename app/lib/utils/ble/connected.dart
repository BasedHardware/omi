import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/logger.dart';

Future<BTDeviceStruct?> getConnectedDevice() async {
  var deviceId = SharedPreferencesUtil().btDeviceStruct.id;
  for (var device in FlutterBluePlus.connectedDevices) {
    if (device.remoteId.str == deviceId) {
      try {
        int rssi = await device.readRssi();
        return BTDeviceStruct(
          id: device.remoteId.str,
          name: device.platformName,
          rssi: rssi,
          type: SharedPreferencesUtil().btDeviceStruct.type,
        );
      } catch (e) {
        debugPrint('Error reading RSSI: $e');
        debugPrint('Device is disconnected');
        Logger.handle(e, StackTrace.current,
            message: 'Oops! Looks like the device is disconnected. Please connect to the device and try again.');
        return null;
      }
    }
  }
  debugPrint('getConnectedDevice: device not found');
  return null;
}

StreamSubscription<OnConnectionStateChangedEvent>? getConnectionStateListener({
  required String deviceId,
  required Function onDisconnected,
  required Function(BTDeviceStruct) onConnected,
}) {
  return FlutterBluePlus.events.onConnectionStateChanged.listen((event) async {
    debugPrint('onConnectionStateChanged: ${event.device.remoteId.str} ${event.connectionState}');
    if (event.device.remoteId.str == deviceId) {
      if (event.connectionState == BluetoothConnectionState.disconnected) {
        onDisconnected();
      } else if (event.connectionState == BluetoothConnectionState.connected) {
        print('Connected to ${event.device.platformName}');
        try {
          // FIXME: Reading RSSI value takes time and it shouldn't be done inside of a listener. Instead move it to somehwere else @mdmohsin7
          // This is a note for the future.
          int rssi = await event.device.readRssi();
          onConnected(BTDeviceStruct(
            id: event.device.remoteId.str,
            name: event.device.platformName,
            rssi: rssi,
            // TODO: add firmware version
          ));
        } catch (e) {
          debugPrint('Error reading RSSI, device disconnected by the time rssi was read: $e');
        }
      }
    }
  });
}
