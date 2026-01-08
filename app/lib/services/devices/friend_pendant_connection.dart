import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';

/// Friend Pendant device connection
/// Uses LC3 codec at 16 kHz with 10ms frames (30 bytes per frame)
/// Packets contain 3 frames (90 bytes LC3 data + 5 bytes footer = 95 bytes total)
class FriendPendantDeviceConnection extends DeviceConnection {
  static const int packetFooterSize = 5;
  static const int packetSize = 95;
  static const int lc3DataSize = 90; // 3 frames of 30 bytes each
  static const int lc3FrameSize = 30; // Single LC3 frame size

  final _audioController = StreamController<List<int>>.broadcast();
  StreamSubscription? _audioSub;
  bool _isRecording = false;

  FriendPendantDeviceConnection(super.device, super.transport);

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
    bool autoConnect = false,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged, autoConnect: autoConnect);
    await Future.delayed(const Duration(seconds: 1));

    // Subscribe to audio stream
    _audioSub = transport
        .getCharacteristicStream(friendPendantServiceUuid, friendPendantAudioCharacteristicUuid)
        .listen((data) {
      final payload = _processAudioPacket(data);
      if (payload != null && payload.isNotEmpty) {
        // Split 90-byte payload into 30-byte LC3 frames and add each separately
        for (int i = 0; i < payload.length; i += lc3FrameSize) {
          final end = (i + lc3FrameSize <= payload.length) ? i + lc3FrameSize : payload.length;
          final chunk = payload.sublist(i, end);
          if (chunk.length == lc3FrameSize) {
            _audioController.add(chunk);
          }
        }
      }
    });
  }

  @override
  Future<void> disconnect() async {
    _isRecording = false;
    await _audioSub?.cancel();
    await _audioController.close();
    await super.disconnect();
  }

  /// Process audio packet by stripping the 5-byte footer
  List<int>? _processAudioPacket(List<int> data) {
    if (data.length < packetFooterSize) {
      return null;
    }

    // Strip the 5-byte footer to get LC3 audio data
    return data.sublist(0, data.length - packetFooterSize);
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    // Friend Pendant doesn't have battery level reporting via BLE
    return 90;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    if (onBatteryLevelChange == null) return null;

    final controller = StreamController<List<int>>();

    // Send initial battery level immediately
    onBatteryLevelChange(90);

    // Send 90% battery level every 30 seconds
    final timer = Timer.periodic(const Duration(seconds: 30), (timer) {
      onBatteryLevelChange(90);
    });

    controller.onCancel = () => timer.cancel();

    return controller.stream.listen(null);
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async => BleAudioCodec.lc3FS1030;

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    _isRecording = true;
    return _audioController.stream.listen(onAudioBytesReceived);
  }

  @override
  Future<List<int>> performGetButtonState() async => [];

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async =>
      null;

  @override
  Future performCameraStartPhotoController() async {}

  @override
  Future performCameraStopPhotoController() async {}

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async => false;

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async =>
      null;

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async =>
      null;

  @override
  Future<int> performGetFeatures() async => 0;

  @override
  Future<void> performSetLedDimRatio(int ratio) async {}

  @override
  Future<int?> performGetLedDimRatio() async => null;

  @override
  Future<void> performSetMicGain(int gain) async {}

  @override
  Future<int?> performGetMicGain() async => null;

  Future<Map<String, String>> getDeviceInfo() async {
    return {
      'modelNumber': 'Friend Pendant',
      'firmwareRevision': '1.0.0',
      'hardwareRevision': 'Friend',
      'manufacturerName': 'Friend',
    };
  }
}
