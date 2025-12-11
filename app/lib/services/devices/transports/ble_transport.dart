import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi/utils/bluetooth/bluetooth_adapter.dart';

import 'device_transport.dart';

class BleTransport extends DeviceTransport {
  final BluetoothDevice _bleDevice;
  final StreamController<DeviceTransportState> _connectionStateController;
  final Map<String, StreamController<List<int>>> _streamControllers = {};
  final Map<String, StreamSubscription> _characteristicSubscriptions = {};
  Future<void> _writeQueue = Future.value();

  List<BluetoothService> _services = [];
  DeviceTransportState _state = DeviceTransportState.disconnected;
  StreamSubscription<BluetoothConnectionState>? _bleConnectionSubscription;

  BleTransport(this._bleDevice) : _connectionStateController = StreamController<DeviceTransportState>.broadcast() {
    _bleConnectionSubscription = _bleDevice.connectionState.listen((state) {
      switch (state) {
        case BluetoothConnectionState.disconnected:
          _updateState(DeviceTransportState.disconnected);
          break;
        case BluetoothConnectionState.connecting:
          _updateState(DeviceTransportState.connecting);
          break;
        case BluetoothConnectionState.connected:
          _updateState(DeviceTransportState.connected);
          break;
        case BluetoothConnectionState.disconnecting:
          _updateState(DeviceTransportState.disconnecting);
          break;
      }
    });
  }

  @override
  String get deviceId => _bleDevice.remoteId.str;

  @override
  Stream<DeviceTransportState> get connectionStateStream => _connectionStateController.stream;

  void _updateState(DeviceTransportState newState) {
    if (_state != newState) {
      _state = newState;
      _connectionStateController.add(_state);
    }
  }

  @override
  Future<void> connect() async {
    if (_state == DeviceTransportState.connected) {
      return;
    }

    _updateState(DeviceTransportState.connecting);

    try {
      // Wait for Bluetooth adapter to be ready
      await BluetoothAdapter.adapterState.where((val) => val == BluetoothAdapterStateHelper.on).first;

      // Connect to device
      await _bleDevice.connect();
      await _bleDevice.connectionState.where((val) => val == BluetoothConnectionState.connected).first;

      // Request larger MTU for better performance on Android
      if (Platform.isAndroid && _bleDevice.mtuNow < 512) {
        await _bleDevice.requestMtu(512);
      }

      // Discover services
      _services = await _bleDevice.discoverServices();

      _updateState(DeviceTransportState.connected);
    } catch (e) {
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }
  }

  @override
  Future<void> disconnect() async {
    if (_state == DeviceTransportState.disconnected) {
      return;
    }

    _updateState(DeviceTransportState.disconnecting);

    try {
      for (final subscription in _characteristicSubscriptions.values) {
        await subscription.cancel();
      }
      _characteristicSubscriptions.clear();

      for (final controller in _streamControllers.values) {
        await controller.close();
      }
      _streamControllers.clear();

      await _bleDevice.disconnect();

      _updateState(DeviceTransportState.disconnected);
    } catch (e) {
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }
  }

  @override
  Future<bool> isConnected() async {
    return _bleDevice.isConnected;
  }

  @override
  Future<bool> ping() async {
    try {
      await _bleDevice.readRssi(timeout: 10);
      return true;
    } catch (e) {
      debugPrint('BLE Transport ping failed: $e');
      return false;
    }
  }

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    final key = '$serviceUuid:$characteristicUuid';

    if (!_streamControllers.containsKey(key)) {
      _streamControllers[key] = StreamController<List<int>>.broadcast();
      _setupCharacteristicListener(serviceUuid, characteristicUuid, key);
    }

