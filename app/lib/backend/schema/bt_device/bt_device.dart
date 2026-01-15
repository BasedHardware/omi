import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/devices/apple_watch_connection.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/fieldy_connection.dart';
import 'package:omi/services/devices/frame_connection.dart';
import 'package:omi/services/devices/friend_pendant_connection.dart';
import 'package:omi/services/devices/limitless_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/omi_connection.dart';
import 'package:omi/services/devices/plaud_connection.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/logger.dart';

enum ImageOrientation {
  orientation0, // 0 degrees
  orientation90, // 90 degrees clockwise
  orientation180, // 180 degrees
  orientation270; // 270 degrees clockwise

  factory ImageOrientation.fromValue(int value) {
    switch (value) {
      case 0:
        return ImageOrientation.orientation0;
      case 1:
        return ImageOrientation.orientation90;
      case 2:
        return ImageOrientation.orientation180;
      case 3:
        return ImageOrientation.orientation270;
      default:
        // Fallback to 0 degrees if the value is unknown
        return ImageOrientation.orientation0;
    }
  }
}

enum BleAudioCodec {
  pcm16,
  pcm8,
  mulaw16,
  mulaw8,
  opus,
  opusFS320,
  aac,
  lc3FS1030,
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
      case BleAudioCodec.aac:
        return 'AAC';
      case BleAudioCodec.lc3FS1030:
        return 'LC3 (10ms/30B)';
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

  /// Check if this codec is supported for custom STT providers
  bool get isCustomSttSupported {
    return this == BleAudioCodec.pcm8 ||
        this == BleAudioCodec.pcm16 ||
        this == BleAudioCodec.opus ||
        this == BleAudioCodec.opusFS320;
  }

