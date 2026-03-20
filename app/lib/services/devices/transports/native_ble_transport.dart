import 'dart:async';
import 'dart:typed_data';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/logger.dart';
import 'device_transport.dart';

/// BLE transport backed by native platform APIs via Pigeon.
/// iOS: CoreBluetooth. Android: BluetoothGatt + CompanionDeviceManager.
class NativeBleTransport extends DeviceTransport {
  final String _peripheralUuid;
  final BleHostApi _hostApi = BleHostApi();
  final StreamController<DeviceTransportState> _connectionStateController =
      StreamController<DeviceTransportState>.broadcast();

  /// Characteristic notification streams, keyed by "serviceUuid:charUuid" (lowercased).
  final Map<String, StreamController<List<int>>> _streamControllers = {};

  /// Discovered services from native.
  List<BleService> _services = [];
  Completer<void>? _connectCompleter;
  Completer<List<BleService>>? _servicesCompleter;

  DeviceTransportState _state = DeviceTransportState.disconnected;

  NativeBleTransport(this._peripheralUuid) {
    BleBridge.instance.registerPeripheral(
      peripheralUuid: _peripheralUuid,
      onConnectionState: _handleConnectionState,
      onServicesDiscovered: _handleServicesDiscovered,
      onCharacteristicValue: _handleCharacteristicValue,
    );
  }

  @override
  String get deviceId => _peripheralUuid;

  @override
  Stream<DeviceTransportState> get connectionStateStream => _connectionStateController.stream;

  // MARK: - Connection

  @override
  Future<void> connect() async {
    if (_state == DeviceTransportState.connected) return;

    _updateState(DeviceTransportState.connecting);

    try {
      _connectCompleter = Completer<void>();
      // Set services completer early — native may send onServicesDiscovered
      // together with onPeripheralConnected (when already connected)
      _servicesCompleter = Completer<List<BleService>>();
      _hostApi.connectPeripheral(_peripheralUuid);

      await _connectCompleter!.future.timeout(const Duration(seconds: 30));
      _connectCompleter = null;

      // If services already arrived (from already-connected path), use them
      if (_servicesCompleter!.isCompleted || _services.isNotEmpty) {
        if (!_servicesCompleter!.isCompleted) _servicesCompleter!.complete(_services);
      } else {
        // Trigger discovery — native hasn't sent services yet (fresh connection)
        _hostApi.discoverServices(_peripheralUuid);
      }

      _services = await _servicesCompleter!.future.timeout(const Duration(seconds: 15));
      _servicesCompleter = null;

      // Audio batching disabled — backend expects one Opus frame per WebSocket message.
      // Batching would require backend changes to handle concatenated frames.

      _updateState(DeviceTransportState.connected);
    } catch (e) {
      print('[NativeBleTransport] connect failed: $e');
      _connectCompleter = null;
      _servicesCompleter = null;
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }
  }

  @override
  Future<void> disconnect() async {
    if (_state == DeviceTransportState.disconnected) return;

    _updateState(DeviceTransportState.disconnecting);

    try {
      // Unsubscribe all active streams
      for (final key in _streamControllers.keys.toList()) {
        final parts = key.split(':');
        if (parts.length == 2) {
          try {
            _hostApi.unsubscribeCharacteristic(_peripheralUuid, parts[0], parts[1]);
          } catch (_) {}
        }
      }

      _closeAllStreams();
      _hostApi.disconnectPeripheral(_peripheralUuid);
      _updateState(DeviceTransportState.disconnected);
    } catch (e) {
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }
  }

  @override
  Future<bool> isConnected() async {
    try {
      return _hostApi.isPeripheralConnected(_peripheralUuid);
    } catch (e) {
      return false;
    }
  }

  @override
  Future<bool> ping() async {
    try {
      return _hostApi.isPeripheralConnected(_peripheralUuid);
    } catch (e) {
      return false;
    }
  }

  // MARK: - Characteristic Streams

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    final key = '${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}';

    if (!_streamControllers.containsKey(key)) {
      _streamControllers[key] = StreamController<List<int>>.broadcast();
      _subscribeCharacteristic(serviceUuid, characteristicUuid);
    }

