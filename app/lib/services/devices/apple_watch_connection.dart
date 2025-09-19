import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/src/flutter_communicator.g.dart';
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
          debugPrint(
              'Apple Watch: Received audio chunk ${bytes.length} bytes, active controllers: ${_audioControllers.length}');

          _audioControllers.removeWhere((controller) => controller.isClosed);

          if (_audioControllers.isNotEmpty) {
            for (final controller in _audioControllers) {
              try {
                controller.add(bytes);
                debugPrint('Apple Watch: Forwarded ${bytes.length} bytes to controller');
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
          debugPrint('Apple Watch battery update: ${batteryLevel.toStringAsFixed(1)}%, state: $batteryState');

          _batteryControllers.removeWhere((controller) => controller.isClosed);

          if (_batteryControllers.isNotEmpty) {
            final batteryLevelInt = batteryLevel.round();
            for (final controller in _batteryControllers) {
              try {
                controller.add([batteryLevelInt]);
                debugPrint('Apple Watch: Forwarded battery level $batteryLevelInt% to controller');
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
      debugPrint('Apple Watch: Pigeon bridge setup completed');
    } else {
      debugPrint('Apple Watch: Pigeon bridge already exists');
    }
  }

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
  }) async {
    // No BLE connect for Apple Watch. Treat paired+reachable as connected.
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

    // Only call the callback once with the final state
    if (reachable) {
      debugPrint('Apple Watch is reachable - setting connected state');
      connectionState = DeviceConnectionState.connected;
      onConnectionStateChanged?.call(device.id, DeviceConnectionState.connected);

      // Check if we should start recording after app relaunch
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

      // Set flag indicating we're waiting for permission (watch app will close)
      await _setWaitingForPermissionFlag(true);

      // Request microphone permission - this will cause the watch app to close
      await _hostAPI.requestMainAppMicrophonePermission();

      debugPrint('Apple Watch: Permission requested - watch app will close and reopen');
    } catch (e) {
      debugPrint('Apple Watch: Error requesting permission: $e');
      await _setWaitingForPermissionFlag(false);
    }
  }

  /// Check if we should start recording on app launch (after permission was granted)
  Future<void> checkAndStartRecordingOnRelaunch() async {
    try {
      // Check if we were waiting for permission
      final bool wasWaitingForPermission = await _getWaitingForPermissionFlag();
      if (!wasWaitingForPermission) {
        debugPrint('Apple Watch: Not waiting for permission - no action needed');
        return;
      }

      debugPrint('Apple Watch: App relaunched - checking if permission was granted...');

      // Check if permission is now granted
      final bool hasPermission = await _hostAPI.checkMainAppMicrophonePermission();
      debugPrint('Apple Watch: Permission status after relaunch: $hasPermission');

      if (hasPermission) {
        // Clear the flag and start recording
        await _setWaitingForPermissionFlag(false);
        debugPrint('Apple Watch: Permission granted after relaunch - starting recording...');
        await _hostAPI.startRecording();
        debugPrint('Apple Watch: Recording started successfully after relaunch');
      } else {
        // Permission still not granted
        await _setWaitingForPermissionFlag(false);
        debugPrint('Apple Watch: Permission still not granted after relaunch');
      }
    } catch (e) {
      debugPrint('Apple Watch: Error checking permission on relaunch: $e');
      await _setWaitingForPermissionFlag(false);
    }
  }

  /// Set flag to indicate we're waiting for permission (stored in SharedPreferences)
  Future<void> _setWaitingForPermissionFlag(bool waiting) async {
    try {
      // Use SharedPreferences to persist across app restarts
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool('apple_watch_waiting_for_permission', waiting);
      debugPrint('Apple Watch: Set waiting for permission flag: $waiting');
    } catch (e) {
      debugPrint('Apple Watch: Error setting permission flag: $e');
    }
  }

  /// Get flag indicating if we're waiting for permission
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
    print('Apple Watch isSupported: $supported');
    if (!supported) return false;
    final paired = await _hostAPI.isWatchPaired();
    print('Apple Watch isPaired: $paired');
    if (!paired) return false;
    final reachable = await _hostAPI.isWatchReachable();
    print('Apple Watch isConnected: $reachable');
    return reachable;
  }

  @override
  Future<void> disconnect() async {
    // For Apple Watch, avoid calling BLE disconnect. Just notify and cleanup.
    connectionState = DeviceConnectionState.disconnected;

    // Clean up audio controller
    if (_audioBytesController != null) {
      _audioControllers.remove(_audioBytesController);
      _audioBytesController?.close();
      _audioBytesController = null;
      debugPrint('Apple Watch: Cleaned up audio controller on disconnect');
    }

    // Clean up battery controller
    if (_batteryController != null) {
      _batteryControllers.remove(_batteryController);
      _batteryController?.close();
      _batteryController = null;
      debugPrint('Apple Watch: Cleaned up battery controller on disconnect');
    }
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    // Get battery level from Apple Watch via Pigeon
    try {
      final batteryLevel = await _hostAPI.getWatchBatteryLevel();
      print('Apple Watch battery level: $batteryLevel');
      return batteryLevel.round();
    } catch (e) {
      debugPrint('Apple Watch: Error getting battery level: $e');
      return -1;
    }
  }

  /// Get Apple Watch battery level as percentage (0-100)
  Future<double> getWatchBatteryLevel() async {
    try {
      return await _hostAPI.getWatchBatteryLevel();
    } catch (e) {
      debugPrint('Apple Watch: Error getting battery level: $e');
      return 0.0;
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

  /// Request immediate battery update from Apple Watch
  Future<void> requestWatchBatteryUpdate() async {
    try {
      await _hostAPI.requestWatchBatteryUpdate();
      debugPrint('Apple Watch: Requested battery update');
    } catch (e) {
      debugPrint('Apple Watch: Error requesting battery update: $e');
    }
  }

  /// Get Apple Watch device information (name, model, system version, etc.)
  Future<Map<String, String>> getWatchInfo() async {
    try {
      final deviceInfo = await _hostAPI.getWatchInfo();
      debugPrint('Apple Watch: Device info: $deviceInfo');
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
    debugPrint('Apple Watch: Setting up battery level listener');
    _ensurePigeonSetup();

    // Clean up any existing battery controller
    if (_batteryController != null) {
      _batteryControllers.remove(_batteryController);
      _batteryController?.close();
    }

    // Create a new battery controller and register it globally
    _batteryController = StreamController<List<int>>.broadcast();
    _batteryControllers.add(_batteryController!);

    final subscription = _batteryController!.stream.listen((batteryData) {
      if (batteryData.isNotEmpty) {
        final batteryLevel = batteryData[0];
        debugPrint('Apple Watch: Battery stream received $batteryLevel% - forwarding to callback');
        onBatteryLevelChange?.call(batteryLevel);
      }
    });

    // Request initial battery update
    await requestWatchBatteryUpdate();

    debugPrint(
        'Apple Watch: Battery listener setup completed, registered controller (${_batteryControllers.length} total)');
    return subscription;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int> p1) onAudioBytesReceived,
  }) async {
    debugPrint('Apple Watch: Setting up audio bytes listener');
    _ensurePigeonSetup();

    // Clean up any existing controller
    if (_audioBytesController != null) {
      _audioControllers.remove(_audioBytesController);
      _audioBytesController?.close();
    }

    // Create a new controller and register it globally
    _audioBytesController = StreamController<List<int>>.broadcast();
    _audioControllers.add(_audioBytesController!);

    final subscription = _audioBytesController!.stream.listen((bytes) {
      debugPrint('Apple Watch: Audio stream received ${bytes.length} bytes - forwarding to WebSocket');
      onAudioBytesReceived(bytes);
    });

    debugPrint(
        'Apple Watch: Audio listener setup completed, registered controller (${_audioControllers.length} total)');
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
    // Not supported for Apple Watch via this path.
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
  Future<StreamSubscription?> performGetImageListener({
    required void Function(Uint8List base64JpgData) onImageReceived,
  }) async {
    return null;
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
}
