import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/gen/flutter_communicator.g.dart';
import 'package:omi/services/bridges/apple_watch_bridge.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Note: Apple Watch connectivity is not BLE; this class provides no-op/default
/// implementations for BLE-specific operations so it can be wired into the
/// app's existing device management pipeline. Platform-specific watch
/// communication (WCSession) should be integrated on top of this class
class AppleWatchDeviceConnection extends DeviceConnection {
  static AppleWatchFlutterBridge? _bridge;
  static final List<StreamController<List<int>>> _audioControllers = [];
  static final List<StreamController<List<int>>> _batteryControllers = [];

  final WatchRecorderHostAPI _hostAPI = WatchRecorderHostAPI();
  StreamController<List<int>>? _audioBytesController;
  StreamController<List<int>>? _batteryController;

  AppleWatchDeviceConnection(
    super.device,
    super.bleDevice,
  );

  void _ensurePigeonSetup() {
    if (_bridge == null) {
      _bridge = AppleWatchFlutterBridge(
        onChunk: (Uint8List bytes, int chunkIndex, bool isLast, double sampleRate) {
          _audioControllers.removeWhere((controller) => controller.isClosed);

          if (_audioControllers.isNotEmpty) {
            for (final controller in _audioControllers) {
              try {
                controller.add(bytes);
              } catch (e) {
                debugPrint('Apple Watch: Error forwarding to controller: $e');
              }
            }
          } else {
            debugPrint('Apple Watch: WARNING - No active audio controllers to forward bytes');
          }
        },
        onRecordingStartedCb: () {
          debugPrint('Apple Watch recording started');
        },
        onRecordingStoppedCb: () {
          debugPrint('Apple Watch recording stopped');
        },
        onRecordingErrorCb: (String error) {
          debugPrint('Apple Watch recording error: $error');
        },
        onMicPermissionCb: (bool granted) {
          debugPrint('Apple Watch mic permission: $granted');
        },
        onMainAppMicPermissionCb: (bool granted) {
          debugPrint('Main app mic permission: $granted');
        },
        onBatteryUpdateCb: (double batteryLevel, int batteryState) {
          _batteryControllers.removeWhere((controller) => controller.isClosed);

          if (_batteryControllers.isNotEmpty) {
            final batteryLevelInt = batteryLevel.round();
            for (final controller in _batteryControllers) {
              try {
                controller.add([batteryLevelInt]);
              } catch (e) {
                debugPrint('Apple Watch: Error forwarding battery to controller: $e');
              }
            }
          } else {
            debugPrint('Apple Watch: WARNING - No active battery controllers to forward battery level');
          }
        },
      );
      WatchRecorderFlutterAPI.setUp(_bridge!);
    }
  }

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
  }) async {
    _ensurePigeonSetup();

    final bool supported = await _hostAPI.isWatchSessionSupported();
    final bool paired = await _hostAPI.isWatchPaired();
    final bool reachable = await _hostAPI.isWatchReachable();

    debugPrint('Apple Watch connect: supported=$supported, paired=$paired, reachable=$reachable');

    if (!supported) {
      throw DeviceConnectionException('Apple Watch session not supported on this device');
    }
    if (!paired) {
      throw DeviceConnectionException('Apple Watch not paired');
    }

    if (reachable) {
      debugPrint('Apple Watch is reachable - setting connected state');
      connectionState = DeviceConnectionState.connected;
      onConnectionStateChanged?.call(device.id, DeviceConnectionState.connected);

      await checkAndStartRecordingOnRelaunch();
    } else {
      debugPrint('Apple Watch is not reachable - setting disconnected state');
      connectionState = DeviceConnectionState.disconnected;
      onConnectionStateChanged?.call(device.id, DeviceConnectionState.disconnected);
    }
  }

  /// Check microphone permission and start recording immediately if granted
  /// Returns true if recording started, false if permission is needed
  Future<bool> checkPermissionAndStartRecording() async {
    try {
      final bool hasPermission = await _hostAPI.checkMainAppMicrophonePermission();
      debugPrint('Apple Watch: Microphone permission status: $hasPermission');

      if (hasPermission) {
        // Permission already granted - start recording immediately
        debugPrint('Apple Watch: Starting recording immediately...');
        await _hostAPI.startRecording();
        debugPrint('Apple Watch: Recording started successfully');
        return true;
      } else {
        // Permission not granted - caller should show dialog
        debugPrint('Apple Watch: Microphone permission not granted - need to request');
        return false;
      }
    } catch (e) {
      debugPrint('Apple Watch: Error checking permission/starting recording: $e');
      return false;
    }
  }

  /// Request microphone permission and handle app relaunch
  Future<void> requestPermissionAndStartRecording() async {
    try {
      debugPrint('Apple Watch: Requesting microphone permission...');

      await _setWaitingForPermissionFlag(true);

      await _hostAPI.requestMainAppMicrophonePermission();
    } catch (e) {
      debugPrint('Apple Watch: Error requesting permission: $e');
      await _setWaitingForPermissionFlag(false);
    }
  }

  Future<void> checkAndStartRecordingOnRelaunch() async {
    try {
      final bool wasWaitingForPermission = await _getWaitingForPermissionFlag();
      if (!wasWaitingForPermission) {
        return;
      }

      final bool hasPermission = await _hostAPI.checkMainAppMicrophonePermission();

      if (hasPermission) {
        // Clear the flag and start recording
        await _setWaitingForPermissionFlag(false);
        await _hostAPI.startRecording();
      } else {
        // Permission still not granted
        await _setWaitingForPermissionFlag(false);
      }
    } catch (e) {
      debugPrint('Apple Watch: Error checking permission on relaunch: $e');
      await _setWaitingForPermissionFlag(false);
    }
  }

  Future<void> _setWaitingForPermissionFlag(bool waiting) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool('apple_watch_waiting_for_permission', waiting);
    } catch (e) {
      debugPrint('Apple Watch: Error setting permission flag: $e');
    }
  }

  Future<bool> _getWaitingForPermissionFlag() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getBool('apple_watch_waiting_for_permission') ?? false;
    } catch (e) {
      debugPrint('Apple Watch: Error getting permission flag: $e');
      return false;
    }
  }

  @override
  Future<bool> isConnected() async {
    final supported = await _hostAPI.isWatchSessionSupported();
    if (!supported) return false;
    final paired = await _hostAPI.isWatchPaired();
    if (!paired) return false;
    final reachable = await _hostAPI.isWatchReachable();
    return reachable;
  }

  @override
  Future<void> disconnect() async {
    connectionState = DeviceConnectionState.disconnected;

    if (_audioBytesController != null) {
      _audioControllers.remove(_audioBytesController);
      _audioBytesController?.close();
      _audioBytesController = null;
    }

    if (_batteryController != null) {
      _batteryControllers.remove(_batteryController);
      _batteryController?.close();
      _batteryController = null;
    }
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final batteryLevel = await _hostAPI.getWatchBatteryLevel();
      return batteryLevel.round();
    } catch (e) {
      debugPrint('Apple Watch: Error getting battery level: $e');
      return -1;
    }
  }

  /// Get Apple Watch battery state (0=unknown, 1=unplugged, 2=charging, 3=full)
  Future<int> getWatchBatteryState() async {
    try {
      return await _hostAPI.getWatchBatteryState();
    } catch (e) {
      debugPrint('Apple Watch: Error getting battery state: $e');
      return 0;
    }
  }

  Future<void> requestWatchBatteryUpdate() async {
    try {
      await _hostAPI.requestWatchBatteryUpdate();
    } catch (e) {
      debugPrint('Apple Watch: Error requesting battery update: $e');
    }
  }

  Future<Map<String, String>> getWatchInfo() async {
    try {
      final deviceInfo = await _hostAPI.getWatchInfo();
      return deviceInfo;
    } catch (e) {
      debugPrint('Apple Watch: Error getting device info: $e');
      return {};
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int p1)? onBatteryLevelChange,
  }) async {
    _ensurePigeonSetup();

    if (_batteryController != null) {
      _batteryControllers.remove(_batteryController);
      _batteryController?.close();
    }

    _batteryController = StreamController<List<int>>.broadcast();
    _batteryControllers.add(_batteryController!);

    final subscription = _batteryController!.stream.listen((batteryData) {
      if (batteryData.isNotEmpty) {
        final batteryLevel = batteryData[0];
        onBatteryLevelChange?.call(batteryLevel);
      }
    });

    await requestWatchBatteryUpdate();

    return subscription;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int> p1) onAudioBytesReceived,
  }) async {
    _ensurePigeonSetup();

    if (_audioBytesController != null) {
      _audioControllers.remove(_audioBytesController);
      _audioBytesController?.close();
    }

    _audioBytesController = StreamController<List<int>>.broadcast();
    _audioControllers.add(_audioBytesController!);

    final subscription = _audioBytesController!.stream.listen((bytes) {
      onAudioBytesReceived(bytes);
    });

    return subscription;
  }

  @override
  Future<List<int>> performGetButtonState() async {
    return <int>[];
  }

  @override
  Future<StreamSubscription?> performGetBleButtonListener({
    required void Function(List<int> p1) onButtonReceived,
  }) async {
    return null;
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    return BleAudioCodec.pcm16;
  }

  @override
  Future<bool> performPlayToSpeakerHaptic(int mode) async {
    return false;
  }

  @override
  Future<List<int>> performGetStorageList() async {
    return <int>[];
  }

  @override
  Future<bool> performWriteToStorage(int numFile, int command, int offset) async {
    return false;
  }

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int> p1) onStorageBytesReceived,
  }) async {
    return null;
  }

  @override
  Future cameraStartPhotoController() async {
    return null;
  }

  @override
  Future cameraStopPhotoController() async {
    return null;
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async {
    return false;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int p1)? onAccelChange,
  }) async {
    return null;
  }

  @override
  Future<int> performGetFeatures() async {
    return 0;
  }

  @override
  Future<void> performSetLedDimRatio(int ratio) async {
    return;
  }

  @override
  Future<int?> performGetLedDimRatio() async {
    return null;
  }

  @override
  Future performCameraStartPhotoController() {
    throw UnimplementedError();
  }

  @override
  Future performCameraStopPhotoController() {
    throw UnimplementedError();
  }

  @override
  Future<StreamSubscription?> performGetImageListener(
      {required void Function(OrientedImage orientedImage) onImageReceived}) {
    throw UnimplementedError();
  }
}
