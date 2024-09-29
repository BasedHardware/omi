import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device_info.dart';
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
  BtDeviceInfo? _info;

  BtDevice({required this.name, required this.id, required this.type, required this.rssi, BtDeviceInfo? info}) {
    if (info != null) {
      _info = info;
    }
  }

  BtDeviceInfo? get info => _info;

  String getShortId() => BtDevice.shortId(id);

  static shortId(String id) {
    try {
      return id.replaceAll(':', '').split('-').last.substring(0, 6);
    } catch (e) {
      return id.length > 6 ? id.substring(0, 6) : id;
    }
  }

  Future<BtDevice> updateDeviceInfo(DeviceConnection? conn) async {
    if (conn == null) {
      return this;
    }
    _info = await getDeviceInfo(conn);
    return this;
  }

  Future<BtDeviceInfo> getDeviceInfo(DeviceConnection? conn) async {
    if (conn == null) {
      if (SharedPreferencesUtil().btDevice.id.isNotEmpty) {
        var device = SharedPreferencesUtil().btDevice;
        return device.info ?? BtDeviceInfo('Unknown22', 'Unknown', 'Unknown', 'Unknown', device.type);
      } else {
        return BtDeviceInfo('Unknown33', 'Unknown', 'Unknown', 'Unknown', DeviceType.friend);
      }
    }

    if (type == DeviceType.friend) {
      _info = await _getDeviceInfoFromFriend(conn);
    } else if (type == DeviceType.openglass) {
      _info = await _getDeviceInfoFromFriend(conn);
    } else if (type == DeviceType.frame) {
      _info = await _getDeviceInfoFromFrame(conn as FrameDeviceConnection);
    } else {
      _info = await _getDeviceInfoFromFriend(conn);
    }
    return _info!;
  }

  Future<BtDeviceInfo> _getDeviceInfoFromFriend(DeviceConnection conn) async {
    var modelNumber = 'Friend';
    var firmwareRevision = '1.0.2';
    var hardwareRevision = 'Seeed Xiao BLE Sense';
    var manufacturerName = 'Based Hardware';

    // if (device == null) {
    //   return BtDeviceInfo(modelNumber, firmwareRevision, hardwareRevision, manufacturerName, DeviceType.friend);
    // }

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

    return BtDeviceInfo(
      modelNumber,
      firmwareRevision,
      hardwareRevision,
      manufacturerName,
      t,
    );
  }

  static Future<BtDeviceInfo> _getDeviceInfoFromFrame(FrameDeviceConnection conn) async {
    await conn.init();
    return BtDeviceInfo(
      conn.modelNumber,
      conn.firmwareRevision,
      conn.hardwareRevision,
      conn.manufacturerName,
      DeviceType.frame,
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
    );
  }

  // to json
  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'id': id,
      'type': type.index,
      'rssi': rssi,
    };
  }
}
