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

/// Optional capability for transports that own a reconnecting connection.
///
/// A generation is published only after the transport has installed the
/// services for a newly ready connection. Consumers can use it to repeat
/// per-connection setup without treating a native auto-reconnect as a new
/// [connect] call.
abstract interface class DeviceReadyGenerationSource {
  int get readyGeneration;
  Stream<int> get readyGenerationStream;
}

/// A transport whose background ownership must be released before another
/// client, such as a DFU plugin, can exclusively manage the device.
abstract interface class ExclusiveOperationTransport {
  Future<void> releaseForExclusiveOperation();
}

/// Releases background ownership, then retires the Dart transport.
///
/// Disposal is attempted even when exclusive release fails, while the first
/// failure remains authoritative for transactional rollback.
Future<void> releaseTransportForExclusiveOperation(DeviceTransport transport) async {
  Object? firstError;
  StackTrace? firstStackTrace;

  final exclusiveTransport = transport is ExclusiveOperationTransport ? transport as ExclusiveOperationTransport : null;
  if (exclusiveTransport != null) {
    try {
      await exclusiveTransport.releaseForExclusiveOperation();
    } catch (error, stackTrace) {
      firstError = error;
      firstStackTrace = stackTrace;
    }
  }

  try {
    await transport.dispose();
  } catch (error, stackTrace) {
    firstError ??= error;
    firstStackTrace ??= stackTrace;
  }

  if (firstError != null) {
    Error.throwWithStackTrace(firstError, firstStackTrace!);
  }
}

enum DeviceTransportState { disconnected, connecting, connected, disconnecting }
