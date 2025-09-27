import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:omi/utils/mutex.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/errors.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/services/devices/discovery/device_discoverer.dart';
import 'package:omi/services/devices/discovery/bluetooth_discoverer.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/discovery/apple_watch_discoverer.dart';
import 'package:omi/services/devices/communication/device_communicator.dart';
import 'package:omi/services/devices/communication/communicator_factory.dart';

abstract class IDeviceService {
  void start();
  void stop();
  Future<void> discover({String? desirableDeviceId, int timeout = 5});

  Future<DeviceConnection?> ensureConnection(String deviceId, {bool force = false});

  void subscribe(IDeviceServiceSubsciption subscription, Object context);
  void unsubscribe(Object context);

  DateTime? getFirstConnectedAt();
}

enum DeviceServiceStatus {
  init,
  ready,
  scanning,
  stop,
}

// enum DeviceConnectionState {
//   connected,
//   disconnected,
// }

class OmiFeatures {
  static const int speaker = 1 << 0;
  static const int accelerometer = 1 << 1;
  static const int button = 1 << 2;
  static const int battery = 1 << 3;
  static const int usb = 1 << 4;
  static const int haptic = 1 << 5;
  static const int offlineStorage = 1 << 6;
  static const int ledDimming = 1 << 7;
}

abstract class IDeviceServiceSubsciption {
  void onDevices(List<BtDevice> devices);
  void onStatusChanged(DeviceServiceStatus status);
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state);
}

class DeviceService implements IDeviceService {
  DeviceServiceStatus _status = DeviceServiceStatus.init;
  List<BtDevice> _devices = [];

  // New: discoverers (start with Bluetooth only to keep behavior)
  final List<DeviceDiscoverer> _discoverers = [
    BluetoothDeviceDiscoverer(),
    AppleWatchDiscoverer(),
  ];

  final Map<Object, IDeviceServiceSubsciption> _subscriptions = {};

  DeviceConnection? _connection;
  final Map<String, DeviceCommunicator> _communicators = {};

  List<BtDevice> get devices => _devices;

  DeviceServiceStatus get status => _status;

  DateTime? _firstConnectedAt;

  @override
  Future<void> discover({
    String? desirableDeviceId,
    int timeout = 5,
  }) async {
    debugPrint("Device discovering...");
    if (_status != DeviceServiceStatus.ready) {
      logCommonErrorMessage("Device service is not ready, may busying or stop");
      return;
    }

    _status = DeviceServiceStatus.scanning;

    try {
      final discoveredDevices = <BtDevice>[];

      // Sequential to preserve timing/ordering; can parallelize later
      for (final d in _discoverers.where((d) => d.isSupported)) {
        try {
          final result = await d.discover(timeout: timeout);
          discoveredDevices.addAll(result.devices);

          // We no longer keep BLE ScanResult around in the service
        } catch (e, st) {
          debugPrint('Discovery failed for ${d.name}: $e');
          debugPrint('$st');
        }
      }

      _devices = discoveredDevices;
      onDevices(devices);

      if (desirableDeviceId != null && desirableDeviceId.isNotEmpty) {
        await ensureConnection(desirableDeviceId, force: true);
      }
    } finally {
      _status = DeviceServiceStatus.ready;
    }
  }

  // Legacy helper is no longer used after introducing discoverers.

  Future<void> _connectToDevice(String id) async {
    // Drop exist connection first
    if (_connection?.status == DeviceConnectionState.connected) {
      await _connection?.disconnect();
    }
    _connection = null;

    var device = _devices.firstWhereOrNull((f) => f.id == id);
    if (device == null) {
      debugPrint("device is null");
      return;
    }

    // Create communicator for this device
    final communicator = CommunicatorFactory.create(device);
    if (communicator == null) {
      debugPrint("Failed to create communicator for device: ${device.id}");
      return;
    }

    // Store communicator for later use
    _communicators[device.id] = communicator;

    // For now, still use the existing DeviceConnectionFactory for compatibility
    // TODO: Refactor DeviceConnection to use communicators directly
    if (device.locator?.kind == TransportKind.bluetooth) {
      final targetId = device.locator!.bluetoothId;
      if (targetId == null) {
        debugPrint("Bluetooth locator missing deviceId for ${device.id}");
        return;
      }
      final bleDevice = BluetoothDevice.fromId(targetId);

      if (bleDevice.isConnected) {
        await bleDevice.disconnect();
      }

      _connection = DeviceConnectionFactory.create(device, bleDevice);
      await _connection?.connect(onConnectionStateChanged: onDeviceConnectionStateChanged);
    } else if (device.locator?.kind == TransportKind.watchConnectivity) {
      await _connectToAppleWatch();
    }
  }

