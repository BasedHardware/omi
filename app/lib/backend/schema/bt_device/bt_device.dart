import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/frame_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/logger.dart';

enum BleAudioCodec {
  pcm16,
  pcm8,
  mulaw16,
  mulaw8,
  opus,
  opusFS320,
  unknown;

  @override
  String toString() => mapCodecToName(this);

  bool isOpusSupported() {
    return this == BleAudioCodec.opusFS320 || this == BleAudioCodec.opus;
  }

  String toFormattedString() {
    switch (this) {
      case BleAudioCodec.opusFS320:
        return 'OPUS (320)';
      case BleAudioCodec.opus:
        return 'OPUS';
      case BleAudioCodec.pcm16:
        return 'PCM (16kHz)';
      case BleAudioCodec.pcm8:
        return 'PCM (8kHz)';
      default:
        return toString().split('.').last.toUpperCase();
    }
  }

  int getFramesPerSecond() {
    return this == BleAudioCodec.opusFS320 ? 50 : 100;
  }

  int getFramesLengthInBytes() {
    return this == BleAudioCodec.opusFS320 ? 160 : 80;
  }

  // PDM frame size
  int getFrameSize() {
    return this == BleAudioCodec.opusFS320 ? 320 : 160;
  }
}

String mapCodecToName(BleAudioCodec codec) {
  switch (codec) {
    case BleAudioCodec.opusFS320:
      return 'opus_fs320';
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
    case 'opus_fs320':
      return BleAudioCodec.opusFS320;
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
    case BleAudioCodec.opusFS320:
      return 16000;
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
    case BleAudioCodec.opusFS320:
      return 16;
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
  if (device.servicesList.where((s) => s.uuid == Guid(omiServiceUuid)).isNotEmpty) {
    // Check if the device has the image data stream characteristic
    final hasImageStream = device.servicesList
        .where((s) => s.uuid == Guid.fromString(omiServiceUuid))
        .expand((s) => s.characteristics)
        .any((c) => c.uuid.toString().toLowerCase() == imageDataStreamCharacteristicUuid.toLowerCase());
    deviceType = hasImageStream ? DeviceType.openglass : DeviceType.omi;
  } else if (device.servicesList.where((s) => s.uuid == Guid(frameServiceUuid)).isNotEmpty) {
    deviceType = DeviceType.frame;
  }
  if (deviceType != null) {
    cachedDevicesMap[device.remoteId.toString()] = deviceType;
  }
  return deviceType;
}

enum DeviceType {
  omi,
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
        type = DeviceType.omi,
        rssi = 0,
        _modelNumber = '',
        _firmwareRevision = '',
        _hardwareRevision = '',
        _manufacturerName = '';

  // getters
  String get modelNumber => _modelNumber ?? 'Unknown';
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

    if (type == DeviceType.omi) {
      return await _getDeviceInfoFromOmi(conn);
    } else if (type == DeviceType.openglass) {
      return await _getDeviceInfoFromOmi(conn);
    } else if (type == DeviceType.frame) {
      return await _getDeviceInfoFromFrame(conn as FrameDeviceConnection);
    } else {
      return await _getDeviceInfoFromOmi(conn);
    }
  }

  Future _getDeviceInfoFromOmi(DeviceConnection conn) async {
    var modelNumber = 'Omi Device';
    var firmwareRevision = '1.0.2';
    var hardwareRevision = 'Seeed Xiao BLE Sense';
    var manufacturerName = 'Based Hardware';
    var t = DeviceType.omi;
    try {
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

      if (type == DeviceType.openglass) {
        t = DeviceType.openglass;
      } else {
        final omiService = await conn.getService(omiServiceUuid);
        if (omiService != null) {
          var imageCaptureControlCharacteristic = conn.getCharacteristic(omiService, imageDataStreamCharacteristicUuid);
          if (imageCaptureControlCharacteristic != null) {
            t = DeviceType.openglass;
          }
        }
      }
    } on PlatformException catch (e) {
      Logger.error('Device Disconnected while getting device info: $e');
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
      type: DeviceType.omi,
      rssi: rssi,
    );
  }

  // from ScanResult
  static fromScanResult(ScanResult result) {
    DeviceType? deviceType;
    if (result.advertisementData.serviceUuids.contains(Guid(omiServiceUuid))) {
      deviceType = DeviceType.omi;
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
      type: deviceType ?? DeviceType.omi,
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
