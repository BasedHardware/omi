import 'package:omi/backend/schema/bt_device/bt_device.dart';

class DeviceDiscoveryResult {
  final List<BtDevice> devices;
  final Map<String, dynamic>? metadata;

  const DeviceDiscoveryResult({
    required this.devices,
    this.metadata,
  });
}

abstract class DeviceDiscoverer {
  String get name;
  bool get isSupported;

  Future<DeviceDiscoveryResult> discover({int timeout = 5});
  Future<void> stop();
}
