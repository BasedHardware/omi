import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/gen/flutter_communicator.g.dart';
import 'package:omi/services/bridges/apple_watch_bridge.dart';

import 'device_transport.dart';

class WatchTransport extends DeviceTransport {
  final WatchRecorderHostAPI _hostAPI = WatchRecorderHostAPI();
  final StreamController<DeviceTransportState> _connectionStateController;
  final Map<String, StreamController<List<int>>> _streamControllers = {};
  final Map<String, Timer> _periodicTimers = {};

  DeviceTransportState _state = DeviceTransportState.disconnected;

  static AppleWatchFlutterBridge? _bridge;
  static final List<StreamController<List<int>>> _audioControllers = [];
  static final List<StreamController<List<int>>> _batteryControllers = [];

  WatchTransport() : _connectionStateController = StreamController<DeviceTransportState>.broadcast() {
    _ensureWatchBridgeSetup();
  }

  @override
  String get deviceId => 'apple-watch';

  @override
  Stream<DeviceTransportState> get connectionStateStream => _connectionStateController.stream;

  void _updateState(DeviceTransportState newState) {
    if (_state != newState) {
      _state = newState;
      _connectionStateController.add(_state);
    }
  }

  void _ensureWatchBridgeSetup() {
    if (_bridge == null) {
      _bridge = AppleWatchFlutterBridge(
        onChunk: (Uint8List bytes, int chunkIndex, bool isLast, double sampleRate) {
          _audioControllers.removeWhere((controller) => controller.isClosed);

          if (_audioControllers.isNotEmpty) {
            for (final controller in _audioControllers) {
              try {
                controller.add(bytes);
              } catch (e) {
                debugPrint('Watch Transport: Error forwarding audio to controller: $e');
              }
            }
          }
        },
        onRecordingStartedCb: () {
          debugPrint('Watch Transport: Recording started');
        },
        onRecordingStoppedCb: () {
          debugPrint('Watch Transport: Recording stopped');
        },
        onRecordingErrorCb: (String error) {
          debugPrint('Watch Transport: Recording error: $error');
        },
        onMicPermissionCb: (bool granted) {
          debugPrint('Watch Transport: Mic permission: $granted');
        },
        onMainAppMicPermissionCb: (bool granted) {
          debugPrint('Watch Transport: Main app mic permission: $granted');
        },
        onBatteryUpdateCb: (double batteryLevel, int batteryState) {
          _batteryControllers.removeWhere((controller) => controller.isClosed);

          if (_batteryControllers.isNotEmpty) {
            final batteryLevelInt = batteryLevel.round();
            for (final controller in _batteryControllers) {
              try {
                controller.add([batteryLevelInt]);
              } catch (e) {
                debugPrint('Watch Transport: Error forwarding battery to controller: $e');
              }
            }
          }
        },
      );
      WatchRecorderFlutterAPI.setUp(_bridge!);
    }
  }

  @override
  Future<void> connect({bool autoConnect = false}) async {
    if (_state == DeviceTransportState.connected) {
      return;
    }

    _updateState(DeviceTransportState.connecting);

    try {
      final supported = await _hostAPI.isWatchSessionSupported();
      final paired = await _hostAPI.isWatchPaired();
      final reachable = await _hostAPI.isWatchReachable();

      if (!supported) {
        throw Exception('Apple Watch session not supported on this device');
      }
      if (!paired) {
        throw Exception('Apple Watch not paired');
      }

      if (reachable) {
        _updateState(DeviceTransportState.connected);
      } else {
        _updateState(DeviceTransportState.disconnected);
        throw Exception('Apple Watch not reachable');
      }
    } catch (e) {
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }
  }

  @override
  Future<void> disconnect() async {
    if (_state == DeviceTransportState.disconnected) {
      return;
    }

    _updateState(DeviceTransportState.disconnecting);

    for (final timer in _periodicTimers.values) {
      timer.cancel();
    }
    _periodicTimers.clear();

    for (final controller in _streamControllers.values) {
      _audioControllers.remove(controller);
      _batteryControllers.remove(controller);
      await controller.close();
    }
    _streamControllers.clear();

    _updateState(DeviceTransportState.disconnected);
  }

  @override
  Future<bool> isConnected() async {
    try {
      final supported = await _hostAPI.isWatchSessionSupported();
      if (!supported) return false;

      final paired = await _hostAPI.isWatchPaired();
      if (!paired) return false;

      final reachable = await _hostAPI.isWatchReachable();
      return reachable;
    } catch (e) {
      return false;
    }
  }

