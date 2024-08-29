import 'dart:async';
import 'dart:typed_data';

import 'package:friend_private/backend/schema/bt_device.dart';

abstract class DeviceBase {
  abstract final String deviceId;
  late String name;

  DeviceBase(String deviceId);

  Future<int> retrieveBatteryLevel();

  Future<StreamSubscription<List<int>>?> getBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  });

  Future<StreamSubscription?> getBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  });

  Future<BleAudioCodec> getAudioCodec();

  Future cameraStartPhotoController();

  Future cameraStopPhotoController();

  Future<bool> hasPhotoStreamingCharacteristic();

  Future<StreamSubscription?> getImageListener(
      {required void Function(Uint8List base64JpgData) onImageReceived});
}
