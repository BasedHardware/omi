import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/devices/device.dart';
import 'package:friend_private/devices/deviceType.dart';
import 'package:friend_private/devices/frame/frameDevice.dart';

class FrameDeviceType extends BtleDeviceType {
  FrameDeviceType() : super();
  @override String get manufacturerName => "Brilliant Labs";
  @override String get deviceNameForMatching => "Frame";
  @override List<Guid> get serviceGuids => [Guid("7A230001-5475-A6A4-654C-8431F6AD49C4")];
  @override Type get deviceType => FrameDevice;

  @override
  Device createDeviceFromScan(String name, String id, int? rssi) {
    print("Creating FrameDevice from scan with id $id, name $name, rssi $rssi");
    FrameDevice device = FrameDevice(id);
    device.name = name;
    if (rssi != null) {
      device.rssi = rssi;
    }
    return device;
  } 
}