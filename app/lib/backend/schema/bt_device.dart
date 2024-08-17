import 'package:friend_private/utils/ble/gatt_utils.dart';

enum BleAudioCodec { pcm16, pcm8, mulaw16, mulaw8, opus, unknown }

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

class BTDeviceStruct {
  String name;
  String id;
  int? rssi;
  List<int>? fwver;

  BTDeviceStruct({
    required this.id,
    required this.name,
    this.rssi,
    this.fwver,
  });

  String getShortId() => BTDeviceStruct.shortId(id);

  static shortId(String id) {
    try {
      return id.replaceAll(':', '').split('-').last.substring(0, 6);
    } catch (e) {
      return id.length > 6 ? id.substring(0, 6) : id;
    }
  }

  factory BTDeviceStruct.fromJson(Map<String, dynamic> json) {
    return BTDeviceStruct(
      id: json['id'] as String,
      name: json['name'] as String,
      rssi: json['rssi'] as int?,
      fwver: json['fwver'] as List<int>?,
    );
  }

  Map<String, dynamic> toJson() => {'id': id, 'name': name, 'rssi': rssi, 'fwver': fwver?.toList()};
}

class DeviceInfo {
  String modelNumber;
  String firmwareRevision;
  String hardwareRevision;
  String manufacturerName;

  DeviceInfo(this.modelNumber, this.firmwareRevision, this.hardwareRevision, this.manufacturerName);

  static Future<DeviceInfo> getDeviceInfo(BTDeviceStruct? device) async {
    var modelNumber = 'Friend';
    var firmwareRevision = '1.0.2';
    var hardwareRevision = 'Seeed Xiao BLE Sense';
    var manufacturerName = 'Based Hardware';

    if (device == null) return DeviceInfo(modelNumber, firmwareRevision, hardwareRevision, manufacturerName);

    String deviceId = device.id;

    var deviceInformationService = await getServiceByUuid(deviceId, deviceInformationServiceUuid);
    if (deviceInformationService != null) {
      var modelNumberCharacteristic = getCharacteristicByUuid(deviceInformationService, modelNumberCharacteristicUuid);
      if (modelNumberCharacteristic != null) {
        modelNumber = String.fromCharCodes(await modelNumberCharacteristic.read());
      }

      var firmwareRevisionCharacteristic =
          getCharacteristicByUuid(deviceInformationService, firmwareRevisionCharacteristicUuid);
      if (firmwareRevisionCharacteristic != null) {
        firmwareRevision = String.fromCharCodes(await firmwareRevisionCharacteristic.read());
      }

      var hardwareRevisionCharacteristic =
          getCharacteristicByUuid(deviceInformationService, hardwareRevisionCharacteristicUuid);
      if (hardwareRevisionCharacteristic != null) {
        hardwareRevision = String.fromCharCodes(await hardwareRevisionCharacteristic.read());
      }

      var manufacturerNameCharacteristic =
          getCharacteristicByUuid(deviceInformationService, manufacturerNameCharacteristicUuid);
      if (manufacturerNameCharacteristic != null) {
        manufacturerName = String.fromCharCodes(await manufacturerNameCharacteristic.read());
      }
    }

    return DeviceInfo(
      modelNumber,
      firmwareRevision,
      hardwareRevision,
      manufacturerName,
    );
  }
}
