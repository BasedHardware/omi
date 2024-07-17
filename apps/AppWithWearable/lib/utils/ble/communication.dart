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
      try {
        await canNotify.setNotifyValue(true);
      } catch (e, stackTrace) {
        debugPrint('Error setting notify value: $e');
        CrashReporting.reportHandledCrash(
          e,
          stackTrace,
          level: NonFatalExceptionLevel.error,
          userAttributes: {'deviceId': btDevice.id},
        );
        return null;
      }
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
  return service.characteristics.firstWhereOrNull(
    (characteristic) => characteristic.uuid.str128.toLowerCase() == uuid.toLowerCase(),
  );
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
    try {
      await streamCharacteristic.setNotifyValue(true); // device could be disconnected here.
    } catch (e, stackTrace) {
      debugPrint('Error setting notify value: $e');
      CrashReporting.reportHandledCrash(
        e,
        stackTrace,
        level: NonFatalExceptionLevel.error,
        userAttributes: {'deviceId': deviceId},
      );
      return null;
    }
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

Future cameraStartPhotoController(BTDeviceStruct btDevice) async {
  final bytesService = await getServiceByUuid(btDevice.id, '19b10000-e8f2-537e-4f6c-d104768a1214');
  var streamCharacteristic = getCharacteristicByUuid(bytesService!, '19B10006-E8F2-537E-4F6C-D104768A1214');
  await streamCharacteristic!.write([0x0A]);
  print('cameraStartPhotoController');
}

Future cameraStopPhotoController(BTDeviceStruct btDevice) async {
  final bytesService = await getServiceByUuid(btDevice.id, '19b10000-e8f2-537e-4f6c-d104768a1214');
  var streamCharacteristic = getCharacteristicByUuid(bytesService!, '19B10006-E8F2-537E-4F6C-D104768A1214');
  await streamCharacteristic!.write([0x00]);
  print('cameraStopPhotoController');
}

Future<bool> hasPhotoStreamingCharacteristic(String deviceId) async {
  final bytesService = await getServiceByUuid(deviceId, '19b10000-e8f2-537e-4f6c-d104768a1214');
  if (bytesService == null) return false;
  var streamCharacteristic = getCharacteristicByUuid(bytesService, '19b10005-e8f2-537e-4f6c-d104768a1214');
  return streamCharacteristic != null;
}

Future<StreamSubscription?> getBleImageBytesListener(
  String deviceId, {
  required void Function(List<int>) onImageBytesReceived,
}) async {
  final device = BluetoothDevice.fromId(deviceId);
  final bytesService = await getServiceByUuid(deviceId, '19b10000-e8f2-537e-4f6c-d104768a1214');
  if (bytesService == null) return null;
  var streamCharacteristic = getCharacteristicByUuid(bytesService, '19b10005-e8f2-537e-4f6c-d104768a1214');

  if (streamCharacteristic != null) {
    try {
      await streamCharacteristic.setNotifyValue(true); // device could be disconnected here.
    } catch (e, stackTrace) {
      debugPrint('Error setting notify value: $e');
      CrashReporting.reportHandledCrash(
        e,
        stackTrace,
        level: NonFatalExceptionLevel.error,
        userAttributes: {'deviceId': deviceId},
      );
      return null;
    }
    if (Platform.isAndroid) await device.requestMtu(512);

    debugPrint('Subscribed to imageBytes stream from Friend Device');
    var listener = streamCharacteristic.lastValueStream.listen((value) {
      if (value.isNotEmpty) onImageBytesReceived(value);
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
  return BleAudioCodec.pcm8; // unknown
}

Future<BleAudioCodec> getDeviceCodec(String deviceId) async {
  final bytesService = await getServiceByUuid(deviceId, audioBytesServiceUuid);

  if (bytesService == null) return _errorObtainingCodec(message: 'Audio bytes service not found');
  var streamCharacteristic = getCharacteristicByUuid(bytesService, '19b10001-e8f2-537e-4f6c-d104768a1214');
  var codecCharacteristic = getCharacteristicByUuid(bytesService, '19b10002-e8f2-537e-4f6c-d104768a1214');
  if (streamCharacteristic == null) return _errorObtainingCodec(message: 'Audio stream characteristic not found');
  if (codecCharacteristic == null) return _errorObtainingCodec(message: 'Audio codec characteristic not found');

  var codecId = 1;
  try {
    codecId = (await codecCharacteristic.read()).single;
  } catch (e, stackTrace) {
    debugPrint('Error reading codec characteristic: $e');
    return _errorObtainingCodec(message: 'Error reading codec characteristic');
  }
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
