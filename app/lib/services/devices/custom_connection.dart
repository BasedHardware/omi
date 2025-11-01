import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

/// Base class for custom device connections with configurable protocol
/// Allows easy addition of devices with similar command-based protocols
abstract class CustomDeviceConnection extends DeviceConnection {
  // ═══════════════════════════════════════════════════════════════
  //                    Abstract Configuration
  // ═══════════════════════════════════════════════════════════════

  /// Service UUID for the device
  String get serviceUuid;

  /// Control characteristic UUID for sending commands
  String get controlCharacteristicUuid;

  /// Audio characteristic UUID for receiving audio data
  String get audioCharacteristicUuid;

  /// Audio codec used by the device
  BleAudioCodec get audioCodec;

  /// Command code for unmuting/starting recording
  int get commandUnmute;

  /// Command code for muting/stopping recording
  int get commandMute;

  /// Command code for getting battery level
  int get commandGetBattery;

  // ═══════════════════════════════════════════════════════════════
  //                    Abstract Protocol Methods
  // ═══════════════════════════════════════════════════════════════

  /// Encode command with device-specific format
  /// Returns bytes to send over BLE
  List<int> encodeCommand(int commandCode, List<int> data);

  /// Parse response from control characteristic
  /// Returns map with 'type', 'code', and 'payload'
  Map<String, dynamic> parseResponse(List<int> data);

  /// Strip header from audio packets if needed
  /// Returns audio payload or null if invalid
  List<int>? stripAudioHeader(List<int> data);

  /// Parse battery response payload
  /// Returns map with 'level' and 'is_charging' or null
  Map<String, dynamic>? parseBatteryResponse(List<int> payload);

  /// Get unmute command data (e.g., [0x01] for Bee)
  List<int> get unmuteCommandData => [0x01];

  /// Get mute command data (e.g., [0x00] for Bee)
  List<int> get muteCommandData => [0x00];

  // ═══════════════════════════════════════════════════════════════
  //                    Internal State
  // ═══════════════════════════════════════════════════════════════

  final Map<int, StreamController<List<int>>> _commandQueues = {};
  final StreamController<List<int>> _audioStream = StreamController<List<int>>.broadcast();

  StreamSubscription? _controlNotificationSub;
  StreamSubscription? _audioNotificationSub;

  int _chunkCount = 0;
  bool _isRecording = false;

  CustomDeviceConnection(super.device, super.transport);

  // ═══════════════════════════════════════════════════════════════
  //                    Connection Management
  // ═══════════════════════════════════════════════════════════════

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
    await Future.delayed(const Duration(seconds: 1));

    // Subscribe to control notifications
    final controlStream = transport.getCharacteristicStream(serviceUuid, controlCharacteristicUuid);
    _controlNotificationSub = controlStream.listen(_handleControlNotification);

    // Subscribe to audio notifications
    final audioStream = transport.getCharacteristicStream(serviceUuid, audioCharacteristicUuid);
    _audioNotificationSub = audioStream.listen(_handleAudioNotification);