    return _streamControllers[key]!.stream;
  }

  void _subscribeCharacteristic(String serviceUuid, String characteristicUuid) {
    try {
      _hostApi.subscribeCharacteristic(_peripheralUuid, serviceUuid, characteristicUuid);
    } catch (e) {
      print('[NativeBleTransport] Failed to subscribe $serviceUuid:$characteristicUuid: $e');
    }
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    try {
      final data = await _hostApi.readCharacteristic(_peripheralUuid, serviceUuid, characteristicUuid);
      return data.toList();
    } catch (e) {
      print('[NativeBleTransport] Failed to read $serviceUuid:$characteristicUuid: $e');
      return [];
    }
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    try {
      await _hostApi.writeCharacteristic(_peripheralUuid, serviceUuid, characteristicUuid, Uint8List.fromList(data));
    } catch (e) {
      print('[NativeBleTransport] Failed to write characteristic: $e');
      rethrow;
    }
  }

  // MARK: - Dispose

  @override
  Future<void> dispose() async {
    BleBridge.instance.unregisterPeripheral(_peripheralUuid);
    _closeAllStreams();
    await _connectionStateController.close();
  }

  // MARK: - Private Helpers

  void _updateState(DeviceTransportState newState) {
    if (_state != newState) {
      _state = newState;
      _connectionStateController.add(_state);
    }
  }

  void _closeAllStreams() {
    for (final controller in _streamControllers.values) {
      controller.close();
    }
    _streamControllers.clear();
  }

  void _addToStream(String serviceUuid, String characteristicUuid, List<int> data) {
    final key = '${serviceUuid.toLowerCase()}:${characteristicUuid.toLowerCase()}';
    final controller = _streamControllers[key];
    if (controller != null && !controller.isClosed) {
      controller.add(data);
    }
  }

  // MARK: - Native Callbacks

  /// Track which characteristics were subscribed so we can re-subscribe on reconnect.
  final Set<String> _activeSubscriptionKeys = {};

  void _handleConnectionState(bool connected, String? error) {
    if (connected) {
      // Complete pending connect if waiting
      if (_connectCompleter != null && !_connectCompleter!.isCompleted) {
        _connectCompleter!.complete();
      } else {
        // Auto-reconnect from native — re-discover services and re-subscribe
        _resubscribeAfterReconnect();
      }
    } else {
      // Remember active subscriptions before closing streams
      _activeSubscriptionKeys.clear();
      _activeSubscriptionKeys.addAll(_streamControllers.keys);

      _closeAllStreams();
      _services = []; // Clear so reconnect waits for fresh discovery
      _updateState(DeviceTransportState.disconnected);

      // Fail pending completers
      if (_connectCompleter != null && !_connectCompleter!.isCompleted) {
        _connectCompleter!.completeError(error ?? 'Disconnected');
      }
      if (_servicesCompleter != null && !_servicesCompleter!.isCompleted) {
        _servicesCompleter!.completeError(error ?? 'Disconnected');
      }
    }
  }

  bool _isResubscribing = false;

  Future<void> _resubscribeAfterReconnect() async {
    if (_isResubscribing) return;
    _isResubscribing = true;
    try {
      // Wait for native to complete its connect → MTU → discoverServices flow
      // Native fires onServicesDiscovered automatically, so just wait for it
      if (_services.isEmpty) {
        _servicesCompleter = Completer<List<BleService>>();
        _services = await _servicesCompleter!.future.timeout(const Duration(seconds: 15));
        _servicesCompleter = null;
      }

      // Re-create stream controllers and re-subscribe to previously active characteristics
      for (final key in _activeSubscriptionKeys) {
        final parts = key.split(':');
        if (parts.length == 2) {
          _streamControllers[key] = StreamController<List<int>>.broadcast();
          _subscribeCharacteristic(parts[0], parts[1]);
        }
      }

      _updateState(DeviceTransportState.connected);
    } catch (e) {
      print('[NativeBleTransport] Failed to re-subscribe after reconnect: $e');
      _servicesCompleter = null;
      _updateState(DeviceTransportState.disconnected);
    } finally {
      _isResubscribing = false;
    }
  }

  void _handleServicesDiscovered(List<BleService> services) {
    _services = services;
    if (_servicesCompleter != null && !_servicesCompleter!.isCompleted) {
      _servicesCompleter!.complete(services);
    }
  }

  void _handleCharacteristicValue(String serviceUuid, String characteristicUuid, Uint8List value) {
    _addToStream(serviceUuid, characteristicUuid, value);
  }
}
