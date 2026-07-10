import 'package:flutter/services.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/devices/connectors/apple_watch_connection.dart';
import 'package:omi/services/devices/connectors/bee_connection.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/connectors/fieldy_connection.dart';
import 'package:omi/services/devices/connectors/friend_pendant_connection.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/connectors/omiglass_connection.dart';
import 'package:omi/services/devices/connectors/plaud_connection.dart';
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

enum DeviceType { omi, openglass, appleWatch, plaud, bee, fieldy, friendPendant, limitless, raybanMeta }

// Legacy index order (before Frame was removed) — keep for backward-compatible deserialization.
const List<String> _legacyDeviceTypeNames = [
  'omi',
  'openglass',
  'frame',
  'appleWatch',
  'plaud',
  'bee',
  'fieldy',
  'friendPendant',
  'limitless',
  'raybanMeta',
];

DeviceType _deviceTypeFromJson(dynamic raw) {
  String? name;
  if (raw is int) {
    if (raw >= 0 && raw < _legacyDeviceTypeNames.length) name = _legacyDeviceTypeNames[raw];
  } else if (raw is String) {
    name = raw;
  }
  return DeviceType.values.firstWhere((e) => e.name == name, orElse: () => DeviceType.omi);
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
  String? _serialNumber;

  BtDevice({
    required this.name,
    required this.id,
    required this.type,
    required this.rssi,
    this.locator,
    String? modelNumber,
    String? firmwareRevision,
    String? hardwareRevision,
    String? manufacturerName,
    String? serialNumber,
  }) {
    _modelNumber = modelNumber;
    _firmwareRevision = firmwareRevision;
    _hardwareRevision = hardwareRevision;
    _manufacturerName = manufacturerName;
    _serialNumber = serialNumber;
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
        _manufacturerName = '',
        _serialNumber = '';

  // getters
  String get modelNumber => _modelNumber ?? 'Unknown';
  String get firmwareRevision => _firmwareRevision ?? 'Unknown';
  String get hardwareRevision => _hardwareRevision ?? 'Unknown';
  String get manufacturerName => _manufacturerName ?? 'Unknown';
  String? get serialNumber => _serialNumber;

  // set details
  set modelNumber(String modelNumber) => _modelNumber = modelNumber;
  set firmwareRevision(String firmwareRevision) => _firmwareRevision = firmwareRevision;
  set hardwareRevision(String hardwareRevision) => _hardwareRevision = hardwareRevision;
  set manufacturerName(String manufacturerName) => _manufacturerName = manufacturerName;
  set serialNumber(String? serialNumber) => _serialNumber = serialNumber;

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

  BtDevice copyWith({
    String? name,
    String? id,
    DeviceType? type,
    int? rssi,
    DeviceLocator? locator,
    String? modelNumber,
    String? firmwareRevision,
    String? hardwareRevision,
    String? manufacturerName,
    String? serialNumber,
  }) {
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
      serialNumber: serialNumber ?? _serialNumber,
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
    } else if (type == DeviceType.appleWatch) {
      return await _getDeviceInfoFromAppleWatch(conn as AppleWatchDeviceConnection);
    } else if (type == DeviceType.raybanMeta) {
      return _getDeviceInfoFromRayBanMeta();
    } else {
      return await _getDeviceInfoFromOmi(conn);
    }
  }

  // The Meta Wearables toolkit doesn't expose firmware/hardware revisions, so
  // static identity fields are all we can report.
  BtDevice _getDeviceInfoFromRayBanMeta() {
    return copyWith(
      modelNumber: 'Ray-Ban Meta',
      firmwareRevision: 'Unknown',
      hardwareRevision: 'Unknown',
      manufacturerName: 'Meta',
      type: DeviceType.raybanMeta,
    );
  }

  Future _getDeviceInfoFromOmi(DeviceConnection conn) async {
    var modelNumber = 'Omi';
    var firmwareRevision = '1.0.2';
    var hardwareRevision = 'Seeed Xiao BLE Sense';
    var manufacturerName = 'Based Hardware';
    String? serialNumber;
    var t = DeviceType.omi;

    try {
      Map<String, dynamic>? deviceInfo;

      if (conn is OmiGlassConnection) {
        deviceInfo = await conn.getDeviceInfo();
        t = DeviceType.openglass;
      } else if (conn is OmiDeviceConnection) {
        deviceInfo = await conn.getDeviceInfo();

        // Check if device has image streaming capability (OpenGlass detection)
        if (type == DeviceType.openglass) {
          t = DeviceType.openglass;
        } else if (deviceInfo['hasImageStream'] == 'true') {
          t = DeviceType.openglass;
        }
      }

      if (deviceInfo != null) {
        modelNumber = deviceInfo['modelNumber'] ?? modelNumber;
        firmwareRevision = deviceInfo['firmwareRevision'] ?? firmwareRevision;
        hardwareRevision = deviceInfo['hardwareRevision'] ?? hardwareRevision;
        manufacturerName = deviceInfo['manufacturerName'] ?? manufacturerName;
        serialNumber = deviceInfo['serialNumber'];
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
      serialNumber: serialNumber,
      type: t,
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
      if (conn is BeeDeviceConnection) {
        final deviceInfo = await conn.getDeviceInfo();
        modelNumber = deviceInfo['modelNumber'] ?? modelNumber;
        firmwareRevision = deviceInfo['firmwareRevision'] ?? firmwareRevision;
        hardwareRevision = deviceInfo['hardwareRevision'] ?? hardwareRevision;
        manufacturerName = deviceInfo['manufacturerName'] ?? manufacturerName;
      }
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

  bool get isBeeFirmwareUnsupported {
    if (type != DeviceType.bee) return false;
    final fw = firmwareRevision;
    if (fw.isEmpty) return false;
    final parts = fw.split('.');
    if (parts.length < 3) return false;
    try {
      final major = int.parse(parts[0]);
      final minor = int.parse(parts[1]);
      final patch = int.parse(parts[2]);
      // Unsupported if >= 0.6.1
      if (major > 0) return true;
      if (minor > 6) return true;
      if (minor == 6 && patch >= 1) return true;
      return false;
    } catch (_) {
      return false;
    }
  }

  /// Returns firmware warning title for this device type
  /// Empty string means no warning needed
  String getFirmwareWarningTitle() {
    switch (type) {
      case DeviceType.plaud:
      case DeviceType.fieldy:
      case DeviceType.friendPendant:
      case DeviceType.limitless:
        return 'Compatibility Note';
      case DeviceType.bee:
        return isBeeFirmwareUnsupported ? 'Firmware Not Supported' : 'Compatibility Note';
      case DeviceType.omi:
      case DeviceType.openglass:
      case DeviceType.appleWatch:
      case DeviceType.raybanMeta:
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
        if (isBeeFirmwareUnsupported) {
          return 'Your $name is running firmware v$firmwareRevision which uses encrypted audio that Omi cannot process.\n\n'
              'Please downgrade your Bee firmware to a version below 0.6.1 for compatibility with Omi.\n\n'
              'Audio capture will not work with the current firmware.';
        }
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
      case DeviceType.appleWatch:
      case DeviceType.raybanMeta:
        return ''; // No warning needed
    }
  }

  // from json
  static fromJson(Map<String, dynamic> json) {
    // Persisted values may be missing or mistyped (e.g. rssi stored as a
    // String by an older app version) — never throw during deserialization.
    final rawRssi = json['rssi'];
    final rssi = rawRssi is int ? rawRssi : (rawRssi is num ? rawRssi.toInt() : int.tryParse('$rawRssi') ?? 0);
    return BtDevice(
      name: json['name'] is String ? json['name'] : '',
      id: json['id'] is String ? json['id'] : '',
      type: _deviceTypeFromJson(json['type']),
      rssi: rssi,
      locator: json['locator'] is Map<String, dynamic> ? DeviceLocator.fromJson(json['locator']) : null,
      modelNumber: json['modelNumber'] is String ? json['modelNumber'] : null,
      firmwareRevision: json['firmwareRevision'] is String ? json['firmwareRevision'] : null,
      hardwareRevision: json['hardwareRevision'] is String ? json['hardwareRevision'] : null,
      manufacturerName: json['manufacturerName'] is String ? json['manufacturerName'] : null,
      serialNumber: json['serialNumber'] is String ? json['serialNumber'] : null,
    );
  }

  // to json
  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'id': id,
      // Persist by stable name (not index): _deviceTypeFromJson reads both the
      // new name strings and legacy integer indexes, so removing an enum value
      // can never mis-map existing or newly-saved devices.
      'type': type.name,
      'rssi': rssi,
      'locator': locator?.toJson(),
      'modelNumber': modelNumber,
      'firmwareRevision': firmwareRevision,
      'hardwareRevision': hardwareRevision,
      'manufacturerName': manufacturerName,
      'serialNumber': _serialNumber,
    };
  }
}
