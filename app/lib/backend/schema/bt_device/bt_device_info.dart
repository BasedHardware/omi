import 'package:friend_private/backend/schema/bt_device/bt_device.dart';

class BtDeviceInfo {
  String modelNumber;
  String firmwareRevision;
  String hardwareRevision;
  String manufacturerName;
  DeviceType type;

  BtDeviceInfo(this.modelNumber, this.firmwareRevision, this.hardwareRevision, this.manufacturerName, this.type);
}
