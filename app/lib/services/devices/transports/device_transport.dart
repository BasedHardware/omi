import 'dart:async';

/// Abstract transport layer for device communication
/// Provides a unified interface for different communication protocols (BLE, WatchConnectivity, etc.)
abstract class DeviceTransport {
  String get deviceId;

  Future<void> connect();
  Future<void> disconnect();
  Future<bool> isConnected();
  Future<bool> ping();

  /// Request bonding for devices that require encrypted links.
  /// Returns true if bonded, false if not needed or failed.
  /// Default: no-op (most devices don't need explicit bonding).
  Future<bool> requestBond() async => true;

  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid);

  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid);
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data);

  Stream<DeviceTransportState> get connectionStateStream;

  Future<void> dispose();
}

enum DeviceTransportState { disconnected, connecting, connected, disconnecting }

/// Observable subscription outcomes for transports that confirm notifications.
abstract interface class CaptureSubscriptionErrors {
  Stream<Object> get audioSubscriptionErrors;
}

/// Pendant audio that reached a transport while no capture listener held the
/// stream. The GATT notification subscription outlives Dart listeners, and a
/// legacy pendant does not write its own storage while subscribed, so these
/// packets exist nowhere else. Capture installs [sink] and persists them.
class OrphanAudioRoute {
  static void Function(String deviceId, List<int> packet)? sink;

  static void deliver(String deviceId, List<int> packet) => sink?.call(deviceId, packet);
}
