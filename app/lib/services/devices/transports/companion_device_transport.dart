import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi/services/devices/companion_device_manager.dart';
import 'package:omi/services/devices/transports/ble_transport.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

/// A transport wrapper that adds Android CompanionDeviceManager support to BleTransport.
///
/// Architecture:
/// - CompanionDeviceTransport wraps a BleTransport
/// - Delegates all BLE operations to the underlying BleTransport
/// - Adds presence detection via CompanionDeviceManager
/// - Listens for presence events and triggers reconnection
class CompanionDeviceTransport extends DeviceTransport {
  final BleTransport _bleTransport;
  final String _deviceAddress;
  final CompanionDeviceManagerService _companionService;

  StreamSubscription<CompanionDeviceEvent>? _presenceSubscription;
  bool _isObservingPresence = false;
  bool _autoReconnectEnabled = false;

  /// Callback when device presence is detected
  void Function()? onDeviceAppeared;

  /// Callback when device disappears
  void Function()? onDeviceDisappeared;

  CompanionDeviceTransport(
    BluetoothDevice bleDevice, {
    CompanionDeviceManagerService? companionService,
  })  : _bleTransport = BleTransport(bleDevice),
        _deviceAddress = bleDevice.remoteId.str,
        _companionService = companionService ?? CompanionDeviceManagerService.instance {
    _setupPresenceListener();
  }

  void _setupPresenceListener() {
    _presenceSubscription = _companionService.events.listen((event) {
      // Only handle events for our device
      if (event.deviceAddress != _deviceAddress) return;

      switch (event.type) {
        case CompanionDeviceEventType.appeared:
          debugPrint('CompanionDeviceTransport: Device appeared - $_deviceAddress');
          onDeviceAppeared?.call();

          // Auto-reconnect if enabled
          if (_autoReconnectEnabled) {
            _handleDeviceAppeared();
          }
          break;

        case CompanionDeviceEventType.disappeared:
          debugPrint('CompanionDeviceTransport: Device disappeared - $_deviceAddress');
          onDeviceDisappeared?.call();
          break;

        case CompanionDeviceEventType.associated:
          debugPrint('CompanionDeviceTransport: Device associated - $_deviceAddress');
          break;
      }
    });
  }

  Future<void> _handleDeviceAppeared() async {
    // Device appeared, try to connect
    try {
      await connect(autoConnect: false); // Direct connect since device is available
    } catch (e) {
      debugPrint('CompanionDeviceTransport: Auto-reconnect failed: $e');
    }
  }

  @override
  String get deviceId => _bleTransport.deviceId;

  @override
  Stream<DeviceTransportState> get connectionStateStream => _bleTransport.connectionStateStream;

  /// Connect to the device.
  @override
  Future<void> connect({bool autoConnect = false}) async {
    if (autoConnect && Platform.isAndroid) {
      final presenceSupported = await _companionService.isPresenceObservingSupported();

      if (presenceSupported) {
        // Check if device is associated
        final isAssociated = await _companionService.isDeviceAssociated(_deviceAddress);

        if (isAssociated) {
          await _startPresenceObservation();
          _autoReconnectEnabled = true;

          try {
            await _bleTransport.connect(autoConnect: false);
            return;
          } catch (e) {
            debugPrint('CompanionDeviceTransport: Initial connect failed, waiting for presence: $e');
            return;
          }
        } else {
          debugPrint('CompanionDeviceTransport: Device not associated, using BLE autoConnect');
        }
      }
    }

    await _bleTransport.connect(autoConnect: autoConnect);
  }

  Future<void> _startPresenceObservation() async {
    if (_isObservingPresence) return;

    final success = await _companionService.startObservingDevicePresence(_deviceAddress);
    if (success) {
      _isObservingPresence = true;
      debugPrint('CompanionDeviceTransport: Started presence observation for $_deviceAddress');
    } else {
      debugPrint('CompanionDeviceTransport: Failed to start presence observation');
    }
  }

  Future<void> _stopPresenceObservation() async {
    if (!_isObservingPresence) return;

    await _companionService.stopObservingDevicePresence(_deviceAddress);
    _isObservingPresence = false;
    debugPrint('CompanionDeviceTransport: Stopped presence observation for $_deviceAddress');
  }

  @override
  Future<void> disconnect() async {
    _autoReconnectEnabled = false;
    await _stopPresenceObservation();
    await _bleTransport.disconnect();
  }

  @override
  Future<bool> isConnected() => _bleTransport.isConnected();

  @override
  Future<bool> ping() => _bleTransport.ping();

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    return _bleTransport.getCharacteristicStream(serviceUuid, characteristicUuid);
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) {
    return _bleTransport.readCharacteristic(serviceUuid, characteristicUuid);
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) {
    return _bleTransport.writeCharacteristic(serviceUuid, characteristicUuid, data);
  }

  @override
  Future<void> dispose() async {
    _autoReconnectEnabled = false;
    await _presenceSubscription?.cancel();
    await _stopPresenceObservation();
    await _bleTransport.dispose();
  }

  Future<AssociationResult> associateDevice({String? deviceName}) async {
    return _companionService.associate(
      deviceAddress: _deviceAddress,
      deviceName: deviceName,
    );
  }

  Future<bool> isAssociated() async {
    return _companionService.isDeviceAssociated(_deviceAddress);
  }

  Future<void> enableAutoReconnect() async {
    _autoReconnectEnabled = true;
    await _startPresenceObservation();
  }

  Future<void> disableAutoReconnect() async {
    _autoReconnectEnabled = false;
    await _stopPresenceObservation();
  }

  bool get isObservingPresence => _isObservingPresence;

  bool get isAutoReconnectEnabled => _autoReconnectEnabled;
}
