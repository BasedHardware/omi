import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/devices/device.dart';
import 'package:friend_private/devices/deviceType.dart';
import 'package:friend_private/devices/friend/friendDevice.dart';
import 'package:friend_private/devices/friend/openGlassDevice.dart';

class OpenGlassDeviceType extends BtleDeviceType {
  OpenGlassDeviceType() : super();
  @override String get manufacturerName => "Based Hardware";
  @override String get deviceNameForMatching => "OpenGlass";
  @override List<Guid> get serviceGuids => [friendServiceUuid.guid];
  @override Type get deviceType => OpenGlassDevice;

  @override
  Device createDeviceFromScan(String name, String id, int? rssi) {
    OpenGlassDevice device = OpenGlassDevice(id);
    device.name = name;
    if (rssi != null) {
      device.rssi = rssi;
    }
    return device;
  } 
}