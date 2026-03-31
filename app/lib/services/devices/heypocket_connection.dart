import 'dart:async';
import 'dart:convert';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/logger.dart';

/// HeyPocket (Pocket) device connection
///
/// Uses a text-based control protocol with ASCII command frames (MCU&/APP& prefixes)
/// and binary MP3 audio streaming over BLE notifications.
///
/// GATT Profile:
///   Service:         001120a0-2233-4455-6677-889912345678
///   Control Write:   001120a2-2233-4455-6677-889912345678
///   Control Notify:  001120a1-2233-4455-6677-889912345678
///   Audio Notify:    001120a3-2233-4455-6677-889912345678
class HeyPocketDeviceConnection extends DeviceConnection {
  static const String _serviceUuid = '001120a0-2233-4455-6677-889912345678';
  static const String _controlWriteCharUuid =
      '001120a2-2233-4455-6677-889912345678';
  static const String _controlNotifyCharUuid =
      '001120a1-2233-4455-6677-889912345678';
  static const String _audioNotifyCharUuid =
      '001120a3-2233-4455-6677-889912345678';

  /// Control command prefixes indicating text-based protocol messages
  static const List<String> _controlPrefixes = [
    'MCU&',
    'APP&',
    'BLE&',
    'SYS&',
  ];

  final _audioController = StreamController<List<int>>.broadcast();
  StreamSubscription? _controlSub;
  StreamSubscription? _audioSub;
  int _batteryLevel = -1;
  bool _isRecording = false;

  HeyPocketDeviceConnection(super.device, super.transport);

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)?
        onConnectionStateChanged,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
    await Future.delayed(const Duration(seconds: 1));

    // Subscribe to control notifications for battery/status
    _controlSub = transport
        .getCharacteristicStream(_serviceUuid, _controlNotifyCharUuid)
        .listen((data) {
      _handleControlNotification(data);
    });

    // Subscribe to audio notifications
    _audioSub = transport
        .getCharacteristicStream(_serviceUuid, _audioNotifyCharUuid)
        .listen((data) {
      if (data.isNotEmpty && !_isControlPayload(data)) {
        _audioController.add(data);
      }
    });

    // Send initial status/time sync
    await _sendInitCommands();
  }

  @override
  Future<void> disconnect() async {
    if (_isRecording) {
      try {
        await _sendControlCommand('APP&STO');
      } catch (_) {}
      _isRecording = false;
    }
    await _controlSub?.cancel();
    await _audioSub?.cancel();
    await _audioController.close();
    await super.disconnect();
  }

  /// Check if a payload is a text-based control message
  bool _isControlPayload(List<int> data) {
    if (data.isEmpty) return false;
    // Check if all bytes are printable ASCII
    final allPrintable = data.every((b) => b >= 0x20 && b <= 0x7E);
    if (!allPrintable) return false;

    final text = utf8.decode(data, allowMalformed: true);
    return _controlPrefixes.any((prefix) => text.startsWith(prefix));
  }

  /// Handle incoming control notifications
  void _handleControlNotification(List<int> data) {
    if (data.isEmpty) return;

    if (_isControlPayload(data)) {
      final text = utf8.decode(data, allowMalformed: true);
      Logger.debug('HeyPocket control: $text');

      // Parse battery response: MCU&BAT&<0-100>
      if (text.startsWith('MCU&BAT&')) {
        final parts = text.split('&');
        if (parts.length >= 3) {
          final level = int.tryParse(parts[2]);
          if (level != null && level >= 0 && level <= 100) {
            _batteryLevel = level;
          }
        }
      }
    } else {
      // Some firmware variants may emit audio on control notify
      _audioController.add(data);
    }
  }

  /// Send initialization commands after connection
  Future<void> _sendInitCommands() async {
    try {
      // Query battery
      await _sendControlCommand('APP&BAT');

      // Query status/mode
      await _sendControlCommand('APP&STE');

      // Time sync
      final now = DateTime.now();
      final timeStr =
          '${now.year}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}'
          '${now.hour.toString().padLeft(2, '0')}${now.minute.toString().padLeft(2, '0')}${now.second.toString().padLeft(2, '0')}';
      await _sendControlCommand('APP&T&$timeStr');
    } catch (e) {
      Logger.debug('HeyPocket: Error sending init commands: $e');
    }
  }

  /// Send a text control command to the device
  Future<void> _sendControlCommand(String command) async {
    try {
      final data = utf8.encode(command);
      await transport.writeCharacteristic(
          _serviceUuid, _controlWriteCharUuid, data);
      // Small delay between commands per protocol notes
      await Future.delayed(const Duration(milliseconds: 100));
    } catch (e) {
      Logger.debug('HeyPocket: Error sending command "$command": $e');
    }
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      await _sendControlCommand('APP&BAT');
      // Wait briefly for response
      await Future.delayed(const Duration(seconds: 2));
      return _batteryLevel >= 0 ? _batteryLevel : -1;
    } catch (e) {
      Logger.debug('HeyPocket: Error reading battery level: $e');
      return -1;
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    if (onBatteryLevelChange == null) return null;

    final controller = StreamController<List<int>>();

    // Poll battery every 60 seconds
    final timer = Timer.periodic(const Duration(seconds: 60), (timer) async {
      final level = await performRetrieveBatteryLevel();
      if (level >= 0) {
        onBatteryLevelChange(level);
      }
    });

    controller.onCancel = () => timer.cancel();

    // Get initial level
    final initialLevel = await performRetrieveBatteryLevel();
    if (initialLevel >= 0) {
      onBatteryLevelChange(initialLevel);
    }

    return controller.stream.listen(null);
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    // HeyPocket streams MP3 audio chunks over BLE notifications.
    // There is no dedicated MP3 codec in BleAudioCodec, so we report
    // 'unknown' and let the backend detect and decode the MP3 stream.
    // If backend MP3 support is added later, a dedicated enum value
    // should replace this.
    return BleAudioCodec.unknown;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    // Start recording on the device
    await _sendControlCommand('APP&STA');
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
      'modelNumber': 'HeyPocket',
      'firmwareRevision': '1.0.0',
      'hardwareRevision': 'PKT01',
      'manufacturerName': 'Pocket',
    };
  }
}
