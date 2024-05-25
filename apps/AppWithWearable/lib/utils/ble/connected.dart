import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';

StreamSubscription<BluetoothConnectionState>? getConnectionStateListener(
    String deviceId, Function onDisconnect, Function onConnect) {
  BluetoothDevice? connectedDevice =
      (FlutterBluePlus.connectedDevices).firstWhereOrNull((e) => e.remoteId.str == deviceId);
  if (connectedDevice == null) return null;

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
