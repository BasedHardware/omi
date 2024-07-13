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

const String batteryServiceUuid = '0000180f-0000-1000-8000-00805f9b34fb';
const String audioBytesServiceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';

Future<List<BluetoothService>> getBleServices(String deviceId) async {
  final device = BluetoothDevice.fromId(deviceId);
  try {
    return await device.discoverServices();
  } catch (e, stackTrace) {
    print(e);
    CrashReporting.reportHandledCrash(
      e,
      stackTrace,
      level: NonFatalExceptionLevel.error,
      userAttributes: {'deviceId': deviceId},
    );
    return [];
  }
}

Future<BluetoothService?> getServiceByUuid(String deviceId, String uuid) async {
  final services = await getBleServices(deviceId);
  return services.firstWhereOrNull((service) => service.uuid.str128.toLowerCase() == uuid);
}

Future<int> retrieveBatteryLevel(BTDeviceStruct btDevice) async {
  final batteryService = await getServiceByUuid(btDevice.id, batteryServiceUuid);

  if (batteryService == null) return -1;
  var canRead = batteryService.characteristics.firstWhereOrNull((characteristic) => characteristic.properties.read);
  var currValue = await canRead?.read();
  if (currValue != null && currValue.isNotEmpty) return currValue[0];
  return -1;
}

Future<StreamSubscription<List<int>>?> getBleBatteryLevelListener(
  BTDeviceStruct btDevice, {
  void Function(int)? onBatteryLevelChange,
}) async {
  final batteryService = await getServiceByUuid(btDevice.id, batteryServiceUuid);
  if (batteryService == null) return null;

  var canRead = batteryService.characteristics.firstWhereOrNull((characteristic) => characteristic.properties.read);
  if (canRead != null) {
    var currValue = await canRead.read();
    if (currValue.isNotEmpty) {
      debugPrint('Battery level: ${currValue[0]}');
      onBatteryLevelChange!(currValue[0]);
    }

    var canNotify =
        batteryService.characteristics.firstWhereOrNull((characteristic) => characteristic.properties.notify);
    if (canNotify != null) {
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

BluetoothCharacteristic? getCharacteristicByUuid(BluetoothService service, String uuid) {
  return service.characteristics.firstWhereOrNull((characteristic) => characteristic.uuid.str128.toLowerCase() == uuid);
}

Future<StreamSubscription?> getBleAudioBytesListener(
  String deviceId, {
  required void Function(List<int>) onAudioBytesReceived,
}) async {
  final device = BluetoothDevice.fromId(deviceId);
  final bytesService = await getServiceByUuid(deviceId, audioBytesServiceUuid);

  if (bytesService == null) return null;
  var streamCharacteristic = getCharacteristicByUuid(bytesService, '19b10001-e8f2-537e-4f6c-d104768a1214');
  var codecCharacteristic = getCharacteristicByUuid(bytesService, '19b10002-e8f2-537e-4f6c-d104768a1214');

  if (streamCharacteristic != null && codecCharacteristic != null) {
    await streamCharacteristic.setNotifyValue(true);
    if (Platform.isAndroid) await device.requestMtu(512); // FORCING REQUEST AGAIN OF MTU

    debugPrint('Subscribed to audioBytes stream from Friend Device');
    var listener = streamCharacteristic.lastValueStream.listen((value) {
      if (value.isNotEmpty) onAudioBytesReceived(value);
    });
    device.cancelWhenDisconnected(listener);
    return listener;
  }
  debugPrint('Desired audio characteristic not found');
  return null;
}

enum BleAudioCodec { pcm16, pcm8, mulaw16, mulaw8, opus, unknown }

_errorObtainingCodec({
  String message = 'Desired audio characteristic not found',
}) {
  debugPrint(message);
  CrashReporting.reportHandledCrash(
    Exception(message),
    StackTrace.current,
    level: NonFatalExceptionLevel.error,
  );
  return BleAudioCodec.unknown;
}

Future<BleAudioCodec> getDeviceCodec(String deviceId) async {
  final bytesService = await getServiceByUuid(deviceId, audioBytesServiceUuid);

  if (bytesService == null) return _errorObtainingCodec(message: 'Audio bytes service not found');
  var streamCharacteristic = getCharacteristicByUuid(bytesService, '19b10001-e8f2-537e-4f6c-d104768a1214');
  var codecCharacteristic = getCharacteristicByUuid(bytesService, '19b10002-e8f2-537e-4f6c-d104768a1214');
  if (streamCharacteristic == null) return _errorObtainingCodec(message: 'Audio stream characteristic not found');
  if (codecCharacteristic == null) return _errorObtainingCodec(message: 'Audio codec characteristic not found');

  debugPrint('codecCharacteristic: ${await codecCharacteristic.read()}');
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
      return _errorObtainingCodec(message: 'Unknown codec id: $codecId');
  }
  debugPrint('Codec is $codec');
  return codec;
}
