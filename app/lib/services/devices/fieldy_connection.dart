import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/custom_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/logger.dart';

class FieldyDeviceConnection extends CustomDeviceConnection {
  FieldyDeviceConnection(super.device, super.transport);

  @override
  String get serviceUuid => fieldyServiceUuid;

  @override
  String get controlCharacteristicUuid => "82a48422-3ca9-4156-ae67-4170f58666e0";

  @override
  String get audioCharacteristicUuid => "82a48422-3ca9-4156-ae67-4170f58666e0";

  @override
  BleAudioCodec get audioCodec => BleAudioCodec.opusFS320;

  @override
  int get unmuteCommandCode => 0x00;

  @override
  int get muteCommandCode => 0x00;

  @override
  int get batteryCommandCode => 0x00;

  @override
  List<int> get unmuteCommandData => [];

  @override
  List<int> get muteCommandData => [];

  @override
  Map<String, dynamic> parseResponse(List<int> data) {
    return {'type': 'unknown', 'data': data};
  }

  @override
  List<int>? processAudioPacket(List<int> data) {
    return data;
  }

  @override
  Map<String, dynamic>? parseBatteryResponse(List<int> payload) {
    if (payload.isEmpty) return null;
    return {'level': payload[0]};
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    try {
      final data = await transport.readCharacteristic(batteryServiceUuid, batteryLevelCharacteristicUuid);
      if (data.isNotEmpty) return data[0];
      return -1;
    } catch (e) {
      Logger.debug('Fieldy: Error reading battery level: $e');
      return -1;
    }
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    try {
      final stream = transport.getCharacteristicStream(serviceUuid, audioCharacteristicUuid);

      Logger.debug('Subscribed to audioBytes stream from Fieldy Device');
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
              Logger.debug(
                  'Fieldy: Warning - Frame at offset $offset doesn\'t start with 0xb8: ${frame[0].toRadixString(16)}');
              onAudioBytesReceived(frame);
            }

            offset += frameSize;
          }

          if (offset < value.length) {
            final remaining = value.sublist(offset);
            Logger.debug('Fieldy: Note - Found ${remaining.length}-byte frame (not 40 bytes)');
            if (remaining.isNotEmpty && remaining[0] == 0xb8) {
              onAudioBytesReceived(remaining);
            }
          }
        }
      });

      return subscription;
    } catch (e) {
      Logger.debug('Fieldy: Error setting up audio listener: $e');
      return null;
    }
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
        Logger.debug('Fieldy: Error reading model number: $e');
      }

      try {
        final firmwareValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, firmwareRevisionCharacteristicUuid);
        if (firmwareValue.isNotEmpty) {
          deviceInfo['firmwareRevision'] = String.fromCharCodes(firmwareValue);
        }
      } catch (e) {
        Logger.debug('Fieldy: Error reading firmware revision: $e');
      }

      try {
        final hardwareValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, hardwareRevisionCharacteristicUuid);
        if (hardwareValue.isNotEmpty) {
          deviceInfo['hardwareRevision'] = String.fromCharCodes(hardwareValue);
        }
      } catch (e) {
        Logger.debug('Fieldy: Error reading hardware revision: $e');
      }

      try {
        final manufacturerValue =
            await transport.readCharacteristic(deviceInformationServiceUuid, manufacturerNameCharacteristicUuid);
        if (manufacturerValue.isNotEmpty) {
          deviceInfo['manufacturerName'] = String.fromCharCodes(manufacturerValue);
        }
      } catch (e) {
        Logger.debug('Fieldy: Error reading manufacturer name: $e');
      }
    } catch (e) {
      Logger.debug('Fieldy: Error getting device info: $e');
    }

    deviceInfo['modelNumber'] ??= 'Fieldy';
    deviceInfo['firmwareRevision'] ??= '1.0.0';
    deviceInfo['hardwareRevision'] ??= 'Fieldy Hardware';
    deviceInfo['manufacturerName'] ??= 'Fieldy';

    return deviceInfo;
  }
}
