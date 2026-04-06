import 'dart:typed_data';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/utils/logger.dart';

/// Callback signature for characteristic value updates.
typedef CharacteristicValueCallback = void Function(String serviceUuid, String characteristicUuid, Uint8List value);

/// Callback signature for connection state changes
typedef ConnectionStateCallback = void Function(bool connected, String? error);

/// Callback signature for device ready (connected + services + bonded + MTU done).
typedef DeviceReadyCallback = void Function(List<BleService> services);

/// Callback signature for RSSI updates (diagnostics).
typedef RssiUpdateCallback = void Function(int rssi);

/// Singleton bridge that implements BleFlutterApi (Pigeon) and dispatches
/// native BLE events to registered listeners (NativeBleTransport instances).
class BleBridge implements BleFlutterApi {
  static final BleBridge instance = BleBridge._();

  BleBridge._();

  final Map<String, CharacteristicValueCallback> _characteristicCallbacks = {};
  final Map<String, ConnectionStateCallback> _disconnectCallbacks = {};
  final Map<String, DeviceReadyCallback> _deviceReadyCallbacks = {};
  final Map<String, RssiUpdateCallback> _rssiCallbacks = {};

  void Function(String state)? bluetoothStateChangedCallback;
  void Function(BlePeripheral peripheral)? peripheralDiscoveredCallback;
  void Function(List<String> peripheralUuids)? stateRestoredCallback;

  void registerPeripheral({
    required String peripheralUuid,
    CharacteristicValueCallback? onCharacteristicValue,
    ConnectionStateCallback? onConnectionState,
    DeviceReadyCallback? onDeviceReady,
  }) {
    final key = peripheralUuid.toUpperCase();
    if (onCharacteristicValue != null) _characteristicCallbacks[key] = onCharacteristicValue;
    if (onConnectionState != null) _disconnectCallbacks[key] = onConnectionState;
    if (onDeviceReady != null) _deviceReadyCallbacks[key] = onDeviceReady;
  }

  void registerRssiCallback(String peripheralUuid, RssiUpdateCallback callback) {
    _rssiCallbacks[peripheralUuid.toUpperCase()] = callback;
  }

  void unregisterRssiCallback(String peripheralUuid) {
    _rssiCallbacks.remove(peripheralUuid.toUpperCase());
  }

  void unregisterPeripheral(String peripheralUuid) {
    final key = peripheralUuid.toUpperCase();
    _characteristicCallbacks.remove(key);
    _disconnectCallbacks.remove(key);
    _deviceReadyCallbacks.remove(key);
  }

  @override
  void onBluetoothStateChanged(String state) {
    bluetoothStateChangedCallback?.call(state);
  }

  @override
  void onPeripheralDiscovered(BlePeripheral peripheral) {
    peripheralDiscoveredCallback?.call(peripheral);
  }

  @override
  void onDeviceReady(String peripheralUuid, List<BleService> services) {
    final key = peripheralUuid.toUpperCase();
    _deviceReadyCallbacks[key]?.call(services);
  }

  @override
  void onPeripheralDisconnected(String peripheralUuid, String? error) {
    final key = peripheralUuid.toUpperCase();
    _disconnectCallbacks[key]?.call(false, error);
  }

  @override
  void onCharacteristicValueUpdated(
    String peripheralUuid,
    String serviceUuid,
    String characteristicUuid,
    Uint8List value,
  ) {
    final key = peripheralUuid.toUpperCase();
    _characteristicCallbacks[key]?.call(serviceUuid, characteristicUuid, value);
  }

  @override
  void onRssiUpdate(String peripheralUuid, int rssi) {
    _rssiCallbacks[peripheralUuid.toUpperCase()]?.call(rssi);
  }

  @override
  void onStateRestored(List<String> peripheralUuids) {
    Logger.debug('BleBridge: State restored for ${peripheralUuids.length} peripherals');
    stateRestoredCallback?.call(peripheralUuids);
  }
}
