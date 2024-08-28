import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device.dart';

Future<void> bleConnectDevice(String deviceId, {bool autoConnect = true}) async {
  final device = BluetoothDevice.fromId(deviceId);
  try {
    if (!autoConnect) return await device.connect(autoConnect: false, mtu: null);

    // Step 1: Connect with autoConnect
    await device.connect(autoConnect: true, mtu: null);
    // Step 2: Listen to the connection state to ensure the device is connected
    await device.connectionState.where((state) => state == BluetoothConnectionState.connected).first;

    // Step 3: Request the desired MTU size if the platform is Android
    if (Platform.isAndroid) await device.requestMtu(512);
  } catch (e) {
    debugPrint('bleConnectDevice failed: $e');
  }
}

Future bleDisconnectDevice(BTDeviceStruct btDevice) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  try {
    await device.disconnect(queue: false);
  } catch (e) {
    debugPrint('bleDisconnectDevice failed: $e');
  }
}
