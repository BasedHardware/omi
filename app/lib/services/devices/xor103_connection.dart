import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class Xor103DeviceConnection extends DeviceConnection {
  Xor103DeviceConnection(super.device, super.transport);

  @override
  Future<int> performRetrieveBatteryLevel() async {
    // XOR103 may not have standard battery service
    // Return default or implement custom battery reading
    return 100;
  }

  @override
  Future<List<int>> performGetButtonState() async {
    return [];
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    // XOR103 uses Opus FS320 by default
    return BleAudioCodec.opusFS320;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    // Use XOR103-specific notify characteristic
    final stream = transport.getCharacteristicStream(
      xor103ServiceUuid,
      xor103NotifyCharUuid,
    );
    return stream.listen(onAudioBytesReceived);
  }

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    // XOR103 may not support storage streaming
    return null;
  }

  @override
  Future performCameraStartPhotoController() async {
    // XOR103 doesn't have camera
    return;
  }

  @override
  Future performCameraStopPhotoController() async {
    return;
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async {
    return false;
  }

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async {
    return null;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async {
    return null;
  }

  @override
  Future<int> performGetFeatures() async {
    return 0;
  }

  @override
  Future<void> performSetLedDimRatio(int ratio) async {
    // Not applicable
  }

  @override
  Future<int?> performGetLedDimRatio() async {
    return null;
  }

  @override
  Future<void> performSetMicGain(int gain) async {
    // Not applicable
  }

  @override
  Future<int?> performGetMicGain() async {
    return null;
  }

  Future<Map<String, String>> getDeviceInfo() async {
    return {
      'modelNumber': 'XOR103',
      'firmwareRevision': '1.0.0',
      'hardwareRevision': 'XOR103 Device',
      'manufacturerName': 'XOR',
    };
  }
}
