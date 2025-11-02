import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';

class FieldyDeviceConnection extends DeviceConnection {
  FieldyDeviceConnection(super.device, super.transport);

  get deviceId => device.id;

  @override
  Future<void> connect({Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final data = await transport.readCharacteristic(batteryServiceUuid, batteryLevelCharacteristicUuid);
      if (data.isNotEmpty) return data[0];
      return -1;
    } catch (e) {
      debugPrint('Fieldy: Error reading battery level: $e');
      return -1;
    }
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(batteryServiceUuid, batteryLevelCharacteristicUuid);

      final subscription = stream.listen((value) {
        if (value.isNotEmpty && onBatteryLevelChange != null) {
          debugPrint('Battery level changed: ${value[0]}');
          onBatteryLevelChange(value[0]);
        }
      });

      return subscription;
    } catch (e) {
      debugPrint('Fieldy: Error setting up battery listener: $e');
      return null;
    }
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    return BleAudioCodec.opusFS320;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(fieldyServiceUuid, fieldyOpusAudioCharacteristicUuid);

      debugPrint('Subscribed to audioBytes stream from Fieldy Device');
      final subscription = stream.listen((value) {
        if (value.isNotEmpty) {
          // Each BLE notification contains 6 Opus frames of 40 bytes each (240 bytes total)
          const frameSize = 40;
          int offset = 0;

          while (offset + frameSize <= value.length) {
            final frame = value.sublist(offset, offset + frameSize);

            // Verify frame starts with Opus TOC byte
            if (frame[0] == 0xb8) {
              onAudioBytesReceived(frame);
            } else {
              debugPrint(
                  'Fieldy: Warning - Frame at offset $offset doesn\'t start with 0xb8: ${frame[0].toRadixString(16)}');
              onAudioBytesReceived(frame);
            }

            offset += frameSize;
          }

          if (offset < value.length) {
            final remaining = value.sublist(offset);
            debugPrint('Fieldy: Note - Found ${remaining.length}-byte frame (not 40 bytes)');
            if (remaining.isNotEmpty && remaining[0] == 0xb8) {
              onAudioBytesReceived(remaining);
            }
          }
        }
      });

      return subscription;
    } catch (e) {
      debugPrint('Fieldy: Error setting up audio listener: $e');
      return null;
    }
  }

  @override
  Future<List<int>> performGetButtonState() async {
    return <int>[];
  }

  @override
  Future<StreamSubscription?> performGetBleButtonListener({
    required void Function(List<int>) onButtonReceived,
  }) async {
    return null;
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
  Future<void> performSetLedDimRatio(int ratio) async {}

  @override
  Future<int?> performGetLedDimRatio() async {
    return null;
  }

  @override
  Future<void> performSetMicGain(int gain) async {}

  @override
  Future<int?> performGetMicGain() async {
    return null;
  }

  Future<Map<String, String>> getDeviceInfo() async {
    Map<String, String> deviceInfo = {};

    try {
      try {
        final modelValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, modelNumberCharacteristicUuid);
        if (modelValue.isNotEmpty) {
          deviceInfo['modelNumber'] = String.fromCharCodes(modelValue);
        }
      } catch (e) {
        debugPrint('Fieldy: Error reading model number: $e');
      }

      try {
        final firmwareValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, firmwareRevisionCharacteristicUuid);
        if (firmwareValue.isNotEmpty) {
          deviceInfo['firmwareRevision'] = String.fromCharCodes(firmwareValue);
        }
      } catch (e) {
        debugPrint('Fieldy: Error reading firmware revision: $e');
      }

      try {
        final hardwareValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, hardwareRevisionCharacteristicUuid);
        if (hardwareValue.isNotEmpty) {
          deviceInfo['hardwareRevision'] = String.fromCharCodes(hardwareValue);
        }
      } catch (e) {
        debugPrint('Fieldy: Error reading hardware revision: $e');
      }

      try {
        final manufacturerValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, manufacturerNameCharacteristicUuid);
        if (manufacturerValue.isNotEmpty) {
          deviceInfo['manufacturerName'] = String.fromCharCodes(manufacturerValue);
        }
      } catch (e) {
        debugPrint('Fieldy: Error reading manufacturer name: $e');
      }
    } catch (e) {
      debugPrint('Fieldy: Error getting device info: $e');
    }

    deviceInfo['modelNumber'] ??= 'Fieldy';
    deviceInfo['firmwareRevision'] ??= '1.0.0';
    deviceInfo['hardwareRevision'] ??= 'Fieldy Hardware';
    deviceInfo['manufacturerName'] ??= 'Fieldy';

    return deviceInfo;
  }
}
