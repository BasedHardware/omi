import 'package:omi/backend/schema/bt_device/bt_device.dart';

class DeviceDiscoveryResult {
  final List<BtDevice> devices;
  final Map<String, dynamic>? metadata;

  /// True when discovery was intentionally not started because the BLE radio
  /// or its required permission was unavailable. This is distinct from a scan
  /// that completed without finding a device.
  final bool isBlocked;

  const DeviceDiscoveryResult({required this.devices, this.metadata, this.isBlocked = false});
}

abstract class DeviceDiscoverer {
  String get name;
  bool get isSupported;

  Future<DeviceDiscoveryResult> discover({int timeout = 5});
  Future<void> stop();
}
