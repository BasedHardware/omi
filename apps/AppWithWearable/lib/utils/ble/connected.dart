import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import '/backend/schema/structs/index.dart';
import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';

Future<List<BTDeviceStruct>> getConnectedDevices({includeRssi = true}) async {
  final connectedDevices = FlutterBluePlus.connectedDevices;
  List<BTDeviceStruct> devices = [];

  for (var device in connectedDevices) {
    devices.add(BTDeviceStruct(
      name: device.advName,
      id: device.remoteId.str,
      rssi: includeRssi ? (await device.readRssi()) : null,
    ));
  }
  return devices;
}

StreamSubscription<BluetoothConnectionState>? getConnectionStateListener(
    String deviceId, Function onDisconnect, Function onConnect) {
  BluetoothDevice? connectedDevice =
      (FlutterBluePlus.connectedDevices).firstWhereOrNull((e) => e.remoteId.str == deviceId);
  if (connectedDevice == null) {
    return null;
  }
  StreamSubscription<BluetoothConnectionState>? connectionStateListener =
      connectedDevice.connectionState.listen((event) {
    debugPrint('connectionStateListener: $event');
    if (event == BluetoothConnectionState.disconnected) {
      onDisconnect();
    } else if (event == BluetoothConnectionState.connected) {
      onConnect();
    }
  });
  return connectionStateListener;
}
