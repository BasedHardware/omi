import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

// Future<String?> bleReceiveData(BTDeviceStruct btDevice) async {
//   final device = BluetoothDevice.fromId(btDevice.id);
//   final services = await device.discoverServices();
//   for (BluetoothService service in services) {
//     for (BluetoothCharacteristic characteristic in service.characteristics) {
//       final isRead = characteristic.properties.read;
//       final isNotify = characteristic.properties.notify;
//       if (isRead && isNotify) {
//         final value = await characteristic.read();
//         return String.fromCharCodes(value);
//       }
//     }
//   }
//   return null;
// }
//
// Future bleSendData(BTDeviceStruct btDevice, String data) async {
//   final device = BluetoothDevice.fromId(btDevice.id);
//   final services = await device.discoverServices();
//   for (BluetoothService service in services) {
//     for (BluetoothCharacteristic characteristic in service.characteristics) {
//       final isWrite = characteristic.properties.write;
//       if (isWrite) {
//         await characteristic.write(data.codeUnits);
//       }
//     }
//   }
// }

Future<int> retrieveBatteryLevel(BTDeviceStruct btDevice) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  final services = await device.discoverServices();
  final batteryService = services
      .firstWhereOrNull((service) => service.uuid.str128.toLowerCase() == '0000180f-0000-1000-8000-00805f9b34fb');
  if (batteryService != null) {
    var canRead = batteryService.characteristics.firstWhereOrNull((characteristic) => characteristic.properties.read);
    debugPrint('batteryLevelCharacteristic: ${canRead?.uuid.str128.toLowerCase()} ${canRead?.properties}');
    debugPrint('batteryLevelCharacteristic value: ${await canRead?.read()}');
    if (canRead != null) {
      var currValue = (await canRead.read()).single;
      debugPrint('Battery level: $currValue');
      return currValue;
    }
  }
  return -1;
}

Future<StreamSubscription<List<int>>?> getBleBatteryLevelListener(
  BTDeviceStruct btDevice, {
  void Function(int)? onBatteryLevelChange,
}) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  final services = await device.discoverServices();
  final batteryService = services
      .firstWhereOrNull((service) => service.uuid.str128.toLowerCase() == '0000180f-0000-1000-8000-00805f9b34fb');
  if (batteryService != null) {
    var canRead = batteryService.characteristics.firstWhereOrNull((characteristic) => characteristic.properties.read);
    var canNotify =
        batteryService.characteristics.firstWhereOrNull((characteristic) => characteristic.properties.notify);
    debugPrint('batteryLevelCharacteristic value: ${await canRead?.read()}');
    if (canRead != null && canNotify != null) {
      var currValue = (await canRead.read()).single;
      debugPrint('Battery level: $currValue');
      onBatteryLevelChange!(currValue);
      await canNotify.setNotifyValue(true);
      return canNotify.lastValueStream.listen((value) {
        // debugPrint('Battery level listener: $value');
        if (value.isNotEmpty) {
          onBatteryLevelChange!(value[0]);
        }
      });
    }
  }
  return null;
}

Future<StreamSubscription?> getBleAudioBytesListener(
  String deviceId, {
  required void Function(List<int>) onAudioBytesReceived,
}) async {
  final device = BluetoothDevice.fromId(deviceId);
  final services = await device.discoverServices();
  final bytesService = services
      .firstWhereOrNull((service) => service.uuid.str128.toLowerCase() == '19b10000-e8f2-537e-4f6c-d104768a1214');

  if (bytesService != null) {
    var streamCharacteristic = bytesService.characteristics.firstWhereOrNull(
        (characteristic) => characteristic.uuid.str128.toLowerCase() == '19b10001-e8f2-537e-4f6c-d104768a1214');
    var codecCharacteristic = bytesService.characteristics.firstWhereOrNull(
        (characteristic) => characteristic.uuid.str128.toLowerCase() == '19b10002-e8f2-537e-4f6c-d104768a1214');
    if (streamCharacteristic != null && codecCharacteristic != null) {
      await streamCharacteristic.setNotifyValue(true);
      if (Platform.isAndroid) await device.requestMtu(512); // FORCING REQUEST AGAIN OF MTU
      debugPrint('Subscribed to audioBytes stream from Friend Device');
      var listener = streamCharacteristic.lastValueStream.listen((value) {
        // debugPrint('lastValueStream: ${value.length} ~ mtu: ${device.mtuNow}');
        if (value.isNotEmpty) onAudioBytesReceived(value);
      });
      device.cancelWhenDisconnected(listener);
      return listener;
    }
  }
  debugPrint('Desired audio characteristic not found');
  return null;
}

enum BleAudioCodec { pcm16, pcm8, mulaw16, mulaw8, opus, unknown }

Future<BleAudioCodec> getDeviceCodec(String deviceId) async {
  final device = BluetoothDevice.fromId(deviceId);
  final services = await device.discoverServices();
  final bytesService = services
      .firstWhereOrNull((service) => service.uuid.str128.toLowerCase() == '19b10000-e8f2-537e-4f6c-d104768a1214');

  if (bytesService != null) {
    var canNotify = bytesService.characteristics.firstWhereOrNull(
        (characteristic) => characteristic.uuid.str128.toLowerCase() == '19b10001-e8f2-537e-4f6c-d104768a1214');
    var codecCharacteristic = bytesService.characteristics.firstWhereOrNull(
        (characteristic) => characteristic.uuid.str128.toLowerCase() == '19b10002-e8f2-537e-4f6c-d104768a1214');
    debugPrint('codecCharacteristic: ${await codecCharacteristic?.read()}');
    if (canNotify != null && codecCharacteristic != null) {
      var codecId = (await codecCharacteristic.read()).single;
      BleAudioCodec codec;
      switch (codecId) {
        // case 0:
        //   codec = BleAudioCodec.pcm16;
        case 1:
          codec = BleAudioCodec.pcm8; // INITIAL CODEC FOR ALL DEVICES
        // case 10:
        //   codec = BleAudioCodec.mulaw16;
        // case 11:
        //   codec = BleAudioCodec.mulaw8;
        case 20:
          codec = BleAudioCodec.opus;
        default:
          CrashReporting.reportHandledCrash(Exception('Unknown codec $codecId'), StackTrace.current,
              level: NonFatalExceptionLevel.error);
          throw Exception('Non handled codec yet $codecId');
      }
      debugPrint('Codec is $codec');
      return codec;
    }
  }
  debugPrint('Desired audio characteristic not found');
  CrashReporting.reportHandledCrash(Exception('Desired audio characteristic not found'), StackTrace.current,
      level: NonFatalExceptionLevel.error);
  throw Exception('Desired audio characteristic not found');
}
