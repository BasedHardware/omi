import 'dart:typed_data';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/utils/logger.dart';

/// Callback signature for characteristic value updates.
typedef CharacteristicValueCallback = void Function(String serviceUuid, String characteristicUuid, Uint8List value);

/// Callback signature for batched audio data.
typedef AudioBatchCallback = void Function(
    String serviceUuid, String characteristicUuid, Uint8List batchedData, int notificationCount);

/// Callback signature for connection state changes.
typedef ConnectionStateCallback = void Function(bool connected, String? error);

/// Callback signature for service discovery.
typedef ServicesDiscoveredCallback = void Function(List<BleService> services);

/// Singleton bridge that implements BleFlutterApi (Pigeon) and dispatches
/// native BLE events to registered listeners (NativeBleTransport instances).
class BleBridge implements BleFlutterApi {
  static final BleBridge instance = BleBridge._();

  BleBridge._();

  // Per-peripheral callbacks, keyed by peripheral UUID (uppercased).
  final Map<String, CharacteristicValueCallback> _characteristicCallbacks = {};
  final Map<String, AudioBatchCallback> _audioBatchCallbacks = {};
  final Map<String, ConnectionStateCallback> _connectionCallbacks = {};
  final Map<String, ServicesDiscoveredCallback> _servicesCallbacks = {};

  // Global listeners (prefixed to avoid conflict with BleFlutterApi method names)
  void Function(String state)? bluetoothStateChangedCallback;
  void Function(BlePeripheral peripheral)? peripheralDiscoveredCallback;
  void Function(List<String> peripheralUuids)? stateRestoredCallback;

  /// Register callbacks for a specific peripheral.
  void registerPeripheral({
    required String peripheralUuid,
    CharacteristicValueCallback? onCharacteristicValue,
    AudioBatchCallback? onAudioBatch,
    ConnectionStateCallback? onConnectionState,
    ServicesDiscoveredCallback? onServicesDiscovered,
  }) {
    final key = peripheralUuid.toUpperCase();
    if (onCharacteristicValue != null) _characteristicCallbacks[key] = onCharacteristicValue;
    if (onAudioBatch != null) _audioBatchCallbacks[key] = onAudioBatch;
    if (onConnectionState != null) _connectionCallbacks[key] = onConnectionState;
    if (onServicesDiscovered != null) _servicesCallbacks[key] = onServicesDiscovered;
  }

  /// Unregister all callbacks for a specific peripheral.
  void unregisterPeripheral(String peripheralUuid) {
    final key = peripheralUuid.toUpperCase();
    _characteristicCallbacks.remove(key);
    _audioBatchCallbacks.remove(key);
    _connectionCallbacks.remove(key);
    _servicesCallbacks.remove(key);
  }

  // MARK: - BleFlutterApi implementation

  @override
  void onBluetoothStateChanged(String state) {
    bluetoothStateChangedCallback?.call(state);
  }

  @override
  void onPeripheralDiscovered(BlePeripheral peripheral) {
    peripheralDiscoveredCallback?.call(peripheral);
  }

  @override
  void onPeripheralConnected(String peripheralUuid) {
    final key = peripheralUuid.toUpperCase();
    _connectionCallbacks[key]?.call(true, null);
  }

  @override
  void onPeripheralDisconnected(String peripheralUuid, String? error) {
    final key = peripheralUuid.toUpperCase();
    _connectionCallbacks[key]?.call(false, error);
  }

  @override
  void onServicesDiscovered(String peripheralUuid, List<BleService> services) {
    final key = peripheralUuid.toUpperCase();
    _servicesCallbacks[key]?.call(services);
  }

  @override
  void onCharacteristicValueUpdated(
      String peripheralUuid, String serviceUuid, String characteristicUuid, Uint8List value) {
    final key = peripheralUuid.toUpperCase();
    _characteristicCallbacks[key]?.call(serviceUuid, characteristicUuid, value);
  }

  @override
  void onAudioBatchReceived(
      String peripheralUuid, String serviceUuid, String characteristicUuid, Uint8List batchedData, int notificationCount) {
    final key = peripheralUuid.toUpperCase();
    _audioBatchCallbacks[key]?.call(serviceUuid, characteristicUuid, batchedData, notificationCount);
  }

  @override
  void onStateRestored(List<String> peripheralUuids) {
    Logger.debug('BleBridge: State restored for ${peripheralUuids.length} peripherals');
    stateRestoredCallback?.call(peripheralUuids);
  }
}