  /// Get a user-friendly description of why custom STT isn't supported
  String get customSttUnsupportedReason {
    switch (this) {
      case BleAudioCodec.mulaw8:
      case BleAudioCodec.mulaw16:
        return 'µ-law audio format';
      case BleAudioCodec.aac:
        return 'AAC audio format';
      case BleAudioCodec.lc3FS1030:
        return 'LC3 audio format';
      case BleAudioCodec.unknown:
        return 'unknown audio format';
      default:
        return 'this audio format';
    }
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
    case BleAudioCodec.aac:
      return 'aac';
    case BleAudioCodec.lc3FS1030:
      return 'lc3_fs1030';
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
    case 'aac':
      return BleAudioCodec.aac;
    case 'lc3_fs1030':
      return BleAudioCodec.lc3FS1030;
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
    case BleAudioCodec.lc3FS1030:
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
    case BleAudioCodec.lc3FS1030:
      return 16;
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

  // Check for device types using helper methods
  if (BtDevice.isBeeDeviceFromDevice(device)) {
    deviceType = DeviceType.bee;
  } else if (BtDevice.isPlaudDeviceFromDevice(device)) {
    deviceType = DeviceType.plaud;
  } else if (BtDevice.isFieldyDeviceFromDevice(device)) {
    deviceType = DeviceType.fieldy;
  } else if (BtDevice.isFriendPendantDeviceFromDevice(device)) {
    deviceType = DeviceType.friendPendant;
  } else if (BtDevice.isLimitlessDeviceFromDevice(device)) {
    deviceType = DeviceType.limitless;
  } else if (BtDevice.isOmiDeviceFromDevice(device)) {
    // Check if the device has the image data stream characteristic
    final hasImageStream = device.servicesList
        .where((s) => s.uuid == Guid.fromString(omiServiceUuid))
        .expand((s) => s.characteristics)
        .any((c) => c.uuid.toString().toLowerCase() == imageDataStreamCharacteristicUuid.toLowerCase());
    deviceType = hasImageStream ? DeviceType.openglass : DeviceType.omi;
  } else if (BtDevice.isFrameDeviceFromDevice(device)) {
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
  appleWatch,
  plaud,
  bee,
  fieldy,
  friendPendant,
  limitless,
}

Map<String, DeviceType> cachedDevicesMap = {};

class BtDevice {
  String name;
  String id;
  DeviceType type;
  int rssi;
  // Protocol-agnostic discovery locator for post-discovery connection
  final DeviceLocator? locator;
  String? _modelNumber;
  String? _firmwareRevision;
  String? _hardwareRevision;
  String? _manufacturerName;

  BtDevice(
      {required this.name,
      required this.id,
      required this.type,
      required this.rssi,
      this.locator,
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
        locator = null,
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
      if (id == 'apple-watch') {
        return 'watchOS';
      }
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
      DeviceLocator? locator,
      String? modelNumber,
      String? firmwareRevision,
      String? hardwareRevision,
      String? manufacturerName}) {
    return BtDevice(
      name: name ?? this.name,
      id: id ?? this.id,
      type: type ?? this.type,
      rssi: rssi ?? this.rssi,
      locator: locator ?? this.locator,
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

    if (type == DeviceType.bee) {
      return await _getDeviceInfoFromBee(conn);
    } else if (type == DeviceType.plaud) {
      return await _getDeviceInfoFromPlaud(conn as PlaudDeviceConnection);
    } else if (type == DeviceType.fieldy) {
      return await _getDeviceInfoFromFieldy(conn);
    } else if (type == DeviceType.friendPendant) {
      return await _getDeviceInfoFromFriendPendant(conn);
    } else if (type == DeviceType.limitless) {
      return await _getDeviceInfoFromLimitless(conn as LimitlessDeviceConnection);
    } else if (type == DeviceType.omi) {
      return await _getDeviceInfoFromOmi(conn);
    } else if (type == DeviceType.openglass) {
      return await _getDeviceInfoFromOmi(conn);
    } else if (type == DeviceType.frame) {
      return await _getDeviceInfoFromFrame(conn as FrameDeviceConnection);
    } else if (type == DeviceType.appleWatch) {
      return await _getDeviceInfoFromAppleWatch(conn as AppleWatchDeviceConnection);
    } else {
      return await _getDeviceInfoFromOmi(conn);
    }
  }

  Future _getDeviceInfoFromOmi(DeviceConnection conn) async {
    var modelNumber = 'Omi';
    var firmwareRevision = '1.0.2';
    var hardwareRevision = 'Seeed Xiao BLE Sense';
    var manufacturerName = 'Based Hardware';
    var t = DeviceType.omi;

    try {
      if (conn is OmiDeviceConnection) {
        final deviceInfo = await conn.getDeviceInfo();

        modelNumber = deviceInfo['modelNumber'] ?? modelNumber;
        firmwareRevision = deviceInfo['firmwareRevision'] ?? firmwareRevision;
        hardwareRevision = deviceInfo['hardwareRevision'] ?? hardwareRevision;
        manufacturerName = deviceInfo['manufacturerName'] ?? manufacturerName;

        // Check if device has image streaming capability (OpenGlass detection)
        if (type == DeviceType.openglass) {
          t = DeviceType.openglass;
        } else if (deviceInfo['hasImageStream'] == 'true') {
          t = DeviceType.openglass;
        }
      }
    } on PlatformException catch (e) {
      Logger.error('Device Disconnected while getting device info: $e');
    } catch (e) {
      Logger.error('Error getting Omi device info: $e');
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
    var modelNumber = 'Frame';
    var firmwareRevision = 'Unknown';
    var hardwareRevision = 'Brilliant Labs Frame';
    var manufacturerName = 'Brilliant Labs';

    try {
      final deviceInfo = await conn.getDeviceInfo();

      modelNumber = deviceInfo['modelNumber'] ?? modelNumber;
      firmwareRevision = deviceInfo['firmwareRevision'] ?? firmwareRevision;
      hardwareRevision = deviceInfo['hardwareRevision'] ?? hardwareRevision;
      manufacturerName = deviceInfo['manufacturerName'] ?? manufacturerName;
    } catch (e) {
      Logger.error('Error getting Frame device info: $e');
    }

    return copyWith(
      modelNumber: modelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      type: DeviceType.frame,
    );
  }

  Future _getDeviceInfoFromAppleWatch(AppleWatchDeviceConnection conn) async {
    var modelNumber = 'Apple Watch';
    var firmwareRevision = 'Unknown';
    var hardwareRevision = 'Unknown';
    var manufacturerName = 'Apple';

    try {
      final deviceInfo = await conn.getDeviceInfo();

      modelNumber = deviceInfo['modelNumber'] ?? modelNumber;
      firmwareRevision = deviceInfo['firmwareRevision'] ?? firmwareRevision;
      hardwareRevision = deviceInfo['hardwareRevision'] ?? hardwareRevision;
      manufacturerName = deviceInfo['manufacturerName'] ?? manufacturerName;
    } catch (e) {
      Logger.error('Error getting Apple Watch device info: $e');
    }

    return copyWith(
      modelNumber: modelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      type: DeviceType.appleWatch,
    );
  }

  Future _getDeviceInfoFromBee(DeviceConnection conn) async {
    var modelNumber = 'Bee';
    var firmwareRevision = '1.0.0';
    var hardwareRevision = '1.0.0';
    var manufacturerName = 'Bee';

    try {
      // Bee devices don't have standard device info service
      // Use defaults
    } catch (e) {
      Logger.error('Error getting Bee device info: $e');
    }

    return copyWith(
      modelNumber: modelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      type: DeviceType.bee,
    );
  }

  Future _getDeviceInfoFromPlaud(PlaudDeviceConnection conn) async {
    var modelNumber = 'PLAUD';
    var firmwareRevision = '1.0.0';
    var hardwareRevision = '1.0.0';
    var manufacturerName = 'PLAUD';

    try {
      final deviceInfo = await conn.getDeviceInfo();
      modelNumber = deviceInfo['modelNumber'] ?? modelNumber;
      firmwareRevision = deviceInfo['firmwareRevision'] ?? firmwareRevision;
      hardwareRevision = deviceInfo['hardwareRevision'] ?? hardwareRevision;
      manufacturerName = deviceInfo['manufacturerName'] ?? manufacturerName;
    } catch (e) {
      Logger.error('Error getting PLAUD device info: $e');
    }

    return copyWith(
      modelNumber: modelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      type: DeviceType.plaud,
    );
  }

  Future _getDeviceInfoFromFieldy(DeviceConnection conn) async {
    var modelNumber = 'Fieldy';
    var firmwareRevision = '1.0.0';
    var hardwareRevision = 'Fieldy Hardware';
    var manufacturerName = 'Fieldy';

    try {
      if (conn is FieldyDeviceConnection) {
        final deviceInfo = await conn.getDeviceInfo();
        modelNumber = deviceInfo['modelNumber'] ?? modelNumber;
        firmwareRevision = deviceInfo['firmwareRevision'] ?? firmwareRevision;
        hardwareRevision = deviceInfo['hardwareRevision'] ?? hardwareRevision;
        manufacturerName = deviceInfo['manufacturerName'] ?? manufacturerName;
      }
    } catch (e) {
      Logger.error('Error getting Fieldy device info: $e');
    }

    return copyWith(
      modelNumber: modelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      type: DeviceType.fieldy,
    );
  }

  Future _getDeviceInfoFromFriendPendant(DeviceConnection conn) async {
    var modelNumber = 'Friend Pendant';
    var firmwareRevision = '1.0.0';
    var hardwareRevision = '1.0.0';
    var manufacturerName = 'Friend';

    try {
      if (conn is FriendPendantDeviceConnection) {
        final deviceInfo = await conn.getDeviceInfo();
        modelNumber = deviceInfo['modelNumber'] ?? modelNumber;
        firmwareRevision = deviceInfo['firmwareRevision'] ?? firmwareRevision;
        hardwareRevision = deviceInfo['hardwareRevision'] ?? hardwareRevision;
        manufacturerName = deviceInfo['manufacturerName'] ?? manufacturerName;
      }
    } catch (e) {
      Logger.error('Error getting Friend Pendant device info: $e');
    }

    return copyWith(
      modelNumber: modelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      type: DeviceType.friendPendant,
    );
  }

  Future _getDeviceInfoFromLimitless(LimitlessDeviceConnection conn) async {
    var modelNumber = 'Limitless Pendant';
    var firmwareRevision = '1.0.0';
    var hardwareRevision = 'Unknown';
    var manufacturerName = 'Limitless';

    try {
      final deviceInfo = await conn.getDeviceInfo();
      modelNumber = deviceInfo['modelNumber'] ?? modelNumber;
      firmwareRevision = deviceInfo['firmwareRevision'] ?? firmwareRevision;
      hardwareRevision = deviceInfo['hardwareRevision'] ?? hardwareRevision;
      manufacturerName = deviceInfo['manufacturerName'] ?? manufacturerName;
    } catch (e) {
      Logger.error('Error getting Limitless device info: $e');
    }

    return copyWith(
      modelNumber: modelNumber,
      firmwareRevision: firmwareRevision,
      hardwareRevision: hardwareRevision,
      manufacturerName: manufacturerName,
      type: DeviceType.limitless,
    );
  }

  /// Returns firmware warning title for this device type
  /// Empty string means no warning needed
  String getFirmwareWarningTitle() {
    switch (type) {
      case DeviceType.plaud:
      case DeviceType.bee:
      case DeviceType.fieldy:
      case DeviceType.friendPendant:
      case DeviceType.limitless:
        return 'Compatibility Note';
      case DeviceType.omi:
      case DeviceType.openglass:
      case DeviceType.frame:
      case DeviceType.appleWatch:
        return ''; // No warning needed
    }
  }

  /// Returns firmware warning message for this device type
  /// Empty string means no warning needed
  String getFirmwareWarningMessage() {
    switch (type) {
      case DeviceType.plaud:
        return 'Your $name\'s current firmware works great with Omi.\n\n'
            'We recommend keeping your current firmware and not updating through the PLAUD app, as newer versions may affect compatibility.';

      case DeviceType.bee:
        return 'Your $name\'s current firmware works great with Omi.\n\n'
            'We recommend keeping your current firmware and not updating through the Bee app, as newer versions may affect compatibility.\n\n'
            'For the best experience, please keep your current firmware version.';

      case DeviceType.fieldy:
        return 'Your $name\'s current firmware works great with Omi.\n\n'
            'We recommend keeping your current firmware and not updating through the Compass app, as newer versions may affect compatibility.';

      case DeviceType.friendPendant:
        return 'Your $name\'s current firmware works great with Omi.\n\n'
            'We recommend keeping your current firmware and not updating through the Friend app, as newer versions may affect compatibility.';

      case DeviceType.limitless:
        return 'Your $name\'s current firmware works great with Omi.\n\n'
            'We recommend keeping your current firmware and not updating through the Limitless app, as newer versions may affect compatibility.';

      case DeviceType.omi:
      case DeviceType.openglass:
      case DeviceType.frame:
      case DeviceType.appleWatch:
        return ''; // No warning needed
    }
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

  // Check if a scan result is from a supported device
  static bool isSupportedDevice(ScanResult result) {
    return isBeeDevice(result) ||
        isPlaudDevice(result) ||
        isFieldyDevice(result) ||
        isFriendPendantDevice(result) ||
        isLimitlessDevice(result) ||
        isOmiDevice(result) ||
        isFrameDevice(result);
  }

  static bool isBeeDevice(ScanResult result) {
    return result.device.platformName.toLowerCase().contains('bee');
  }

  static bool isBeeDeviceFromDevice(BluetoothDevice device) {
    return device.servicesList.any((s) => s.uuid.toString().toLowerCase() == beeServiceUuid.toLowerCase()) ||
        device.platformName.toLowerCase().contains('bee');
  }

  static bool isPlaudDevice(ScanResult result) {
    final manufacturerData = result.advertisementData.manufacturerData;

    // Check for PLAUD manufacturer ID (93 / 0x5D)
    // This should be consistent across all PLAUD devices
    if (manufacturerData.containsKey(93)) {
      final data = manufacturerData[93]!;

      // Log the pattern to learn new devices
      Logger.debug(
          '[PLAUD] Found manufacturer ID 93 with data: ${data.map((e) => e.toRadixString(16).padLeft(2, '0')).join()}');

      // Known pattern for NotePin: 0456cf00
      if (data.length >= 4 && data[0] == 0x04 && data[1] == 0x56 && data[2] == 0xcf && data[3] == 0x00) {
        return true;
      }

      // Accept any device with manufacturer ID 93 if it has data
      // This catches other PLAUD models we haven't seen yet
      if (data.isNotEmpty) {
        Logger.debug('[PLAUD] Accepting device with manufacturer ID 93');
        return true;
      }
    }

    // Fallback: name check for renamed/unknown variants
    return result.device.platformName.toUpperCase().startsWith('PLAUD');
  }

  static bool isPlaudDeviceFromDevice(BluetoothDevice device) {
    // Primary check: PLAUD service UUID (most reliable after connection)
    if (device.servicesList.any((s) => s.uuid == Guid(plaudServiceUuid))) {
      return true;
    }

    // Fallback: name check for compatibility
    return device.platformName.toUpperCase().startsWith('PLAUD');
  }

  static bool isFieldyDevice(ScanResult result) {
    final name = result.device.platformName.toLowerCase();
    return name == 'compass' || name == 'fieldy';
  }

  static bool isFieldyDeviceFromDevice(BluetoothDevice device) {
    final name = device.platformName.toLowerCase();
    return device.servicesList.any((s) => s.uuid.toString().toLowerCase() == fieldyServiceUuid.toLowerCase()) ||
        name == 'compass' ||
        name == 'fieldy';
  }

  static bool isFriendPendantDevice(ScanResult result) {
    return result.device.platformName.toLowerCase().startsWith('friend_') ||
        result.advertisementData.serviceUuids
            .any((uuid) => uuid.toString().toLowerCase() == friendPendantServiceUuid.toLowerCase());
  }

  static bool isFriendPendantDeviceFromDevice(BluetoothDevice device) {
    return device.platformName.toLowerCase().startsWith('friend_') ||
        device.servicesList.any((s) => s.uuid.toString().toLowerCase() == friendPendantServiceUuid.toLowerCase());
  }

  static bool isLimitlessDevice(ScanResult result) {
    final name = result.device.platformName.toLowerCase();
    return name.contains('limitless') ||
        name.contains('pendant') ||
        result.advertisementData.serviceUuids
            .any((uuid) => uuid.toString().toLowerCase() == limitlessServiceUuid.toLowerCase());
  }

  static bool isLimitlessDeviceFromDevice(BluetoothDevice device) {
    final name = device.platformName.toLowerCase();
    return name.contains('limitless') ||
        name.contains('pendant') ||
        device.servicesList.any((s) => s.uuid.toString().toLowerCase() == limitlessServiceUuid.toLowerCase());
  }

  static bool isOmiDevice(ScanResult result) {
    return result.advertisementData.serviceUuids.contains(Guid(omiServiceUuid));
  }

  static bool isOmiDeviceFromDevice(BluetoothDevice device) {
    return device.servicesList.any((s) => s.uuid == Guid(omiServiceUuid));
  }

  static bool isFrameDevice(ScanResult result) {
    return result.advertisementData.serviceUuids.contains(Guid(frameServiceUuid));
  }

  static bool isFrameDeviceFromDevice(BluetoothDevice device) {
    return device.servicesList.any((s) => s.uuid == Guid(frameServiceUuid));
  }

  // from ScanResult
  static fromScanResult(ScanResult result) {
    DeviceType? deviceType;

    if (isBeeDevice(result)) {
      deviceType = DeviceType.bee;
    } else if (isPlaudDevice(result)) {
      deviceType = DeviceType.plaud;
    } else if (isFieldyDevice(result)) {
      deviceType = DeviceType.fieldy;
    } else if (isFriendPendantDevice(result)) {
      deviceType = DeviceType.friendPendant;
    } else if (isLimitlessDevice(result)) {
      deviceType = DeviceType.limitless;
    } else if (isOmiDevice(result)) {
      deviceType = DeviceType.omi;
    } else if (isFrameDevice(result)) {
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
      locator: DeviceLocator.bluetooth(deviceId: result.device.remoteId.str),
    );
  }

  // from json
  static fromJson(Map<String, dynamic> json) {
    return BtDevice(
      name: json['name'],
      id: json['id'],
      type: DeviceType.values[json['type']],
      rssi: json['rssi'],
      locator: json['locator'] != null ? DeviceLocator.fromJson(json['locator']) : null,
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
      'locator': locator?.toJson(),
      'modelNumber': modelNumber,
      'firmwareRevision': firmwareRevision,
      'hardwareRevision': hardwareRevision,
      'manufacturerName': manufacturerName,
    };
  }
}