  // Legacy discover method removed (now handled by AppleWatchDiscoverer)

  Future<void> _connectToAppleWatch() async {
    // Build a pseudo BLE device wrapper for factory (not used by AW connection)
    final device = _devices.firstWhereOrNull((f) => f.id == 'apple-watch');
    if (device == null) {
      return;
    }

    // Create a dummy BluetoothDevice to satisfy the existing factory signature.
    final fakeBle = await _createFakeBleDevice();

    // Drop any existing connection
    if (_connection?.status == DeviceConnectionState.connected) {
      await _connection?.disconnect();
    }
    _connection = DeviceConnectionFactory.create(device, fakeBle);
    try {
      await _connection?.connect(onConnectionStateChanged: onDeviceConnectionStateChanged);
    } catch (e) {
      debugPrint('Error connecting to Apple Watch: $e');
      onDeviceConnectionStateChanged('apple-watch', DeviceConnectionState.disconnected);
    }
  }

  Future<BluetoothDevice> _createFakeBleDevice() async {
    try {
      return BluetoothDevice.fromId('00:00:00:00:00:00');
    } catch (_) {
      // This should rarely happen; in worst case throw to surface
      throw Exception('No BLE context available to create Apple Watch connection');
    }
  }

  @override
  void subscribe(IDeviceServiceSubsciption subscription, Object context) {
    _subscriptions.remove(context.hashCode);
    _subscriptions.putIfAbsent(context.hashCode, () => subscription);

    // Retains
    subscription.onDevices(_devices);
    subscription.onStatusChanged(_status);
  }

  @override
  void unsubscribe(Object context) {
    _subscriptions.remove(context.hashCode);
  }

  @override
  void start() {
    _status = DeviceServiceStatus.ready;

    // TODO: Start watchdog to discover automatically, re-connect automatically
  }

  @override
  void stop() {
    _status = DeviceServiceStatus.stop;
    onStatusChanged(_status);

    // Stop all discoverers to prevent resource leaks and battery drain
    for (final discoverer in _discoverers) {
      discoverer.stop();
    }

    // Clean up all communicators
    for (final communicator in _communicators.values) {
      communicator.dispose();
    }
    _communicators.clear();

    _subscriptions.clear();
    _devices.clear();
  }

  void onStatusChanged(DeviceServiceStatus status) {
    for (var s in _subscriptions.values) {
      s.onStatusChanged(status);
    }
  }

  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    debugPrint("device connection state changed...$deviceId...$state");
    DebugLogManager.logEvent('device_connection_state', {
      'device_id': deviceId,
      'state': state.name,
    });
    for (var s in _subscriptions.values) {
      s.onDeviceConnectionStateChanged(deviceId, state);
    }
  }

  void onDevices(List<BtDevice> devices) {
    for (var s in _subscriptions.values) {
      s.onDevices(devices);
    }
  }

  // Warn: Should use a better solution to prevent race conditions
  final Mutex _mutex = Mutex();
  @override
  Future<DeviceConnection?> ensureConnection(String deviceId, {bool force = false}) async {
    await _mutex.acquire();
    try {
      debugPrint("ensureConnection ${_connection?.device.id} ${_connection?.status} $force");

      // Not force
      if (!force && _connection != null) {
        if (_connection?.device.id != deviceId || _connection?.status != DeviceConnectionState.connected) {
          return null;
        }

        // Connected
        return _connection;
      }

      // Force
      if (deviceId == _connection?.device.id && _connection?.status == DeviceConnectionState.connected) {
        return _connection;
      }

      // Connect
      try {
        await _connectToDevice(deviceId);
      } on DeviceConnectionException catch (e) {
        debugPrint(e.toString());
        return null;
      }

      _firstConnectedAt ??= DateTime.now();
      return _connection;
    } finally {
      _mutex.release();
    }
  }

  @override
  DateTime? getFirstConnectedAt() {
    return _firstConnectedAt;
  }
}