  @override
  Future<bool> ping() async {
    return await isConnected();
  }

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    if (serviceUuid == 'watch-battery-service' && characteristicUuid == 'watch-battery-level') {
      return _getBatteryStream();
    } else if (serviceUuid == 'watch-audio-service' && characteristicUuid == 'watch-audio-data') {
      return _getAudioStream();
    }

    return const Stream.empty();
  }

  Stream<List<int>> _getBatteryStream() {
    const key = 'battery';

    if (!_streamControllers.containsKey(key)) {
      _streamControllers[key] = StreamController<List<int>>.broadcast();
      _setupBatteryMonitoring();
    }

    return _streamControllers[key]!.stream;
  }

  Stream<List<int>> _getAudioStream() {
    const key = 'audio';

    if (!_streamControllers.containsKey(key)) {
      _streamControllers[key] = StreamController<List<int>>.broadcast();
      _setupAudioStreaming();
    }

    return _streamControllers[key]!.stream;
  }

  void _setupAudioStreaming() {
    const key = 'audio';

    if (_streamControllers[key] != null) {
      _audioControllers.add(_streamControllers[key]!);
    }
  }

  void _setupBatteryMonitoring() {
    const key = 'battery';

    if (_streamControllers[key] != null) {
      _batteryControllers.add(_streamControllers[key]!);
    }

    _hostAPI.requestWatchBatteryUpdate().catchError((e) {
      debugPrint('Watch Transport: Error requesting initial battery update: $e');
    });

    _periodicTimers[key] = Timer.periodic(const Duration(seconds: 300), (timer) async {
      try {
        await _hostAPI.requestWatchBatteryUpdate();
      } catch (e) {
        debugPrint('Watch Transport: Battery update request error: $e');
      }
    });
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    if (serviceUuid == 'watch-battery-service' && characteristicUuid == 'watch-battery-level') {
      try {
        final level = await _hostAPI.getWatchBatteryLevel();
        return [level.round()];
      } catch (e) {
        debugPrint('Watch Transport: Error reading battery level: $e');
        return [-1];
      }
    } else if (serviceUuid == 'watch-device-info-service') {
      if (characteristicUuid == 'watch-model' || characteristicUuid == 'watch-firmware') {
        try {
          final deviceInfo = await _hostAPI.getWatchInfo();
          if (characteristicUuid == 'watch-model') {
            final model = deviceInfo['model'] ?? 'Apple Watch';
            return model.codeUnits;
          } else if (characteristicUuid == 'watch-firmware') {
            final firmware = deviceInfo['systemVersion'] ?? 'Unknown';
            return firmware.codeUnits;
          }
        } catch (e) {
          debugPrint('Watch Transport: Error reading device info: $e');
        }
      }
    }

    return [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}

  Future<void> startRecording() async {
    try {
      await _hostAPI.startRecording();
    } catch (e) {
      debugPrint('Watch Transport: Error starting recording: $e');
      rethrow;
    }
  }

  Future<void> stopRecording() async {
    try {
      await _hostAPI.stopRecording();
    } catch (e) {
      debugPrint('Watch Transport: Error stopping recording: $e');
      rethrow;
    }
  }

  Future<Map<String, String>> getWatchInfo() async {
    try {
      var res = await _hostAPI.getWatchInfo();
      res['firmwareRevision'] = res['systemVersion'] ?? 'Unknown';
      return res;
    } catch (e) {
      debugPrint('Watch Transport: Error getting watch info: $e');
      return {};
    }
  }

  Future<bool> checkMainAppMicrophonePermission() async {
    try {
      return await _hostAPI.checkMainAppMicrophonePermission();
    } catch (e) {
      debugPrint('Watch Transport: Error checking mic permission: $e');
      return false;
    }
  }

  Future<void> requestMainAppMicrophonePermission() async {
    try {
      await _hostAPI.requestMainAppMicrophonePermission();
    } catch (e) {
      debugPrint('Watch Transport: Error requesting mic permission: $e');
      rethrow;
    }
  }

  @override
  Future<void> dispose() async {
    for (final timer in _periodicTimers.values) {
      timer.cancel();
    }
    _periodicTimers.clear();

    for (final controller in _streamControllers.values) {
      _audioControllers.remove(controller);
      _batteryControllers.remove(controller);
      await controller.close();
    }
    _streamControllers.clear();

    await _connectionStateController.close();
  }
}
