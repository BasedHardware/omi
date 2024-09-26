import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/services/devices/device_connection.dart';
import 'package:friend_private/services/devices/frame_connection.dart';
import 'package:friend_private/services/devices/models.dart';

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
  if (deviceTypeMap.containsKey(device.remoteId.toString())) {
    return deviceTypeMap[device.remoteId.toString()];
  }
  DeviceType? deviceType;
  await device.discoverServices();
  if (device.servicesList.where((s) => s.uuid == Guid(friendServiceUuid)).isNotEmpty) {
    // Check if the device has the image data stream characteristic
    final hasImageStream = device.servicesList
        .where((s) => s.uuid == friendServiceUuid)
        .expand((s) => s.characteristics)
        .any((c) => c.uuid.toString().toLowerCase() == imageDataStreamCharacteristicUuid.toLowerCase());
    deviceType = hasImageStream ? DeviceType.openglass : DeviceType.friend;
  } else if (device.servicesList.where((s) => s.uuid == Guid(frameServiceUuid)).isNotEmpty) {
    deviceType = DeviceType.frame;
  }
  if (deviceType != null) {
    deviceTypeMap[device.remoteId.toString()] = deviceType;
  }
  return deviceType;
}

enum DeviceType {
  friend,
  openglass,
  frame,
}

Map<String, DeviceType> deviceTypeMap = {};

class BTDeviceStruct {
  String name;
  String id;
  int? rssi;
  List<int>? fwver;
  DeviceType? type;

  BTDeviceStruct({required this.id, required this.name, this.rssi, this.fwver, this.type}) {
    if (type != null) {
      deviceTypeMap[id] = type!;
    } else if (deviceTypeMap.containsKey(id)) {
      type = deviceTypeMap[id];
    }
  }

  String getShortId() => BTDeviceStruct.shortId(id);

  static shortId(String id) {
    try {
      return id.replaceAll(':', '').split('-').last.substring(0, 6);
    } catch (e) {
      return id.length > 6 ? id.substring(0, 6) : id;
    }
  }

  factory BTDeviceStruct.fromJson(Map<String, dynamic> json) {
    var fwver = json['fwver'] as List<dynamic>?;
    if (fwver != null) {
      if (fwver.firstOrNull is int) {
        fwver = fwver.map((e) => e as int).toList();
      } else if (fwver.firstOrNull is String) {
        fwver = (fwver.firstOrNull as String).split('.').map((e) => int.parse(e.replaceFirst('v', ''))).toList();
      } else {
        fwver = null;
      }
    }
    return BTDeviceStruct(
      id: json['id'] as String,
      name: json['name'] as String,
      rssi: json['rssi'] as int?,
      fwver: fwver as List<int>?,
      type: json['type'] == null
          ? null
          : DeviceType.values.firstWhere((e) => e.name.toLowerCase() == json['type'].toLowerCase()),
    );
  }

  Map<String, dynamic> toJson({bool fwverAsString = false}) =>
      {'id': id, 'name': name, 'rssi': rssi, 'fwver': fwverAsString ? fwver?.join('.') : fwver, 'type': type?.name};
}

class DeviceInfo {
  String modelNumber;
  String firmwareRevision;
  String hardwareRevision;
  String manufacturerName;
  DeviceType type;

  DeviceInfo(this.modelNumber, this.firmwareRevision, this.hardwareRevision, this.manufacturerName, this.type);

  static Future<DeviceInfo> getDeviceInfo(BTDeviceStruct? device, DeviceConnection? conn) async {
    if (device == null) {
      return DeviceInfo('Unknown', 'Unknown', 'Unknown', 'Unknown', DeviceType.friend);
    }
    if (conn == null) {
      return DeviceInfo('Unknown', 'Unknown', 'Unknown', 'Unknown', DeviceType.friend);
    }

    device.type ??= await getTypeOfBluetoothDevice(conn.bleDevice);

    if (device.type == DeviceType.friend) {
      return _getDeviceInfoFromFriend(device, conn);
    } else if (device.type == DeviceType.openglass) {
      return _getDeviceInfoFromFriend(device, conn);
    } else if (device.type == DeviceType.frame) {
      return _getDeviceInfoFromFrame(device, conn as FrameDeviceConnection);
    } else {
      return _getDeviceInfoFromFriend(device, conn);
    }
  }

  static Future<DeviceInfo> _getDeviceInfoFromFriend(BTDeviceStruct? device, DeviceConnection conn) async {
    var modelNumber = 'Friend';
    var firmwareRevision = '1.0.2';
    var hardwareRevision = 'Seeed Xiao BLE Sense';
    var manufacturerName = 'Based Hardware';

    if (device == null) {
      return DeviceInfo(modelNumber, firmwareRevision, hardwareRevision, manufacturerName, DeviceType.friend);
    }

    var deviceInformationService = await conn.getService(deviceInformationServiceUuid);
    if (deviceInformationService != null) {
      var modelNumberCharacteristic = conn.getCharacteristic(deviceInformationService, modelNumberCharacteristicUuid);
      if (modelNumberCharacteristic != null) {
        modelNumber = String.fromCharCodes(await modelNumberCharacteristic.read());
      }

      var firmwareRevisionCharacteristic =
          conn.getCharacteristic(deviceInformationService, firmwareRevisionCharacteristicUuid);
      if (firmwareRevisionCharacteristic != null) {
        firmwareRevision = String.fromCharCodes(await firmwareRevisionCharacteristic.read());
      }

      var hardwareRevisionCharacteristic =
          conn.getCharacteristic(deviceInformationService, hardwareRevisionCharacteristicUuid);
      if (hardwareRevisionCharacteristic != null) {
        hardwareRevision = String.fromCharCodes(await hardwareRevisionCharacteristic.read());
      }

      var manufacturerNameCharacteristic =
          conn.getCharacteristic(deviceInformationService, manufacturerNameCharacteristicUuid);
      if (manufacturerNameCharacteristic != null) {
        manufacturerName = String.fromCharCodes(await manufacturerNameCharacteristic.read());
      }
    }

    var type = DeviceType.friend;
    if (device.type == DeviceType.openglass) {
      type = DeviceType.openglass;
    } else {
      final friendService = await conn.getService(friendServiceUuid);
      if (friendService != null) {
        var imageCaptureControlCharacteristic =
            conn.getCharacteristic(friendService, imageDataStreamCharacteristicUuid);
        if (imageCaptureControlCharacteristic != null) {
          type = DeviceType.openglass;
        }
      }
    }

    return DeviceInfo(
      modelNumber,
      firmwareRevision,
      hardwareRevision,
      manufacturerName,
      type,
    );
  }

  static Future<DeviceInfo> _getDeviceInfoFromFrame(BTDeviceStruct? device, FrameDeviceConnection conn) async {
    await conn.init();
    return DeviceInfo(
      conn.modelNumber,
      conn.firmwareRevision,
      conn.hardwareRevision,
      conn.manufacturerName,
      DeviceType.frame,
    );
  }
}
