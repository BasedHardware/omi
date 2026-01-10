import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';

const String _photoHeader =
    "/9j/4AAQSkZJRgABAgAAZABkAAD/2wBDACAWGBwYFCAcGhwkIiAmMFA0MCwsMGJGSjpQdGZ6eHJmcG6AkLicgIiuim5woNqirr7EztDOfJri8uDI8LjKzsb/2wBDASIkJDAqMF40NF7GhHCExsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsbGxsb/wAARCAIAAgADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwA=";

class FrameDeviceConnection extends DeviceConnection {
  // Frame-specific properties
  late String name;
  String? _firmwareRevision;
  String? _hardwareRevision;
  String? _modelNumber;
  int? _batteryLevel;

  FrameDeviceConnection(super.device, super.transport);

  get deviceId => device.id;

  String get firmwareRevision {
    return _firmwareRevision ?? 'Unknown';
  }

  String get hardwareRevision {
    return _hardwareRevision ?? 'Unknown';
  }

  String get manufacturerName => "Brilliant Labs";

  String get modelNumber {
    return _modelNumber ?? 'Unknown';
  }

  // Frame SDK initialization is now handled by FrameTransport

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
    bool autoConnect = false,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged, autoConnect: autoConnect);
    try {
      _firmwareRevision = 'Frame';
      _batteryLevel = await performRetrieveBatteryLevel();
    } catch (e) {
      debugPrint('FrameDeviceConnection: Error getting device info: $e');
    }
  }

  // Frame SDK methods are now handled by FrameTransport

  @override
  Future<bool> isConnected() async {
    return connectionState == DeviceConnectionState.connected;
  }

  @override
  Future<void> performCameraStartPhotoController() async {
    try {
      // Frame camera control via transport
      await transport.writeCharacteristic('frame-camera-service', 'frame-camera-control', [0x01]); // START
      debugPrint('Frame camera started');
    } catch (e) {
      debugPrint('FrameDeviceConnection: Error starting camera: $e');
    }
  }

  @override
  Future<void> performCameraStopPhotoController() async {
    try {
      await transport.writeCharacteristic('frame-camera-service', 'frame-camera-control', [0x00]); // STOP
      debugPrint('Frame camera stopped');
    } catch (e) {
      debugPrint('FrameDeviceConnection: Error stopping camera: $e');
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async {
    return null;
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() {
    return Future.value(BleAudioCodec.pcm8);
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener(
      {required void Function(List<int>) onAudioBytesReceived}) async {
    try {
      final stream = transport.getCharacteristicStream('frame-audio-service', 'frame-audio-characteristic');

      debugPrint('Subscribed to audioBytes stream from Frame Device');
      final subscription = stream.listen((value) {
        if (value.isNotEmpty) onAudioBytesReceived(value);
      });

      await transport.writeCharacteristic('frame-audio-service', 'frame-audio-control', [0x01]);

      return subscription;
    } catch (e) {
      debugPrint('FrameDeviceConnection: Error setting up audio listener: $e');
      return null;
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener(
      {void Function(int)? onBatteryLevelChange}) async {
    try {
      final stream = transport.getCharacteristicStream('frame-battery-service', 'frame-battery-characteristic');

      final subscription = stream.listen((value) {
        if (value.isNotEmpty && onBatteryLevelChange != null) {
          final currentLevel = value[0];
          if (currentLevel != _batteryLevel) {
            _batteryLevel = currentLevel;
            onBatteryLevelChange(currentLevel);
          }
        }
      });

      return subscription;
    } catch (e) {
      debugPrint('FrameDeviceConnection: Error setting up battery listener: $e');
      return null;
    }
  }

  @override
  Future<StreamSubscription?> performGetBleButtonListener({required void Function(List<int>) onButtonReceived}) async {
    return null;
  }

  // @override
  //  Future<List<int>> performGetStorageList() {

  //   return <int>[];
  //  }
  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) {
    return Future.value(null);
  }

  @override
  Future<List<int>> performGetButtonState() async {
    return Future.value(<int>[]);
  }

  @override
  Future<int> performGetFeatures() {
    // Frame does not support features check
    return Future.value(0);
  }

  @override
  Future<StreamSubscription?> performGetImageListener(
      {required void Function(OrientedImage orientedImage) onImageReceived}) async {
    try {
      final stream = transport.getCharacteristicStream('frame-image-service', 'frame-image-characteristic');

      final subscription = stream.listen((value) {
        if (value.isNotEmpty) {
          final header = base64.decode(_photoHeader);
          final combinedData = Uint8List.fromList([...header, ...value]);
          onImageReceived(OrientedImage(
            imageBytes: combinedData,
            orientation: ImageOrientation.orientation0,
          ));
        }
      });

      return subscription;
    } catch (e) {
      debugPrint('FrameDeviceConnection: Error setting up image listener: $e');
      return null;
    }
  }

  @override
  Future<int?> performGetLedDimRatio() {
    // Frame does not support LED dimming
    return Future.value(null);
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
  Future<List<int>> performGetStorageList() {
    return Future.value(<int>[]);
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() {
    return Future.value(true);
  }

  @override
  Future<bool> performPlayToSpeakerHaptic(int mode) async {
    return false;
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      // Frame battery level via transport
      final data = await transport.readCharacteristic('frame-battery-service', 'frame-battery-characteristic');
      if (data.isNotEmpty) {
        _batteryLevel = data[0];
        return _batteryLevel!;
      }
      return _batteryLevel ?? -1;
    } catch (e) {
      debugPrint('FrameDeviceConnection: Error reading battery level: $e');
      return -1;
    }
  }

  @override
  Future<void> performSetLedDimRatio(int ratio) async {
    // Frame does not support LED dimming
  }

  @override
  Future<bool> performWriteToStorage(int numFile, int command, int offset) {
    return Future.value(false);
  }

  /// Get device information from Frame device
  Future<Map<String, String>> getDeviceInfo() async {
    Map<String, String> deviceInfo = {};

    try {
      // Read firmware version from Frame
      try {
        final firmwareValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, firmwareRevisionCharacteristicUuid);
        if (firmwareValue.isNotEmpty) {
          deviceInfo['firmwareRevision'] = String.fromCharCodes(firmwareValue);
        }
      } catch (e) {
        debugPrint('FrameDeviceConnection: Error reading firmware revision: $e');
      }

      // Read battery level to confirm device is responsive
      try {
        final batteryValue = await transport.readCharacteristic(batteryServiceUuid, batteryLevelCharacteristicUuid);
        if (batteryValue.isNotEmpty) {
          deviceInfo['batteryLevel'] = batteryValue[0].toString();
        }
      } catch (e) {
        debugPrint('FrameDeviceConnection: Error reading battery level: $e');
      }
    } catch (e) {
      debugPrint('FrameDeviceConnection: Error getting device info: $e');
    }

    // Set Frame-specific defaults
    deviceInfo['modelNumber'] ??= 'Frame';
    deviceInfo['firmwareRevision'] ??= 'Unknown';
    deviceInfo['hardwareRevision'] ??= 'Brilliant Labs Frame';
    deviceInfo['manufacturerName'] ??= 'Brilliant Labs';

    return deviceInfo;
  }

  // Existing getters already provide backward compatibility

  // Frame SDK helper methods are now handled by FrameTransport
}
