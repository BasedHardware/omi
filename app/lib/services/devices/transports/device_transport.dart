import 'dart:async';

/// Abstract transport layer for device communication
/// Provides a unified interface for different communication protocols (BLE, WatchConnectivity, etc.)
abstract class DeviceTransport {
  String get deviceId;

  Future<void> connect({bool autoConnect = false});
  Future<void> disconnect();
  Future<bool> isConnected();
  Future<bool> ping();

  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid);

  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid);
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data);

  Stream<DeviceTransportState> get connectionStateStream;

  Future<void> dispose();
}

enum DeviceTransportState {
  disconnected,
  connecting,
  connected,
  disconnecting,
}
