import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/preferences.dart';
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
  frame,
}

Map<String, DeviceType> cachedDevicesMap = {};

class BtDevice {
  String name;
  String id;
  DeviceType type;
  int rssi;
  String? _modelNumber;
  String? _firmwareRevision;
  String? _hardwareRevision;
  String? _manufacturerName;

  BtDevice(
      {required this.name,
      required this.id,
      required this.type,
      required this.rssi,
      String? modelNumber,
      String? firmwareRevision,
      String? hardwareRevision,
      String? manufacturerName}) {
    _modelNumber = modelNumber;
    _firmwareRevision = firmwareRevision;
    _hardwareRevision = hardwareRevision;
    _manufacturerName = manufacturerName;
  }

  // create an empty device
  BtDevice.empty()
      : name = '',
        id = '',
        type = DeviceType.friend,
        rssi = 0,
        _modelNumber = '',
        _firmwareRevision = '',
        _hardwareRevision = '',
        _manufacturerName = '';

  // getters
  String get modelNumber => _modelNumber ?? 'Unknown11';
  String get firmwareRevision => _firmwareRevision ?? 'Unknown';
  String get hardwareRevision => _hardwareRevision ?? 'Unknown';
  String get manufacturerName => _manufacturerName ?? 'Unknown';

  // set details
  set modelNumber(String modelNumber) => _modelNumber = modelNumber;
  set firmwareRevision(String firmwareRevision) => _firmwareRevision = firmwareRevision;
  set hardwareRevision(String hardwareRevision) => _hardwareRevision = hardwareRevision;
  set manufacturerName(String manufacturerName) => _manufacturerName = manufacturerName;

  String getShortId() => BtDevice.shortId(id);

  static shortId(String id) {
    try {
      return id.replaceAll(':', '').split('-').last.substring(0, 6);
    } catch (e) {
      return id.length > 6 ? id.substring(0, 6) : id;
    }
  }

  BtDevice copyWith(
      {String? name,
      String? id,
      DeviceType? type,
      int? rssi,
      String? modelNumber,
      String? firmwareRevision,
      String? hardwareRevision,
      String? manufacturerName}) {
    return BtDevice(
      name: name ?? this.name,
      id: id ?? this.id,
      type: type ?? this.type,
      rssi: rssi ?? this.rssi,
      modelNumber: modelNumber ?? _modelNumber,
      firmwareRevision: firmwareRevision ?? _firmwareRevision,
      hardwareRevision: hardwareRevision ?? _hardwareRevision,
      manufacturerName: manufacturerName ?? _manufacturerName,
    );
  }

  Future updateDeviceInfo(DeviceConnection? conn) async {
    if (conn == null) {
      return this;
    }
    return await getDeviceInfo(conn);
  }

  Future<BtDevice> getDeviceInfo(DeviceConnection? conn) async {
    if (conn == null) {
      if (SharedPreferencesUtil().btDevice.id.isNotEmpty) {
        var device = SharedPreferencesUtil().btDevice;
        return copyWith(
          id: device.id,
          name: device.name,
          type: device.type,
          rssi: device.rssi,
          modelNumber: device.modelNumber,
          firmwareRevision: device.firmwareRevision,
          hardwareRevision: device.hardwareRevision,
          manufacturerName: device.manufacturerName,
        );
      } else {
        return BtDevice.empty();
      }
    }

    if (type == DeviceType.friend) {
      return await _getDeviceInfoFromFriend(conn);
    } else if (type == DeviceType.openglass) {
      return await _getDeviceInfoFromFriend(conn);
    } else if (type == DeviceType.frame) {
      return await _getDeviceInfoFromFrame(conn as FrameDeviceConnection);
    } else {
      return await _getDeviceInfoFromFriend(conn);
    }
  }

  Future _getDeviceInfoFromFriend(DeviceConnection conn) async {
    var modelNumber = 'Friend';
    var firmwareRevision = '1.0.2';
    var hardwareRevision = 'Seeed Xiao BLE Sense';
    var manufacturerName = 'Based Hardware';

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

    var t = DeviceType.friend;
    if (type == DeviceType.openglass) {
      t = DeviceType.openglass;
    } else {
      final friendService = await conn.getService(friendServiceUuid);
      if (friendService != null) {
        var imageCaptureControlCharacteristic =
            conn.getCharacteristic(friendService, imageDataStreamCharacteristicUuid);
        if (imageCaptureControlCharacteristic != null) {
          t = DeviceType.openglass;
        }
      }
    }

    return copyWith(
      modelNumber: modelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      type: t,
    );
  }

  Future _getDeviceInfoFromFrame(FrameDeviceConnection conn) async {
    await conn.init();
    return copyWith(
      modelNumber: conn.modelNumber,
      firmwareRevision: conn.firmwareRevision,
      hardwareRevision: conn.hardwareRevision,
      manufacturerName: conn.manufacturerName,
      type: DeviceType.frame,
    );
  }

  // from BluetoothDevice
  Future fromBluetoothDevice(BluetoothDevice device) async {
    var rssi = await device.readRssi();
    return BtDevice(
      name: device.platformName,
      id: device.remoteId.str,
      type: DeviceType.friend,
      rssi: rssi,
    );
  }

  // from ScanResult
  static fromScanResult(ScanResult result) {
    DeviceType? deviceType;
    if (result.advertisementData.serviceUuids.contains(Guid(friendServiceUuid))) {
      deviceType = DeviceType.friend;
    } else if (result.advertisementData.serviceUuids.contains(Guid(frameServiceUuid))) {
      deviceType = DeviceType.frame;
    }
    if (deviceType != null) {
      cachedDevicesMap[result.device.remoteId.toString()] = deviceType;
    } else if (cachedDevicesMap.containsKey(result.device.remoteId.toString())) {
      deviceType = cachedDevicesMap[result.device.remoteId.toString()];
    }
    return BtDevice(
      name: result.device.platformName,
      id: result.device.remoteId.str,
      type: deviceType ?? DeviceType.friend,
      rssi: result.rssi,
    );
  }

  // from json
  static fromJson(Map<String, dynamic> json) {
    return BtDevice(
      name: json['name'],
      id: json['id'],
      type: DeviceType.values[json['type']],
      rssi: json['rssi'],
      modelNumber: json['modelNumber'],
      firmwareRevision: json['firmwareRevision'],
      hardwareRevision: json['hardwareRevision'],
      manufacturerName: json['manufacturerName'],
    );
  }

  // to json
  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'id': id,
      'type': type.index,
      'rssi': rssi,
      'modelNumber': modelNumber,
      'firmwareRevision': firmwareRevision,
      'hardwareRevision': hardwareRevision,
      'manufacturerName': manufacturerName,
    };
  }
}
