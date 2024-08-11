import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/gatt_utils.dart';

import 'package:friend_private/utils/ble/errors.dart';

Future<int> retrieveBatteryLevel(String deviceId) async {
  final batteryService = await getServiceByUuid(deviceId, batteryServiceUuid);
  if (batteryService == null) {
    logServiceNotFoundError('Battery', deviceId);
    return -1;
  }

  var batteryLevelCharacteristic = getCharacteristicByUuid(batteryService, batteryLevelCharacteristicUuid);
  if (batteryLevelCharacteristic == null) {
    logCharacteristicNotFoundError('Battery level', deviceId);
    return -1;
  }

  var currValue = await batteryLevelCharacteristic.read();
  if (currValue.isNotEmpty) {
    return currValue[0];
  }

  return -1;
}

Future<StreamSubscription<List<int>>?> getBleBatteryLevelListener(
  String deviceId, {
  void Function(int)? onBatteryLevelChange,
}) async {
  final batteryService = await getServiceByUuid(deviceId, batteryServiceUuid);
  if (batteryService == null) {
    logServiceNotFoundError('Battery', deviceId);
    return null;
  }

  var batteryLevelCharacteristic = getCharacteristicByUuid(batteryService, batteryLevelCharacteristicUuid);
  if (batteryLevelCharacteristic == null) {
    logCharacteristicNotFoundError('Battery level', deviceId);
    return null;
  }

  var currValue = await batteryLevelCharacteristic.read();
  if (currValue.isNotEmpty) {
    debugPrint('Battery level: ${currValue[0]}');
    onBatteryLevelChange!(currValue[0]);
  }

  try {
    await batteryLevelCharacteristic.setNotifyValue(true);
  } catch (e, stackTrace) {
    logSubscribeError('Battery level', deviceId, e, stackTrace);
    return null;
  }

  var listener = batteryLevelCharacteristic.lastValueStream.listen((value) {
    // debugPrint('Battery level listener: $value');
    if (value.isNotEmpty) {
      onBatteryLevelChange!(value[0]);
    }
  });

  final device = BluetoothDevice.fromId(deviceId);
  device.cancelWhenDisconnected(listener);

  return listener;
}

Future<StreamSubscription?> getBleAudioBytesListener(
  String deviceId, {
  required void Function(List<int>) onAudioBytesReceived,
}) async {
  final friendService = await getServiceByUuid(deviceId, friendServiceUuid);
  if (friendService == null) {
    logServiceNotFoundError('Friend', deviceId);
    return null;
  }

  var audioDataStreamCharacteristic = getCharacteristicByUuid(friendService, audioDataStreamCharacteristicUuid);
  if (audioDataStreamCharacteristic == null) {
    logCharacteristicNotFoundError('Audio data stream', deviceId);
    return null;
  }

  try {
    await audioDataStreamCharacteristic.setNotifyValue(true); // device could be disconnected here.
  } catch (e, stackTrace) {
    logSubscribeError('Audio data stream', deviceId, e, stackTrace);
    return null;
  }

  debugPrint('Subscribed to audioBytes stream from Friend Device');
  var listener = audioDataStreamCharacteristic.lastValueStream.listen((value) {
    if (value.isNotEmpty) onAudioBytesReceived(value);
  });

  final device = BluetoothDevice.fromId(deviceId);
  device.cancelWhenDisconnected(listener);

  // This will cause a crash in OpenGlass devices
  // due to a race with discoverServices() that triggers
  // a bug in the device firmware.
  if (Platform.isAndroid) await device.requestMtu(512);

  return listener;
}

enum BleAudioCodec { pcm16, pcm8, mulaw16, mulaw8, opus, unknown }

Future<BleAudioCodec> getAudioCodec(String deviceId) async {
  final friendService = await getServiceByUuid(deviceId, friendServiceUuid);
  if (friendService == null) {
    logServiceNotFoundError('Friend', deviceId);
    return BleAudioCodec.pcm8;
  }

  var audioCodecCharacteristic = getCharacteristicByUuid(friendService, audioCodecCharacteristicUuid);
  if (audioCodecCharacteristic == null) {
    logCharacteristicNotFoundError('Audio codec', deviceId);
    return BleAudioCodec.pcm8;
  }

  // Default codec is PCM8
  var codecId = 1;
  BleAudioCodec codec = BleAudioCodec.pcm8;

  var codecValue = await audioCodecCharacteristic.read();
  if (codecValue.isNotEmpty) {
    codecId = codecValue[0];
  }

  switch (codecId) {
    // case 0:
    //   codec = BleAudioCodec.pcm16;
    case 1:
      codec = BleAudioCodec.pcm8;
    // case 10:
    //   codec = BleAudioCodec.mulaw16;
    // case 11:
    //   codec = BleAudioCodec.mulaw8;
    case 20:
      codec = BleAudioCodec.opus;
    default:
      logErrorMessage('Unknown codec id: $codecId', deviceId);
  }

  debugPrint('Codec is $codec');
  return codec;
}

