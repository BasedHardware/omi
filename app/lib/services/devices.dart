import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:omi/utils/mutex.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/errors.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/bluetooth/bluetooth_adapter.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/src/flutter_communicator.g.dart';

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

enum DeviceConnectionState {
  connected,
  disconnected,
}

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
  List<ScanResult> _bleDevices = [];

  final Map<Object, IDeviceServiceSubsciption> _subscriptions = {};

  DeviceConnection? _connection;

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

    if (!(await BluetoothAdapter.isSupported)) {
      logCommonErrorMessage("Bluetooth is not supported");
      return;
    }

    if (BluetoothAdapter.isScanningNow) {
      debugPrint("Device service is scanning...");
      return;
    }

    // Listen to scan results, always re-emits previous results
    var discoverSubscription = BluetoothAdapter.scanResults.listen(
      (results) async {
        await _onBleDiscovered(results, desirableDeviceId);
      },
      onError: (e) {
        debugPrint('bleFindDevices error: $e');
      },
    );
    BluetoothAdapter.cancelWhenScanComplete(discoverSubscription);

    // Only look for devices that implement Omi or Frame main service
    _status = DeviceServiceStatus.scanning;
    await BluetoothAdapter.adapterState.where((val) => val == BluetoothAdapterStateHelper.on).first;
    await BluetoothAdapter.startScan(
      timeout: Duration(seconds: timeout),
      withServices: [BluetoothAdapter.createGuid(omiServiceUuid), BluetoothAdapter.createGuid(frameServiceUuid)],
    );
    _status = DeviceServiceStatus.ready;
  }

  Future<void> _onBleDiscovered(List<dynamic> results, String? desirableDeviceId) async {
    _bleDevices = results.cast<ScanResult>().where((r) => r.device.platformName.isNotEmpty).toList();
    _bleDevices.sort((a, b) => b.rssi.compareTo(a.rssi));
    _devices = _bleDevices.map<BtDevice>((e) => BtDevice.fromScanResult(e)).toList();

    // Also discover Apple Watch
    await _discoverAppleWatch();
    onDevices(devices);

    // Check desirable device
    if (desirableDeviceId != null && desirableDeviceId.isNotEmpty) {
      await ensureConnection(desirableDeviceId, force: true);
    }
  }

  Future<void> _connectToDevice(String id) async {
    // Drop exist connection first
    if (_connection?.status == DeviceConnectionState.connected) {
      await _connection?.disconnect();
    }
    _connection = null;

    // Handle Apple Watch logical device separately
    if (id == 'apple-watch') {
      await _connectToAppleWatch();
      return;
    }

    var bleDevice = _bleDevices.firstWhereOrNull((f) => f.device.remoteId.str == id);
    var device = _devices.firstWhereOrNull((f) => f.id == id);
    if (bleDevice == null || device == null) {
      debugPrint("bleDevice or device is null");
      return;
    }

    // Check exist ble device connection, force disconnect
    if (bleDevice.device.isConnected) {
      await bleDevice.device.disconnect();
    }

    // Then create new connection
    _connection = DeviceConnectionFactory.create(device, bleDevice.device);
    await _connection?.connect(onConnectionStateChanged: onDeviceConnectionStateChanged);
    return;
  }

  Future<void> _discoverAppleWatch() async {
    try {
      final host = WatchRecorderHostAPI();
      final supported = await host.isWatchSessionSupported();
      final paired = await host.isWatchPaired();
      final reachable = await host.isWatchReachable();

      if (supported && paired) {
        final appleWatch = BtDevice(
          name: 'Apple Watch',
          id: 'apple-watch',
          type: DeviceType.appleWatch,
          rssi: reachable ? 0 : -100,
        );
        _devices.removeWhere((d) => d.type == DeviceType.appleWatch);
        _devices.add(appleWatch);
        onDevices(_devices);
      } else {
        // Remove Apple Watch if not supported/paired
        _devices.removeWhere((d) => d.type == DeviceType.appleWatch);
        onDevices(_devices);
      }
    } catch (e) {
      debugPrint('Apple Watch discover error: $e');
    }
  }

  Future<void> _connectToAppleWatch() async {
    // Build a pseudo BLE device wrapper for factory (not used by AW connection)
    final device = _devices.firstWhereOrNull((f) => f.id == 'apple-watch');
    if (device == null) {
      return;
    }

    // Create a dummy BluetoothDevice to satisfy factory signature
    // We reuse the first BLE device or create a fake handle; AppleWatchDeviceConnection doesn't use it
    final fakeBle = _bleDevices.isNotEmpty ? _bleDevices.first.device : await _createFakeBleDevice();

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

    if (BluetoothAdapter.isScanningNow) {
      BluetoothAdapter.stopScan();
    }
    _subscriptions.clear();
    _devices.clear();
    _bleDevices.clear();
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
