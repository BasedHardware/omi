import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/errors.dart';
import 'package:friend_private/utils/ble/gatt_utils.dart';

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
  if (currValue.isNotEmpty) return currValue[0];
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

  // debugPrint('Codec is $codec');
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
