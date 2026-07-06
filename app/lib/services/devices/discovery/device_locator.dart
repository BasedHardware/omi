enum TransportKind { bluetooth, watchConnectivity, metaDat }

class DeviceLocator {
  final TransportKind kind;

  // For bluetooth
  final String? bluetoothId;

  // Generic bag for future extensibility
  final Map<String, Object?> extras;

  const DeviceLocator._({required this.kind, this.bluetoothId, this.extras = const {}});

  factory DeviceLocator.bluetooth({required String deviceId, Map<String, Object?> extras = const {}}) {
    return DeviceLocator._(kind: TransportKind.bluetooth, bluetoothId: deviceId, extras: extras);
  }

  factory DeviceLocator.watchConnectivity({Map<String, Object?> extras = const {}}) {
    return DeviceLocator._(kind: TransportKind.watchConnectivity, extras: extras);
  }

  // Ray-Ban Meta glasses reached through the Meta Wearables Device Access
  // Toolkit; the DAT device identifier is carried on BtDevice.id.
  factory DeviceLocator.metaDat({Map<String, Object?> extras = const {}}) {
    return DeviceLocator._(kind: TransportKind.metaDat, extras: extras);
  }

  // Serialization
  Map<String, dynamic> toJson() {
    return {'kind': kind.index, 'bluetoothId': bluetoothId, 'extras': extras};
  }

  factory DeviceLocator.fromJson(Map<String, dynamic> json) {
    final kind = TransportKind.values[json['kind'] as int];
    switch (kind) {
      case TransportKind.bluetooth:
        return DeviceLocator.bluetooth(
          deviceId: json['bluetoothId'] as String,
          extras: (json['extras'] as Map<String, dynamic>?) ?? {},
        );
      case TransportKind.watchConnectivity:
        return DeviceLocator.watchConnectivity(extras: (json['extras'] as Map<String, dynamic>?) ?? {});
      case TransportKind.metaDat:
        return DeviceLocator.metaDat(extras: (json['extras'] as Map<String, dynamic>?) ?? {});
    }
  }
}
