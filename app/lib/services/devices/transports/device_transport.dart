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

  /// Whether [characteristicUuid] was discovered under [serviceUuid].
  ///
  /// Default false for non-BLE transports. Native BLE overrides this from the
  /// discovered GATT table — callers must not infer presence from a non-null
  /// [getCharacteristicStream] subscription (that API creates a controller even
  /// when the characteristic is missing).
  bool hasCharacteristic(String serviceUuid, String characteristicUuid) => false;

  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid);
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data);

  Stream<DeviceTransportState> get connectionStateStream;

  Future<void> dispose();
}

enum DeviceTransportState { disconnected, connecting, connected, disconnecting }
