import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';

class PlaudDeviceConnection extends DeviceConnection {
  static const int _cmdGetBattery = 9;
  static const int _cmdStartRecord = 20;
  static const int _cmdStopRecord = 23;
  static const int _cmdSyncFileStart = 28;
  static const int _cmdStopSync = 30;

  final Map<int, StreamController<List<int>>> _commandQueues = {};
  final StreamController<List<int>> _audioStream = StreamController<List<int>>.broadcast();

  StreamSubscription? _notificationSub;
  int? _sessionId;

  PlaudDeviceConnection(super.device, super.transport);

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
    bool autoConnect = false,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged, autoConnect: autoConnect);
    await Future.delayed(const Duration(seconds: 2));

    final stream = transport.getCharacteristicStream(plaudServiceUuid, plaudNotifyCharUuid);
    _notificationSub = stream.listen(_handleNotification);
  }

  @override
  Future<void> disconnect() async {
    if (_sessionId != null) {
      try {
        await _stopSync();
        await _stopRecord(_sessionId!);
      } catch (_) {}
    }

    await _notificationSub?.cancel();
    for (var controller in _commandQueues.values) {
      await controller.close();
    }
    _commandQueues.clear();
    await _audioStream.close();
    await super.disconnect();
  }

  void _handleNotification(List<int> data) {
    if (data.isEmpty) return;

    if (data[0] == 2) {
      // Audio data packet
      final chunk = _parseAudioChunk(data.sublist(1));
      if (chunk != null) _audioStream.add(chunk);
    } else if (data.length >= 3) {
      // Command response
      final cmdId = data[1] | (data[2] << 8);
      final payload = data.length > 3 ? data.sublist(3) : <int>[];
      _commandQueues.putIfAbsent(cmdId, () => StreamController<List<int>>.broadcast()).add(payload);
    }
  }

  List<int>? _parseAudioChunk(List<int> payload) {
    if (payload.length < 9) return null;

    final position = _toInt32(payload.sublist(4, 8));
    if (position == 0xFFFFFFFF) return null; // End marker

    final length = payload[8];
    return payload.sublist(9, 9 + length);
  }

  Future<List<int>?> _sendCommand(int cmdId, List<int> payload) async {
    _commandQueues.putIfAbsent(cmdId, () => StreamController<List<int>>.broadcast());

    final command = [1, cmdId & 0xFF, (cmdId >> 8) & 0xFF, ...payload];
    await transport.writeCharacteristic(plaudServiceUuid, plaudWriteCharUuid, command);

    try {
      return await _commandQueues[cmdId]!.stream.first.timeout(const Duration(seconds: 10));
    } on TimeoutException {
      return null;
    }
  }

  Future<Map<String, int>?> _startRecord() async {
    final payload = [..._toBytes32(1), ..._toBytes32(0), ..._toBytes32(0)];
    final response = await _sendCommand(_cmdStartRecord, payload);

    if (response != null && response.length >= 10) {
      return {
        'sessionId': _toInt32(response.sublist(0, 4)),
        'startTime': _toInt32(response.sublist(4, 8)),
      };
    }
    return null;
  }

  Future<void> _stopRecord(int sessionId) async {
    final payload = [..._toBytes32(sessionId), ..._toBytes32(0)];
    await _sendCommand(_cmdStopRecord, payload);
  }

  Future<bool> _startSync(int sessionId, int start) async {
    final payload = [..._toBytes64(sessionId), ..._toBytes64(start), ..._toBytes64(0x7FFFFFFF)];
    final response = await _sendCommand(_cmdSyncFileStart, payload);
    return response != null;
  }

  Future<void> _stopSync() async {
    await transport.writeCharacteristic(
        plaudServiceUuid, plaudWriteCharUuid, [1, _cmdStopSync & 0xFF, (_cmdStopSync >> 8) & 0xFF, 1]);
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final response = await _sendCommand(_cmdGetBattery, []);
      if (response != null && response.length >= 2) {
        // Response format: [is_charging, battery_level]
        final batteryLevel = response[1];
        final isCharging = response[0] != 0;
        debugPrint('[PLAUD] Battery: $batteryLevel% ${isCharging ? "(Charging)" : ""}');
        return batteryLevel;
      }
      return -1;
    } catch (e) {
      debugPrint('[PLAUD] Error retrieving battery level: $e');
      return -1;
    }
  }

  Future<Map<String, dynamic>?> getBatteryState() async {
    try {
      final response = await _sendCommand(_cmdGetBattery, []);
      if (response != null && response.length >= 2) {
        return {
          'isCharging': response[0] != 0,
          'level': response[1],
        };
      }
      return null;
    } catch (e) {
      debugPrint('[PLAUD] Error getting battery state: $e');
      return null;
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    // PLAUD devices use command-based battery retrieval, not automatic notifications
    // Battery state must be explicitly requested via CMD_GET_BATTERY (command 9)
    // Therefore we poll periodically rather than relying on unsolicited notifications
    if (onBatteryLevelChange == null) return null;

    final controller = StreamController<List<int>>();
    Timer? pollingTimer;
    int? lastBatteryLevel;

    // Set up cleanup when stream is cancelled
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
        debugPrint('[PLAUD] Error polling battery level: $e');
      }
    });

    // Get initial battery level immediately
    try {
      final batteryLevel = await performRetrieveBatteryLevel();
      if (batteryLevel >= 0) {
        lastBatteryLevel = batteryLevel;
        controller.add([batteryLevel]);
        onBatteryLevelChange(batteryLevel);
      }
    } catch (e) {
      debugPrint('[PLAUD] Error getting initial battery level: $e');
    }

    return controller.stream.listen(null);
  }

  @override
  Future<List<int>> performGetButtonState() async {
    return [];
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    return BleAudioCodec.opusFS320;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    if (!await _setupRecordingSession()) {
      debugPrint('[PLAUD] Failed to setup recording session after retries');
      return null;
    }

    // Buffer for 80-byte chunking
    final buffer = <int>[];
    const chunkSize = 80;

    return _audioStream.stream.listen(
      (data) {
        buffer.addAll(data);
        while (buffer.length >= chunkSize) {
          onAudioBytesReceived(buffer.sublist(0, chunkSize));
          buffer.removeRange(0, chunkSize);
        }
      },
      onDone: () {
        if (buffer.isNotEmpty) {
          onAudioBytesReceived(buffer);
        }
      },
    );
  }

  Future<bool> _setupRecordingSession() async {
    const maxRetries = 3;

    for (int attempt = 0; attempt < maxRetries; attempt++) {
      try {
        if (attempt > 0) {
          debugPrint('[PLAUD] Retry attempt $attempt/$maxRetries');
          await Future.delayed(Duration(seconds: attempt)); // Exponential backoff: 0s, 1s, 2s
        }

        await _stopRecord(0);
        await Future.delayed(const Duration(milliseconds: 500));

        final recordInfo = await _startRecord();
        if (recordInfo == null) continue;

        _sessionId = recordInfo['sessionId']!;
        final startTime = recordInfo['startTime']!;

        await Future.delayed(const Duration(seconds: 1));

        if (await _startSync(_sessionId!, startTime)) {
          debugPrint('[PLAUD] Recording session setup successful');
          return true;
        }
      } catch (e) {
        debugPrint('[PLAUD] Setup error (attempt ${attempt + 1}): $e');
      }
    }

    return false;
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

  Future<Map<String, String>> getDeviceInfo() async {
    return {
      'modelNumber': 'PLAUD NotePin',
      'firmwareRevision': '1.0.0',
      'hardwareRevision': '1.0.0',
      'manufacturerName': 'PLAUD',
    };
  }

  List<int> _toBytes32(int v) => [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF];

  List<int> _toBytes64(int v) => [
        v & 0xFF,
        (v >> 8) & 0xFF,
        (v >> 16) & 0xFF,
        (v >> 24) & 0xFF,
        (v >> 32) & 0xFF,
        (v >> 40) & 0xFF,
        (v >> 48) & 0xFF,
        (v >> 56) & 0xFF,
      ];

  int _toInt32(List<int> b) => b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24);
}
