import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/watch_transport.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String watchBatteryServiceUuid = 'watch-battery-service';
const String watchBatteryLevelCharacteristicUuid = 'watch-battery-level';
const String watchAudioServiceUuid = 'watch-audio-service';
const String watchAudioDataCharacteristicUuid = 'watch-audio-data';
const String watchRecordingControlCharacteristicUuid = 'watch-recording-control';
const String watchDeviceInfoServiceUuid = 'watch-device-info-service';
const String watchModelCharacteristicUuid = 'watch-model';
const String watchFirmwareCharacteristicUuid = 'watch-firmware';

class AppleWatchDeviceConnection extends DeviceConnection {
  AppleWatchDeviceConnection(
    super.device,
    super.transport,
  );

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
    bool autoConnect = false,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged, autoConnect: autoConnect);

    // Check for any recording that should be restarted
    await checkAndStartRecordingOnRelaunch();
  }

  /// Returns true if recording started, false if permission is needed
  Future<bool> checkPermissionAndStartRecording() async {
    try {
      if (transport is WatchTransport) {
        final watchTransport = transport as WatchTransport;
        final bool hasPermission = await watchTransport.checkMainAppMicrophonePermission();
        debugPrint('Apple Watch: Microphone permission status: $hasPermission');

        if (hasPermission) {
          await watchTransport.startRecording();
          return true;
        } else {
          debugPrint('Apple Watch: Microphone permission not granted - need to request');
          return false;
        }
      }
      return false;
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

      if (transport is WatchTransport) {
        final watchTransport = transport as WatchTransport;
        await watchTransport.requestMainAppMicrophonePermission();
      }
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

      if (transport is WatchTransport) {
        final watchTransport = transport as WatchTransport;
        final bool hasPermission = await watchTransport.checkMainAppMicrophonePermission();

        if (hasPermission) {
          // Clear the flag and start recording
          await _setWaitingForPermissionFlag(false);
          await watchTransport.startRecording();
        } else {
          // Permission still not granted
          await _setWaitingForPermissionFlag(false);
        }
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
    return await transport.isConnected();
  }

  @override
  Future<void> disconnect() async {
    await transport.disconnect();
    connectionState = DeviceConnectionState.disconnected;
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final result = await transport.readCharacteristic(watchBatteryServiceUuid, watchBatteryLevelCharacteristicUuid);
      return result.isNotEmpty ? result[0] : -1;
    } catch (e) {
      debugPrint('Apple Watch: Error getting battery level: $e');
      return -1;
    }
  }

  Future<Map<String, String>> getDeviceInfo() async {
    if (transport is WatchTransport) {
      final watchTransport = transport as WatchTransport;
      return await watchTransport.getWatchInfo();
    }
    return {};
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int p1)? onBatteryLevelChange,
  }) async {
    final stream = transport.getCharacteristicStream(watchBatteryServiceUuid, watchBatteryLevelCharacteristicUuid);

    final subscription = stream.listen((batteryData) {
      if (batteryData.isNotEmpty) {
        final batteryLevel = batteryData[0];
        onBatteryLevelChange?.call(batteryLevel);
      }
    });

    return subscription;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int> p1) onAudioBytesReceived,
  }) async {
    final stream = transport.getCharacteristicStream(watchAudioServiceUuid, watchAudioDataCharacteristicUuid);

    final subscription = stream.listen((bytes) {
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
  Future<void> performSetMicGain(int gain) async {
    return;
  }

  @override
  Future<int?> performGetMicGain() async {
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
