/// Compatibility state reported by Meta's SDK for a paired device.
///
/// Mirrors `MWDATCore.Compatibility` on iOS and
/// `com.meta.wearable.dat.core.types.DeviceCompatibility` on Android.
enum DeviceCompatibility {
  /// Device and SDK versions are compatible; streaming should work.
  compatible,

  /// The glasses firmware needs to be updated before the SDK can talk
  /// to the device. Surface this to the user with instructions to open
  /// Meta AI / the companion app.
  deviceUpdateRequired,

  /// The host app embeds an older `MWDAT*` SDK than the firmware
  /// expects. Surface this as "please update the app".
  sdkUpdateRequired,

  /// SDK has not yet reported a compatibility verdict for this device,
  /// or the SDK doesn't know how to classify it.
  unknown;

  /// Maps a wire string (`compatible`, `deviceUpdateRequired`,
  /// `sdkUpdateRequired`, `unknown`, `undefined`) to a [DeviceCompatibility].
  static DeviceCompatibility fromRaw(String? raw) {
    switch (raw) {
      case 'compatible':
        return DeviceCompatibility.compatible;
      case 'deviceUpdateRequired':
        return DeviceCompatibility.deviceUpdateRequired;
      case 'sdkUpdateRequired':
        return DeviceCompatibility.sdkUpdateRequired;
      case _:
        return DeviceCompatibility.unknown;
    }
  }
}

/// One `compatibility` event from the native side.
///
/// Emitted by `MetaWearablesDat.compatibilityStream()` whenever the SDK
/// recomputes its verdict for a paired device.
class DeviceCompatibilityEvent {
  /// Creates a [DeviceCompatibilityEvent].
  const DeviceCompatibilityEvent({
    required this.deviceUuid,
    required this.compatibility,
  });

  /// Parses a platform-channel map into a [DeviceCompatibilityEvent].
  factory DeviceCompatibilityEvent.fromMap(Map<Object?, Object?> map) {
    return DeviceCompatibilityEvent(
      deviceUuid: map['deviceUuid'] as String? ?? '',
      compatibility: DeviceCompatibility.fromRaw(
        map['compatibility'] as String?,
      ),
    );
  }

  /// The device this event refers to. Matches `DeviceInfo.uuid`.
  final String deviceUuid;

  /// The current compatibility state.
  final DeviceCompatibility compatibility;

  @override
  String toString() => 'DeviceCompatibilityEvent(deviceUuid: $deviceUuid, '
      'compatibility: $compatibility)';
}