Future cameraStartPhotoController(String deviceId) async {
  final friendService = await getServiceByUuid(deviceId, friendServiceUuid);
  if (friendService == null) {
    logServiceNotFoundError('Friend', deviceId);
    return;
  }

  var imageCaptureControlCharacteristic = getCharacteristicByUuid(friendService, imageCaptureControlCharacteristicUuid);
  if (imageCaptureControlCharacteristic == null) {
    logCharacteristicNotFoundError('Image capture control', deviceId);
    return;
  }

  // Capture photo once every 10s
  await imageCaptureControlCharacteristic.write([0x0A]);

  print('cameraStartPhotoController');
}

Future cameraStopPhotoController(String deviceId) async {
  final friendService = await getServiceByUuid(deviceId, friendServiceUuid);
  if (friendService == null) {
    logServiceNotFoundError('Friend', deviceId);
    return;
  }

  var imageCaptureControlCharacteristic = getCharacteristicByUuid(friendService, imageCaptureControlCharacteristicUuid);
  if (imageCaptureControlCharacteristic == null) {
    logCharacteristicNotFoundError('Image capture control', deviceId);
    return;
  }

  await imageCaptureControlCharacteristic.write([0x00]);

  print('cameraStopPhotoController');
}

Future<bool> hasPhotoStreamingCharacteristic(String deviceId) async {
  final friendService = await getServiceByUuid(deviceId, friendServiceUuid);
  if (friendService == null) {
    logServiceNotFoundError('Friend', deviceId);
    return false;
  }
  var imageCaptureControlCharacteristic = getCharacteristicByUuid(friendService, imageDataStreamCharacteristicUuid);
  return imageCaptureControlCharacteristic != null;
}

Future<StreamSubscription?> getBleImageBytesListener(
  String deviceId, {
  required void Function(List<int>) onImageBytesReceived,
}) async {
  final friendService = await getServiceByUuid(deviceId, friendServiceUuid);
  if (friendService == null) {
    logServiceNotFoundError('Friend', deviceId);
    return null;
  }

  var imageStreamCharacteristic = getCharacteristicByUuid(friendService, imageDataStreamCharacteristicUuid);
  if (imageStreamCharacteristic == null) {
    logCharacteristicNotFoundError('Image data stream', deviceId);
    return null;
  }

  try {
    await imageStreamCharacteristic.setNotifyValue(true); // device could be disconnected here.
  } catch (e, stackTrace) {
    logSubscribeError('Image data stream', deviceId, e, stackTrace);
    return null;
  }

  debugPrint('Subscribed to imageBytes stream from Friend Device');
  var listener = imageStreamCharacteristic.lastValueStream.listen((value) {
    if (value.isNotEmpty) onImageBytesReceived(value);
  });

  final device = BluetoothDevice.fromId(deviceId);
  device.cancelWhenDisconnected(listener);

  // This will cause a crash in OpenGlass devices
  // due to a race with discoverServices() that triggers
  // a bug in the device firmware.
  // if (Platform.isAndroid) await device.requestMtu(512);

  return listener;
}

Future<StreamSubscription<List<int>>?> getAccelListener(
  String deviceId, {
  void Function(int)? onAccelChange,
}) async {
  final accelService = await getServiceByUuid(deviceId, accelDataStreamServiceUuid);
  if (accelService == null) {
    logServiceNotFoundError('Accelerometer', deviceId);
    return null;
  }

  var accelCharacteristic = getCharacteristicByUuid(accelService, accelDataStreamCharacteristicUuid);
  if (accelCharacteristic == null) {
    logCharacteristicNotFoundError('Accelerometer', deviceId);
    return null;
  }

  var currValue = await accelCharacteristic.read();
  if (currValue.isNotEmpty) {
    debugPrint('Accelerometer level: ${currValue[0]}');
    onAccelChange!(currValue[0]);
  }

  try {
    await accelCharacteristic.setNotifyValue(true);
  } catch (e, stackTrace) {
    logSubscribeError('Accelerometer level', deviceId, e, stackTrace);
    return null;
  }

  var listener = accelCharacteristic.lastValueStream.listen((value) {
    // debugPrint('Battery level listener: $value');
    int result = 100;
    int temp = 100;
    if (value.length > 4) { //for some reason, the very first reading is four bytes


    if (value.isNotEmpty) {
       onAccelChange!(value[0]);
      result = (value[0] | (value[1] << 8) | (value[2] << 16) | (value[3] << 24));
      //temp = value[0][0];
      temp = value[4];
      temp = (value[4] | (value[5] << 8) | (value[6] << 16) | (value[7] << 24));
       if (value[0] > 127) { 
       result = ~result & 0xFFFF;  
       result += 1; 
       result = -result; 

       temp = ~temp & 0xFFFF;  
       temp += 1; 
       temp = -temp;      
       }
       double x = result + (temp / 1000000);
   //    debugPrint('Accelerometer reading: $value');
      // debugPrint('first reading: $result');
       debugPrint('result: $x');
      }
    //   debugPrint('Accelerometer reading: $value');


    }
    });

  final device = BluetoothDevice.fromId(deviceId);
  device.cancelWhenDisconnected(listener);

  return listener;
}