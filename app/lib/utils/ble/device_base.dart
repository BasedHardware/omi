import 'dart:async';
import 'dart:typed_data';

import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/services/notification_service.dart';

abstract class DeviceBase {
  abstract final String deviceId;
  late String name;

  DeviceBase(String deviceId);

  Future<bool> isConnected();

  Future<int> retrieveBatteryLevel() async {
    if (await isConnected()) {
      return await performRetrieveBatteryLevel();
    }
    _showDeviceDisconnectedNotification();
    return -1;
  }

  Future<int> performRetrieveBatteryLevel();

  Future<StreamSubscription<List<int>>?> getBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    if (await isConnected()) {
      return await performGetBleBatteryLevelListener(onBatteryLevelChange: onBatteryLevelChange);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  });

  Future<StreamSubscription?> getBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    if (await isConnected()) {
      return await performGetBleAudioBytesListener(onAudioBytesReceived: onAudioBytesReceived);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  });

  Future<BleAudioCodec> getAudioCodec() async {
    if (await isConnected()) {
      return await performGetAudioCodec();
    }
    _showDeviceDisconnectedNotification();
    return BleAudioCodec.pcm8;
  }

  Future<BleAudioCodec> performGetAudioCodec();

  Future cameraStartPhotoController() async {
    if (await isConnected()) {
      return await performCameraStartPhotoController();
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future performCameraStartPhotoController();

  Future cameraStopPhotoController() async {
    if (await isConnected()) {
      return await performCameraStopPhotoController();
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future performCameraStopPhotoController();

  Future<bool> hasPhotoStreamingCharacteristic() async {
    if (await isConnected()) {
      return await performHasPhotoStreamingCharacteristic();
    }
    _showDeviceDisconnectedNotification();
    return false;
  }

  Future<bool> performHasPhotoStreamingCharacteristic();

  Future<StreamSubscription?> getImageListener({
    required void Function(Uint8List base64JpgData) onImageReceived,
  }) async {
    if (await isConnected()) {
      return await performGetImageListener(onImageReceived: onImageReceived);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription?> performGetImageListener({
    required void Function(Uint8List base64JpgData) onImageReceived,
  });

  Future<StreamSubscription<List<int>>?> getAccelListener({
    void Function(int)? onAccelChange,
  }) async {
    if (await isConnected()) {
      return await performGetAccelListener(onAccelChange: onAccelChange);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  });

  void _showDeviceDisconnectedNotification() {
    NotificationService.instance.createNotification(
      title: '$name Disconnected',
      body: 'Please reconnect to continue using your $name.',
    );
  }
}
