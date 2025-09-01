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

        // connected
        var pongAt = _connection?.pongAt;
        var shouldPing = (pongAt == null || pongAt.isBefore(DateTime.now().subtract(const Duration(seconds: 30))));
        if (shouldPing) {
          var ok = await _connection?.ping() ?? false;
          if (!ok) {
            await _connection?.disconnect();
            return null;
          }
        }

        return _connection;
      }

      // Force
      if (deviceId == _connection?.device.id && _connection?.status == DeviceConnectionState.connected) {
        var pongAt = _connection?.pongAt;
        var shouldPing = (pongAt == null || pongAt.isBefore(DateTime.now().subtract(const Duration(seconds: 30))));
        if (shouldPing) {
          var ok = await _connection?.ping() ?? false;
          if (!ok) {
            await _connection?.disconnect();
            return null;
          }
        }

        return _connection;
      }

      // connect
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