    return _streamControllers[key]!.stream;
  }

  Future<void> _setupCharacteristicListener(String serviceUuid, String characteristicUuid, String key) async {
    try {
      final characteristic = await _getCharacteristic(serviceUuid, characteristicUuid);
      if (characteristic == null) {
        debugPrint('BLE Transport: Characteristic not found: $serviceUuid:$characteristicUuid');
        return;
      }

      await characteristic.setNotifyValue(true);

      final subscription = characteristic.lastValueStream.listen(
        (value) {
          if (_streamControllers[key] != null && !_streamControllers[key]!.isClosed) {
            _streamControllers[key]!.add(value);
          }
        },
        onError: (error) {
          debugPrint('BLE Transport characteristic stream error: $error');
        },
      );

      _characteristicSubscriptions[key] = subscription;
      _bleDevice.cancelWhenDisconnected(subscription);
    } catch (e) {
      debugPrint('BLE Transport: Failed to setup characteristic listener: $e');
    }
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    final characteristic = await _getCharacteristic(serviceUuid, characteristicUuid);
    if (characteristic == null) {
      return [];
    }

    try {
      return await characteristic.read();
    } catch (e) {
      debugPrint('BLE Transport: Failed to read characteristic: $e');
      return [];
    }
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    final characteristic = await _getCharacteristic(serviceUuid, characteristicUuid);
    if (characteristic == null) {
      throw Exception('Characteristic not found: $serviceUuid:$characteristicUuid');
    }

    final task = _writeQueue.then((_) async {
      int retries = 0;
      while (true) {
        if (_state != DeviceTransportState.connected || !_bleDevice.isConnected) {
          debugPrint('Skipping write: Device is disconnected');
          return;
        }

        try {
          await characteristic
              .write(
                data,
                withoutResponse: characteristic.properties.writeWithoutResponse,
                allowLongWrite: true,
              )
              .timeout(const Duration(seconds: 2));
          return;
        } catch (e) {
          if (_isDisconnectionError(e)) {
            debugPrint('Device Disconnected');
            return;
          }

          if (!_bleDevice.isConnected) {
            return;
          }

          final retryable = _isRetryable(e);
          if (!retryable || retries >= 3) {
            debugPrint('BLE write failed (stop retry) $serviceUuid:$characteristicUuid → $e');
            rethrow;
          }

          final delay = 80 * (1 << retries);
          await Future.delayed(Duration(milliseconds: delay));
          retries++;
        }
      }
    });

    _writeQueue = task.catchError((_) {});
    await task;
  }

  Future<BluetoothCharacteristic?> _getCharacteristic(String serviceUuid, String characteristicUuid) async {
    final service = _services.firstWhereOrNull(
      (service) => service.uuid.str128.toLowerCase() == serviceUuid.toLowerCase(),
    );

    if (service == null) {
      return null;
    }

    return service.characteristics.firstWhereOrNull(
      (characteristic) => characteristic.uuid.str128.toLowerCase() == characteristicUuid.toLowerCase(),
    );
  }

  bool _isDisconnectionError(Object e) {
    final msg = e.toString().toLowerCase();
    final is133 = RegExp(r'\b133\b').hasMatch(msg);

    return is133 ||
        msg.contains("gatt_error") ||
        msg.contains("unknown_ble_error") ||
        msg.contains("device is disconnected") ||
        msg.contains("the device is disconnected");
  }

  bool _isRetryable(Object e) {
    if (e is FlutterBluePlusException) {
      final desc = (e.description ?? "").toLowerCase();
      if (e.code == 201 || desc.contains("busy")) return true;
      return false;
    }

    final msg = e.toString().toLowerCase();
    return msg.contains("busy") || RegExp(r'\b201\b').hasMatch(msg);
  }

  @override
  Future<void> dispose() async {
    await _bleConnectionSubscription?.cancel();

    for (final subscription in _characteristicSubscriptions.values) {
      await subscription.cancel();
    }
    _characteristicSubscriptions.clear();

    for (final controller in _streamControllers.values) {
      await controller.close();
    }
    _streamControllers.clear();

    await _connectionStateController.close();
  }
}
