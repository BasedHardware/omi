import 'dart:io';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices/discovery/device_discoverer.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/utils/logger.dart';

/// Discovers Ray-Ban Meta glasses.
///
/// Full mode (Meta Wearables Device Access Toolkit linked and registered):
/// lists the glasses the toolkit reports. Audio-only fallback (no toolkit in
/// this build): lists a single entry when a Bluetooth HFP microphone whose
/// name identifies Meta glasses is available. Self-gating — yields nothing on
/// unsupported platforms or builds, which is the repo's idiomatic feature gate.
class RayBanMetaDiscoverer extends DeviceDiscoverer {
  /// Marks a discovered device as the labeled audio-only fallback.
  static const String audioOnlyExtraKey = 'audioOnly';

  @override
  String get name => 'Ray-Ban Meta';

  @override
  bool get isSupported => Platform.isIOS;

  @override
  Future<DeviceDiscoveryResult> discover({int timeout = 5}) async {
    try {
      final host = RayBanMetaHostAPI();
      final mode = await host.getAvailabilityMode();

      if (mode == 'full') {
        final registration = await host.getRegistrationState();
        if (registration != 'registered') {
          return const DeviceDiscoveryResult(devices: []);
        }
        final glasses = await host.getAvailableGlasses();
        final devices = glasses
            .map(
              (g) => BtDevice(
                name: g.name.isNotEmpty ? g.name : 'Ray-Ban Meta',
                id: g.id,
                type: DeviceType.raybanMeta,
                rssi: 0,
                locator: DeviceLocator.metaDat(),
              ),
            )
            .toList();
        return DeviceDiscoveryResult(devices: devices);
      }

      if (mode == 'audio_only') {
        final inputs = await host.getBluetoothHfpInputNames();
        final glassesInput = inputs.where(looksLikeMetaGlasses).toList();
        if (glassesInput.isNotEmpty) {
          final device = BtDevice(
            name: glassesInput.first,
            id: 'rayban-meta-audio',
            type: DeviceType.raybanMeta,
            rssi: 0,
            locator: DeviceLocator.metaDat(extras: const {audioOnlyExtraKey: true}),
          );
          return DeviceDiscoveryResult(devices: [device]);
        }
      }
    } catch (e) {
      Logger.debug('Ray-Ban Meta discovery error: $e');
    }
    return const DeviceDiscoveryResult(devices: []);
  }

  /// Explicit product-name match for the audio-only fallback. Without the
  /// toolkit the HFP port name is the only identity signal, so match Meta's
  /// product names precisely rather than anything containing 'glass'.
  static bool looksLikeMetaGlasses(String portName) {
    final lower = portName.toLowerCase();
    return lower.contains('ray-ban') ||
        lower.contains('rayban') ||
        lower.contains('oakley meta') ||
        lower.contains('meta glasses');
  }

  @override
  Future<void> stop() async {
    // Discovery is a stateless snapshot of the native toolkit state.
  }
}
