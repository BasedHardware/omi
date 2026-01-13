import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/flutter_communicator.g.dart';
import 'package:omi/services/devices/discovery/device_discoverer.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/utils/logger.dart';

class AppleWatchDiscoverer extends DeviceDiscoverer {
  @override
  String get name => 'Apple Watch';

  @override
  bool get isSupported => true; // runtime check inside discover

  @override
  Future<DeviceDiscoveryResult> discover({int timeout = 5}) async {
    try {
      final host = WatchRecorderHostAPI();
      final supported = await host.isWatchSessionSupported();
      final paired = await host.isWatchPaired();
      final reachable = await host.isWatchReachable();

      if (supported && paired) {
        final device = BtDevice(
          name: 'Apple Watch',
          id: 'apple-watch',
          type: DeviceType.appleWatch,
          rssi: reachable ? 0 : -100,
          locator: DeviceLocator.watchConnectivity(),
        );
        return DeviceDiscoveryResult(devices: [device]);
      }
    } catch (e) {
      Logger.debug('Apple Watch discovery error: $e');
    }
    return const DeviceDiscoveryResult(devices: []);
  }

  @override
  Future<void> stop() async {
    // Apple Watch discovery is stateless, no cleanup needed
  }
}
