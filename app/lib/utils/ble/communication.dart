import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/device_base.dart';
import 'package:friend_private/utils/ble/frame_communication.dart';
import 'package:friend_private/utils/ble/friend_communication.dart';


Map<String, DeviceBase> deviceMap = {};
Future<DeviceBase?> getDevice(String deviceId) async {
  if (deviceMap.containsKey(deviceId)) {
    return deviceMap[deviceId];
  } else {
    if (!deviceTypeMap.containsKey(deviceId)) {
      final deviceType = await getTypeOfBluetoothDevice(BluetoothDevice.fromId(deviceId));
      if (deviceType != null) {
        deviceTypeMap[deviceId] = deviceType;
      } else {
        return null;
      }
    }

    final deviceType = deviceTypeMap[deviceId];
    if (deviceType == DeviceType.friend) {
      deviceMap[deviceId] = FriendDevice(deviceId);
    } else if (deviceType == DeviceType.openglass) {
      deviceMap[deviceId] = FriendDevice(deviceId);
    } else if (deviceType == DeviceType.frame) {
      deviceMap[deviceId] = FrameDevice(deviceId);
    }
    return deviceMap[deviceId];
  }
}

Future<int> retrieveBatteryLevel(String deviceId) async =>
    (await getDevice(deviceId))?.retrieveBatteryLevel() ?? Future.value(-1);

Future<StreamSubscription<List<int>>?> getBleBatteryLevelListener(
  String deviceId, {
  void Function(int)? onBatteryLevelChange,
}) async =>
    (await getDevice(deviceId))?.getBleBatteryLevelListener(
            onBatteryLevelChange: onBatteryLevelChange) ??
        Future.value(null);

Future<StreamSubscription?> getBleAudioBytesListener(
  String deviceId, {
  required void Function(List<int>) onAudioBytesReceived,
}) async =>
    (await getDevice(deviceId))?.getBleAudioBytesListener(
            onAudioBytesReceived: onAudioBytesReceived) ??
        Future.value(null);

Future<BleAudioCodec> getAudioCodec(String deviceId) async =>
    (await getDevice(deviceId))?.getAudioCodec() ?? Future.value(BleAudioCodec.pcm8); 

Future cameraStartPhotoController(String deviceId) async =>
    (await getDevice(deviceId))?.cameraStartPhotoController() ?? Future.value(null);

Future cameraStopPhotoController(String deviceId) async =>
    (await getDevice(deviceId))?.cameraStopPhotoController() ?? Future.value(null);

Future<bool> hasPhotoStreamingCharacteristic(String deviceId) async =>
    (await getDevice(deviceId))?.hasPhotoStreamingCharacteristic() ?? Future.value(false);

Future<StreamSubscription?> getImageListener(
  String deviceId, {
  required void Function(Uint8List base64JpgData) onImageReceived,
}) async =>
    (await getDevice(deviceId))?.getImageListener(
            onImageReceived: onImageReceived) ??
        Future.value(null);

Future<StreamSubscription<List<int>>?> getAccelListener(
  String deviceId, {
  void Function(int)? onAccelChange,
}) async =>
    (await getDevice(deviceId))?.getAccelListener(
            onAccelChange: onAccelChange) ??
        Future.value(null);
