import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/services/devices/device_connection.dart';
import 'package:friend_private/services/devices/models.dart';
import 'package:friend_private/services/devices.dart';

class WebMockDeviceConnection extends DeviceConnection {
  WebMockDeviceConnection(BtDevice device, BluetoothDevice? bleDevice) 
      : super(device, bleDevice ?? BluetoothDevice(remoteId: DeviceIdentifier('web-mock-device')));

  @override
  Future<void> connect({Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    // Mock implementation for web
    debugPrint('Web mock device connection: connect');
    if (onConnectionStateChanged != null) {
      onConnectionStateChanged(device.id, DeviceConnectionState.connected);
    }
  }

  @override
  Future<bool> isConnected() async {
    return true; // Always return connected for web
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    return 100; // Mock battery level
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    if (onBatteryLevelChange != null) {
      onBatteryLevelChange(100);
    }
    return null;
  }

  @override
  Future<List<int>> performGetButtonState() async {
    return [1]; // Mock button state
  }

  @override
  Future<StreamSubscription?> performGetBleButtonListener({
    required void Function(List<int>) onButtonReceived,
  }) async {
    // No real implementation needed for web
    return null;
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    return BleAudioCodec.opus;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    return null;
  }

  @override
  Future<List<int>> performGetStorageList() async {
    return []; // Empty storage list for web
  }

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    return null;
  }

  @override
  Future<bool> performPlayToSpeakerHaptic(int level) async {
    return true; // Pretend it worked
  }

  @override
  Future<bool> performWriteToStorage(int numFile, int command, int offset) async {
    return true; // Pretend it worked
  }

  @override
  Future performCameraStartPhotoController() async {
    // No implementation for web
  }

  @override
  Future performCameraStopPhotoController() async {
    // No implementation for web
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async {
    return false;
  }

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(Uint8List base64JpgData) onImageReceived,
  }) async {
    return null;
  }
  
  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async {
    if (onAccelChange != null) {
      onAccelChange(0); // Mock accelerometer data
    }
    return null;
  }
}
