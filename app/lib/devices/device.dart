import 'dart:async';
import 'dart:typed_data';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/devices/deviceType.dart';
import 'package:friend_private/devices/friend/friendDeviceType.dart';

abstract class Device {
  DeviceType get deviceType;
  String get modelNumber;
  String get firmwareRevision;
  String get hardwareRevision;
  String get manufacturerName;
  String get name => _name ?? deviceType.deviceNameForMatching;
  set name(String value) => _name = value;
  String? _name;
  String get id;
  bool get isConnected;

  Future<void> afterConnect();

  Device();
  Future<void> init();

  Future<Device> connectDevice({bool autoConnect = true});

  Future disconnectDevice();

  String get shortId {
    return getShortId(id);
  }

  static String getShortId(String id) {
    try {
      return id.replaceAll(':', '').split('-').last.substring(0, 6);
    } catch (e) {
      return id.length > 6 ? id.substring(0, 6) : id.padLeft(6, '0');
    }
  }

  

  factory Device.fromJson(Map<String, dynamic> json) {
    late DeviceType type;
    if (json['type'] != null) {
      type = AnyDeviceType().deviceTypes.firstWhere(
          (e) => e.deviceNameForMatching == json['type'],
          orElse: () => FriendDeviceType());
    } else {
      type = FriendDeviceType();
    }

    return type.createDeviceFromScan(
        json['name'] as String, json['id'] as String, json['rssi'] as int?);
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'fwver': [firmwareRevision],
        'type': deviceType.deviceNameForMatching,
      };

  Future<int> retrieveBatteryLevel();

  Future<StreamSubscription<List<int>>?> getBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  });

  Future<StreamSubscription?> getAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  });

  Future<BleAudioCodec> getAudioCodec();

  Future cameraStartPhotoController();

  Future cameraStopPhotoController();

  Future<bool> canPhotoStream();

  Future<StreamSubscription?> getImageListener({
    required void Function(Uint8List) onImageReceived,
  });
}