    debugPrint('[CustomDevice] Notifications enabled');
  }

  @override
  Future<void> disconnect() async {
    if (_isRecording) {
      try {
        await _muteDevice();
      } catch (_) {}
    }

    await _controlNotificationSub?.cancel();
    await _audioNotificationSub?.cancel();

    for (var controller in _commandQueues.values) {
      await controller.close();
    }
    _commandQueues.clear();
    await _audioStream.close();

    await super.disconnect();
  }

  // ═══════════════════════════════════════════════════════════════
  //                    Notification Handlers
  // ═══════════════════════════════════════════════════════════════

  void _handleControlNotification(List<int> data) {
    final response = parseResponse(data);

    if (response['type'] == 'response') {
      final cmdId = response['code'] as int;
      final payload = response['payload'] as List<int>;

      _commandQueues.putIfAbsent(cmdId, () => StreamController<List<int>>.broadcast()).add(payload);
    } else if (response['type'] == 'event') {
      _handleEvent(response);
    }
  }

  void _handleAudioNotification(List<int> data) {
    final payload = stripAudioHeader(data);
    if (payload != null && payload.isNotEmpty) {
      processAudioData(payload);
    }
  }

  /// Process audio payload - subclasses can override for buffering/frame detection
  /// Default implementation sends payload directly to stream
  void processAudioData(List<int> payload) {
    _chunkCount++;
    _audioStream.add(payload);

    if (_chunkCount % 100 == 0) {
      debugPrint('[CustomDevice] Received $_chunkCount audio chunks');
    }
  }

  /// Override to handle device-specific events
  void _handleEvent(Map<String, dynamic> event) {
    // Default: do nothing
    debugPrint('[CustomDevice] Event: ${event['code']}');
  }

  // ═══════════════════════════════════════════════════════════════
  //                    Command Methods
  // ═══════════════════════════════════════════════════════════════

  Future<List<int>?> _sendCommand(int cmdId, List<int> payload) async {
    _commandQueues.putIfAbsent(cmdId, () => StreamController<List<int>>.broadcast());

    final command = encodeCommand(cmdId, payload);
    await transport.writeCharacteristic(serviceUuid, controlCharacteristicUuid, command);

    try {
      return await _commandQueues[cmdId]!.stream.first.timeout(const Duration(seconds: 5));
    } on TimeoutException {
      debugPrint('[CustomDevice] Command $cmdId timeout');
      return null;
    }
  }

  Future<void> _unmuteDevice() async {
    await _sendCommand(commandUnmute, unmuteCommandData);
    _isRecording = true;
    debugPrint('[CustomDevice] Device unmuted');
  }

  Future<void> _muteDevice() async {
    await _sendCommand(commandMute, muteCommandData);
    _isRecording = false;
    debugPrint('[CustomDevice] Device muted');
  }

  // ═══════════════════════════════════════════════════════════════
  //                    DeviceConnection Implementation
  // ═══════════════════════════════════════════════════════════════

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final response = await _sendCommand(commandGetBattery, []);
      if (response != null) {
        final batteryInfo = parseBatteryResponse(response);
        if (batteryInfo != null) {
          final level = batteryInfo['level'] as int;
          final isCharging = batteryInfo['is_charging'] as bool;
          debugPrint('[CustomDevice] Battery: $level% ${isCharging ? "(Charging)" : ""}');
          return level;
        }
      }
      return -1;
    } catch (e) {
      debugPrint('[CustomDevice] Error retrieving battery: $e');
      return -1;
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    if (onBatteryLevelChange == null) return null;

    final controller = StreamController<List<int>>();
    Timer? pollingTimer;
    int? lastBatteryLevel;

    controller.onCancel = () {
      pollingTimer?.cancel();
    };

    // Poll battery every 60 seconds
    pollingTimer = Timer.periodic(const Duration(seconds: 60), (timer) async {
      try {
        final batteryLevel = await performRetrieveBatteryLevel();
        if (batteryLevel >= 0 && batteryLevel != lastBatteryLevel) {
          lastBatteryLevel = batteryLevel;
          controller.add([batteryLevel]);
          onBatteryLevelChange(batteryLevel);
        }
      } catch (e) {
        debugPrint('[CustomDevice] Error polling battery: $e');
      }
    });

    // Get initial battery level
    try {
      final batteryLevel = await performRetrieveBatteryLevel();
      if (batteryLevel >= 0) {
        lastBatteryLevel = batteryLevel;
        controller.add([batteryLevel]);
        onBatteryLevelChange(batteryLevel);
      }
    } catch (e) {
      debugPrint('[CustomDevice] Error getting initial battery: $e');
    }

    return controller.stream.listen(null);
  }

  @override
  Future<List<int>> performGetButtonState() async {
    return [];
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    return audioCodec;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    // Start recording
    await _unmuteDevice();
    await Future.delayed(const Duration(seconds: 1));

    debugPrint('[CustomDevice] Starting audio stream');
    _chunkCount = 0;

    return _audioStream.stream.listen(onAudioBytesReceived);
  }

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    return null;
  }

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
}
