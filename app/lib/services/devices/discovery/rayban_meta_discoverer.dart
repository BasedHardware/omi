import 'dart:io';

import 'package:collection/collection.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices/discovery/device_discoverer.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/utils/logger.dart';

/// Discovers Ray-Ban Meta glasses.
///
/// Full mode (Meta Wearables Device Access Toolkit linked and registered):
/// lists the glasses the toolkit reports. Audio-only fallback (no toolkit in
/// this build): lists the user's persisted Bluetooth HFP input by stable UID,
/// or a precisely name-matched input as a setup convenience. Self-gating —
/// yields nothing on unsupported platforms or builds, which is the repo's
/// idiomatic feature gate.
class RayBanMetaDiscoverer extends DeviceDiscoverer {
  /// Marks a discovered device as the labeled audio-only fallback.
  static const String audioOnlyExtraKey = 'audioOnly';

  /// Placeholder entry shown before Meta AI authorization so the user can
  /// start registration from the device list; never connectable directly.
  static const String setupPlaceholderId = 'rayban-meta-setup';

  /// Synthetic id persisted by the audio-only fallback before selections were
  /// keyed by the stable HFP UID. It never matches a real input, so a stored
  /// selection carrying it is treated as no selection at all rather than as a
  /// UID that failed to match.
  static const String legacyAudioOnlyId = 'rayban-meta-audio';

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
          final setupEntry = BtDevice(
            name: 'Ray-Ban Meta',
            id: setupPlaceholderId,
            type: DeviceType.raybanMeta,
            rssi: 0,
            locator: DeviceLocator.metaDat(),
          );
          return DeviceDiscoveryResult(devices: [setupEntry]);
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
        final inputs = await host.getBluetoothHfpInputs();
        final storedDevice = SharedPreferencesUtil().btDevice;
        final hasStoredAudioSelection =
            storedDevice.type == DeviceType.raybanMeta &&
            storedDevice.locator?.extras[audioOnlyExtraKey] == true &&
            storedDevice.id.isNotEmpty &&
            storedDevice.id != legacyAudioOnlyId;

        if (hasStoredAudioSelection) {
          final selected = inputs.where((input) => input.uid == storedDevice.id).firstOrNull;
          if (selected != null) {
            return DeviceDiscoveryResult(devices: [audioOnlyDeviceForInput(selected)]);
          }
          return const DeviceDiscoveryResult(devices: []);
        }

        final convenienceMatch = inputs.where((input) => looksLikeMetaGlasses(input.name)).firstOrNull;
        if (convenienceMatch != null) {
          return DeviceDiscoveryResult(devices: [audioOnlyDeviceForInput(convenienceMatch)]);
        }
      }
    } catch (e) {
      Logger.debug('Ray-Ban Meta discovery error: $e');
    }
    return const DeviceDiscoveryResult(devices: []);
  }

  static BtDevice audioOnlyDeviceForInput(BluetoothHfpInput input) {
    return BtDevice(
      name: input.name,
      id: input.uid,
      type: DeviceType.raybanMeta,
      rssi: 0,
      locator: DeviceLocator.metaDat(extras: const {audioOnlyExtraKey: true}),
    );
  }

  /// Explicit product-name match for the audio-only fallback. Without the
  /// toolkit the HFP port name is the only identity signal, so match Meta's
  /// product names precisely rather than anything containing 'glass'.
  static bool looksLikeMetaGlasses(String portName) {
    final lower = portName.toLowerCase();
    return lower.contains('ray-ban') ||
        lower.contains('rayban') ||
        lower.contains('oakley meta') ||
        lower.contains('meta glasses') ||
        RegExp(r'^el ai\s').hasMatch(lower);
  }

  @override
  Future<void> stop() async {
    // Discovery is a stateless snapshot of the native toolkit state.
  }
}
