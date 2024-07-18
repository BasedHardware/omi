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
const String batteryLevelCharacteristicUuid = '00002a19-0000-1000-8000-00805f9b34fb';

const String audioBytesServiceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';

const String audioStreamCharacteristicUuid = '19b10001-e8f2-537e-4f6c-d104768a1214';
const String audioCodecCharacteristicUuid = '19b10002-e8f2-537e-4f6c-d104768a1214';

const String imageCaptureDataCharacteristicUuid = '19b10005-e8f2-537e-4f6c-d104768a1214';
const String imageCaptureControlCharacteristicUuid = '19b10006-e8f2-537e-4f6c-d104768a1214';

Future<List<BluetoothService>> getBleServices(String deviceId) async {
  final device = BluetoothDevice.fromId(deviceId);
  try {
    if (device.servicesList.isNotEmpty) return device.servicesList;
    var services = await device.discoverServices();
    await Future.delayed(const Duration(milliseconds: 500));
    return services;
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
  var batteryLevelCharacteristic = getCharacteristicByUuid(batteryService, batteryLevelCharacteristicUuid);
  if (batteryLevelCharacteristic != null) {
    var currValue = await batteryLevelCharacteristic.read();
    if (currValue.isNotEmpty) return currValue[0];
  }
  return -1;
}

Future<StreamSubscription<List<int>>?> getBleBatteryLevelListener(
  BTDeviceStruct btDevice, {
  void Function(int)? onBatteryLevelChange,
}) async {
  final batteryService = await getServiceByUuid(btDevice.id, batteryServiceUuid);
  if (batteryService == null) return null;
  var batteryLevelCharacteristic = getCharacteristicByUuid(batteryService, batteryLevelCharacteristicUuid);
  if (batteryLevelCharacteristic != null) {
    var currValue = await batteryLevelCharacteristic.read();
    if (currValue.isNotEmpty) {
      debugPrint('Battery level: ${currValue[0]}');
      onBatteryLevelChange!(currValue[0]);
    }

    try {
      await batteryLevelCharacteristic.setNotifyValue(true);
    } catch (e, stackTrace) {
      debugPrint('Error setting battery notify value: $e');
      CrashReporting.reportHandledCrash(
        e,
        stackTrace,
        level: NonFatalExceptionLevel.error,
        userAttributes: {'deviceId': btDevice.id},
      );
      return null;
    }
    return batteryLevelCharacteristic.lastValueStream.listen((value) {
      // debugPrint('Battery level listener: $value');
      if (value.isNotEmpty) {
        onBatteryLevelChange!(value[0]);
      }
    });
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
  final friendService = await getServiceByUuid(deviceId, audioBytesServiceUuid);

  if (friendService == null) return null;
  var audioStreamCharacteristic = getCharacteristicByUuid(friendService, audioStreamCharacteristicUuid);

  if (audioStreamCharacteristic != null) {
    try {
      await audioStreamCharacteristic.setNotifyValue(true); // device could be disconnected here.
    } catch (e, stackTrace) {
      debugPrint('Error setting audio notify value: $e');
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
    var listener = audioStreamCharacteristic.lastValueStream.listen((value) {
      if (value.isNotEmpty) onAudioBytesReceived(value);
    });

    device.cancelWhenDisconnected(listener);
    return listener;
  }

  debugPrint('Desired audio characteristic not found');
  return null;
}

Future cameraStartPhotoController(BTDeviceStruct btDevice) async {
  final bytesService = await getServiceByUuid(btDevice.id, audioBytesServiceUuid);
  if (bytesService == null) return;
  var imageCaptureControlCharacteristic = getCharacteristicByUuid(bytesService!, imageCaptureControlCharacteristicUuid);
  if (imageCaptureControlCharacteristic != null) {
    // Capture photo once every 10s
    await imageCaptureControlCharacteristic!.write([0x0A]);
  }
  print('cameraStartPhotoController');
}

Future cameraStopPhotoController(BTDeviceStruct btDevice) async {
  final bytesService = await getServiceByUuid(btDevice.id, audioBytesServiceUuid);
  if (bytesService == null) return;
  var imageCaptureControlCharacteristic = getCharacteristicByUuid(bytesService!, imageCaptureControlCharacteristicUuid);
  if (imageCaptureControlCharacteristic != null) {
    await imageCaptureControlCharacteristic.write([0x00]);
  }
  print('cameraStopPhotoController');
}

Future<bool> hasPhotoStreamingCharacteristic(String deviceId) async {
  final bytesService = await getServiceByUuid(deviceId, audioBytesServiceUuid);
  if (bytesService == null) return false;
  var imageCaptureControlCharacteristic = getCharacteristicByUuid(bytesService, imageCaptureDataCharacteristicUuid);
  return imageCaptureControlCharacteristic != null;
}

Future<StreamSubscription?> getBleImageBytesListener(
  String deviceId, {
  required void Function(List<int>) onImageBytesReceived,
}) async {
  final device = BluetoothDevice.fromId(deviceId);
  final bytesService = await getServiceByUuid(deviceId, audioBytesServiceUuid);
  if (bytesService == null) return null;
  var imageStreamCharacteristic = getCharacteristicByUuid(bytesService, imageCaptureDataCharacteristicUuid);

  if (imageStreamCharacteristic != null) {
    try {
      await imageStreamCharacteristic.setNotifyValue(true); // device could be disconnected here.
    } catch (e, stackTrace) {
      debugPrint('Error setting image notify value: $e');
      CrashReporting.reportHandledCrash(
        e,
        stackTrace,
        level: NonFatalExceptionLevel.error,
        userAttributes: {'deviceId': deviceId},
      );
      return null;
    }
    // if (Platform.isAndroid) await device.requestMtu(512);

    debugPrint('Subscribed to imageBytes stream from Friend Device');
    var listener = imageStreamCharacteristic.lastValueStream.listen((value) {
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
  var audioCodecCharacteristic = getCharacteristicByUuid(bytesService, audioCodecCharacteristicUuid);
  if (audioCodecCharacteristic == null) return _errorObtainingCodec(message: 'Audio codec characteristic not found');

  var codecId = 1;
  var codecValue = await audioCodecCharacteristic.read();
  if (codecValue.isNotEmpty) {
    codecId = codecValue[0];
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
