import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/communication/device_communicator.dart';
import 'package:omi/services/devices/communication/omi_communicator.dart';
import 'package:omi/services/devices/communication/frame_communicator.dart';
import 'package:omi/services/devices/communication/apple_watch_communicator.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

class CommunicatorFactory {
  static DeviceCommunicator? create(BtDevice device) {
    final locator = device.locator;
    if (locator == null) {
      return null;
    }

    // Create device-specific communicator based on device type
    switch (device.type) {
      case DeviceType.omi:
      case DeviceType.openglass:
        if (locator.kind == TransportKind.bluetooth) {
          final deviceId = locator.bluetoothId;
          if (deviceId == null) return null;

          try {
            final bleDevice = BluetoothDevice.fromId(deviceId);
            return OmiCommunicator(bleDevice);
          } catch (e) {
            return null;
          }
        }
        return null;

      case DeviceType.frame:
        if (locator.kind == TransportKind.bluetooth) {
          final deviceId = locator.bluetoothId;
          if (deviceId == null) return null;
          return FrameCommunicator(deviceId);
        }
        return null;

      case DeviceType.appleWatch:
        if (locator.kind == TransportKind.watchConnectivity) {
          return AppleWatchCommunicator();
        }
        return null;
    }
  }
}
