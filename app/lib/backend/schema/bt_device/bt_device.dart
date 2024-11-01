import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/services/devices/device_connection.dart';
import 'package:friend_private/services/devices/frame_connection.dart';
import 'package:friend_private/services/devices/models.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/utils/enums.dart';
import 'dart:math' show min;

enum BleAudioCodec {
  pcm16,
  pcm8,
  mulaw16,
  mulaw8,
  opus,
  unknown;

  @override
  String toString() => mapCodecToName(this);
}

String mapCodecToName(BleAudioCodec codec) {
  switch (codec) {
    case BleAudioCodec.opus:
      return 'opus';
    case BleAudioCodec.pcm16:
      return 'pcm16';
    case BleAudioCodec.pcm8:
      return 'pcm8';
    default:
      return 'pcm8';
  }
}

BleAudioCodec mapNameToCodec(String codec) {
  switch (codec) {
    case 'opus':
      return BleAudioCodec.opus;
    case 'pcm16':
      return BleAudioCodec.pcm16;
    case 'pcm8':
      return BleAudioCodec.pcm8;
    default:
      return BleAudioCodec.pcm8;
  }
}

int mapCodecToSampleRate(BleAudioCodec codec) {
  switch (codec) {
    case BleAudioCodec.opus:
      return 16000;
    case BleAudioCodec.pcm16:
      return 16000;
    case BleAudioCodec.pcm8:
      return 16000;
    default:
      return 16000;
  }
}

int mapCodecToBitDepth(BleAudioCodec codec) {
  switch (codec) {
    case BleAudioCodec.opus:
      return 16;
    case BleAudioCodec.pcm16:
      return 16;
    case BleAudioCodec.pcm8:
      return 8;
    default:
      return 16;
  }
}

Future<DeviceType?> getTypeOfBluetoothDevice(BluetoothDevice device) async {
  if (cachedDevicesMap.containsKey(device.remoteId.toString())) {
    return cachedDevicesMap[device.remoteId.toString()];
  }
  DeviceType? deviceType;
  await device.discoverServices();
  if (device.servicesList.where((s) => s.uuid == Guid(friendServiceUuid)).isNotEmpty) {
    // Check if the device has the image data stream characteristic
    final hasImageStream = device.servicesList
        .where((s) => s.uuid == Guid.fromString(friendServiceUuid))
        .expand((s) => s.characteristics)
        .any((c) => c.uuid.toString().toLowerCase() == imageDataStreamCharacteristicUuid.toLowerCase());
    deviceType = hasImageStream ? DeviceType.openglass : DeviceType.friend;
  } else if (device.servicesList.where((s) => s.uuid == Guid(frameServiceUuid)).isNotEmpty) {
    deviceType = DeviceType.frame;
  }
  if (deviceType != null) {
    cachedDevicesMap[device.remoteId.toString()] = deviceType;
  }
  return deviceType;
}

enum DeviceType {
  friend,
  openglass,
  necklace,
  frame,
  watch,
}

Map<String, DeviceType> cachedDevicesMap = {};

class BtDevice {
  final String id;
  final String name;
  final DeviceType type;
  final DeviceConnectionState? status;
  final String? firmwareRevision;
  final String? hardwareRevision;
  final String? modelNumber;
  final String? manufacturerName;

  const BtDevice({
    required this.id,
    required this.name,
    required this.type,
    this.status = DeviceConnectionState.disconnected,
    this.firmwareRevision,
    this.hardwareRevision,
    this.modelNumber,
    this.manufacturerName,
  });

  factory BtDevice.empty() {
    return const BtDevice(
      id: '',
      name: '',
      type: DeviceType.friend,
    );
  }

  String getShortId() {
    return id.substring(0, min(8, id.length));
  }

  static String shortId(String id) {
    return id.substring(0, min(8, id.length));
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'type': type.toString(),
      'status': status?.toString(),
      'firmwareRevision': firmwareRevision,
      'hardwareRevision': hardwareRevision,
      'modelNumber': modelNumber,
      'manufacturerName': manufacturerName,
    };
  }

  factory BtDevice.fromJson(Map<String, dynamic> json) {
    return BtDevice(
      id: json['id'] as String,
      name: json['name'] as String,
      type: DeviceType.values.firstWhere(
        (e) => e.toString() == json['type'],
        orElse: () => DeviceType.friend,
      ),
      status: json['status'] == null
          ? null
          : DeviceConnectionState.values.firstWhere(
              (e) => e.toString() == json['status'],
              orElse: () => DeviceConnectionState.disconnected,
            ),
      firmwareRevision: json['firmwareRevision'] as String?,
      hardwareRevision: json['hardwareRevision'] as String?,
      modelNumber: json['modelNumber'] as String?,
      manufacturerName: json['manufacturerName'] as String?,
    );
  }

  Future<BtDevice> getDeviceInfo(DeviceConnection connection) async {
    // Implementation to get device info
    return this;
  }
}
