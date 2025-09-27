import 'dart:async';

enum DeviceConnectionState {
  connected,
  disconnected,
}

abstract class DeviceCommunicator {
  String get deviceId;
  DeviceConnectionState get connectionState;
  Stream<DeviceConnectionState> get connectionStateStream;

  // Core connection management
  Future<void> connect();
  Future<void> disconnect();
  Future<bool> isConnected();

  // Generic command/response pattern
  Future<Map<String, dynamic>?> sendCommand(String command, [Map<String, dynamic>? params]);
  Stream<Map<String, dynamic>> get messageStream;

  // Resource cleanup
  Future<void> dispose();
}
