import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device.dart';

StreamSubscription<OnConnectionStateChangedEvent>? getConnectionStateListener(
    {required String deviceId, required Function onDisconnected, required Function(BTDeviceStruct) onConnected}) {
  return FlutterBluePlus.events.onConnectionStateChanged.listen((event) async {
    debugPrint('onConnectionStateChanged: ${event.device.remoteId.str} ${event.connectionState}');
    if (event.device.remoteId.str == deviceId) {
      if (event.connectionState == BluetoothConnectionState.disconnected) {
        onDisconnected();
      } else if (event.connectionState == BluetoothConnectionState.connected) {
        onConnected(BTDeviceStruct(
          id: event.device.remoteId.str,
          name: event.device.platformName,
          rssi: await event.device.readRssi(),
          fwver: await event.device.discoverServices().then((services) =>
            services
              .map((service) => service.characteristics)
              .expand((element) => element)
              .firstWhere((characteristic) => characteristic.uuid.str == '00002a26-0000-1000-8000-00805f9b34fb')
              .read()
              .then((value) => value.toList()
          )),
        ));
      }
    }
  });
}
