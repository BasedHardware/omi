enum TransportKind {
  bluetooth,
  watchConnectivity,
  wifi,
}

class DeviceLocator {
  final TransportKind kind;

  // For bluetooth
  final String? bluetoothId;

  // For wifi
  final String? host;
  final int? port;

  // Generic bag for future extensibility
  final Map<String, Object?> extras;

  const DeviceLocator._({
    required this.kind,
    this.bluetoothId,
    this.host,
    this.port,
    this.extras = const {},
  });

  factory DeviceLocator.bluetooth({required String deviceId, Map<String, Object?> extras = const {}}) {
    return DeviceLocator._(kind: TransportKind.bluetooth, bluetoothId: deviceId, extras: extras);
  }

  factory DeviceLocator.watchConnectivity({Map<String, Object?> extras = const {}}) {
    return DeviceLocator._(kind: TransportKind.watchConnectivity, extras: extras);
  }

  factory DeviceLocator.wifi({required String host, int? port, Map<String, Object?> extras = const {}}) {
    return DeviceLocator._(kind: TransportKind.wifi, host: host, port: port, extras: extras);
  }

  // Serialization
  Map<String, dynamic> toJson() {
    return {
      'kind': kind.index,
      'bluetoothId': bluetoothId,
      'host': host,
      'port': port,
      'extras': extras,
    };
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
        return DeviceLocator.watchConnectivity(
          extras: (json['extras'] as Map<String, dynamic>?) ?? {},
        );
      case TransportKind.wifi:
        return DeviceLocator.wifi(
          host: json['host'] as String,
          port: json['port'] as int?,
          extras: (json['extras'] as Map<String, dynamic>?) ?? {},
        );
    }
  }
}
