import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '/backend/schema/structs/index.dart';

Future<String?> bleReceiveData(BTDeviceStruct btdevice) async {
  final device = BluetoothDevice.fromId(btdevice.id);
  final services = await device.discoverServices();
  for (BluetoothService service in services) {
    for (BluetoothCharacteristic characteristic in service.characteristics) {
      final isRead = characteristic.properties.read;
      final isNotify = characteristic.properties.notify;
      if (isRead && isNotify) {
        final value = await characteristic.read();
        return String.fromCharCodes(value);
      }
    }
  }
  return null;
}

Future<StreamSubscription?> getBleBatteryLevelListener(
  BTDeviceStruct btDevice, {
  void Function(int)? onBatteryLevelChange,
}) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  // 0000180f-0000-1000-8000-00805f9b34fb
  final services = await device.discoverServices();
  final batteryService = services
      .firstWhereOrNull((service) => service.uuid.str128.toLowerCase() == '0000180f-0000-1000-8000-00805f9b34fb');
  if (batteryService != null) {
    var canRead = batteryService.characteristics.firstWhereOrNull((characteristic) => characteristic.properties.read);
    var currValue = await canRead?.read();
    if (currValue != null && currValue.isNotEmpty) {
      onBatteryLevelChange!(currValue[0]);
    }
    var canNotify =
        batteryService.characteristics.firstWhereOrNull((characteristic) => characteristic.properties.notify);
    if (canRead != null && canNotify != null) {
      // let percent = (await batteryChar.read())[0];
      await canNotify.setNotifyValue(true);
      return canNotify.lastValueStream.listen((value) {
        debugPrint('Battery level listener: $value');
        if (value.isNotEmpty) {
          onBatteryLevelChange!(value[0]);
        }
      });
    }
  }
  return null;
}

Future bleSendData(BTDeviceStruct btDevice, String data) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  final services = await device.discoverServices();
  for (BluetoothService service in services) {
    for (BluetoothCharacteristic characteristic in service.characteristics) {
      final isWrite = characteristic.properties.write;
      if (isWrite) {
        await characteristic.write(data.codeUnits);
      }
    }
  }
}
