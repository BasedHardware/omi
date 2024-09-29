import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/services/devices/device_connection.dart';
import 'package:friend_private/services/devices/models.dart';

abstract class IDeviceService {
  void start();
  void stop();
  Future<void> discover({String? desirableDeviceId, int timeout = 5});

  Future<DeviceConnection?> ensureConnection(String deviceId, {bool force = false});

  void subscribe(IDeviceServiceSubsciption subscription, Object context);
  void unsubscribe(Object context);
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

  @override
  Future<void> discover({
    String? desirableDeviceId,
    int timeout = 5,
  }) async {
    debugPrint("Device discovering...");
    if (_status != DeviceServiceStatus.ready) {
      throw Exception("Device service is not ready, may busying or stop");
    }

    if (!(await FlutterBluePlus.isSupported)) {
      throw Exception("Bluetooth is not supported");
    }

    if (FlutterBluePlus.isScanningNow) {
      debugPrint("Device service is scanning...");
      return;
    }

    // Listen to scan results, always re-emits previous results
    var discoverSubscription = FlutterBluePlus.scanResults.listen(
      (results) async {
        await _onBleDiscovered(results, desirableDeviceId);
      },
      onError: (e) {
        debugPrint('bleFindDevices error: $e');
      },
    );
    FlutterBluePlus.cancelWhenScanComplete(discoverSubscription);

    // Only look for devices that implement Friend or Frame main service
    _status = DeviceServiceStatus.scanning;
    await FlutterBluePlus.adapterState.where((val) => val == BluetoothAdapterState.on).first;
    await FlutterBluePlus.startScan(
      timeout: Duration(seconds: timeout),
      withServices: [Guid(friendServiceUuid), Guid(frameServiceUuid)],
    );
    _status = DeviceServiceStatus.ready;
  }

  Future<void> _onBleDiscovered(List<ScanResult> results, String? desirableDeviceId) async {
    _bleDevices = results.where((r) => r.device.platformName.isNotEmpty).toList();
    _bleDevices.sort((a, b) => b.rssi.compareTo(a.rssi));
    // Set devices

    // _devices = _bleDevices.map<BtDevice>((deviceResult) {
    //   DeviceType? deviceType;
    //   if (deviceResult.advertisementData.serviceUuids.contains(Guid(friendServiceUuid))) {
    //     deviceType = DeviceType.friend;
    //   } else if (deviceResult.advertisementData.serviceUuids.contains(Guid(frameServiceUuid))) {
    //     deviceType = DeviceType.frame;
    //   }
    //   if (deviceType != null) {
    //     deviceTypeMap[deviceResult.device.remoteId.toString()] = deviceType;
    //   } else if (deviceTypeMap.containsKey(deviceResult.device.remoteId.toString())) {
    //     deviceType = deviceTypeMap[deviceResult.device.remoteId.toString()];
    //   }
    //   return BtDevice(
    //     name: deviceResult.device.platformName,
    //     id: deviceResult.device.remoteId.str,
    //     rssi: deviceResult.rssi,
    //     type: deviceType,
    //   );
    // }).toList();
    _devices = _bleDevices.map<BtDevice>((e) => BtDevice.fromScanResult(e)).toList();
    onDevices(devices);

    // Check desirable device
    if (desirableDeviceId != null) {
      await _connectToDevice(desirableDeviceId);
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

    if (FlutterBluePlus.isScanningNow) {
      FlutterBluePlus.stopScan();
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
    debugPrint("device connection state changed...${deviceId}...${state}");
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
  bool mutex = false;
  @override
  Future<DeviceConnection?> ensureConnection(String deviceId, {bool force = false}) async {
    while (mutex) {
      await Future.delayed(const Duration(milliseconds: 50));
    }
    mutex = true;

    debugPrint("ensureConnection ${_connection?.device.id} ${_connection?.status} ${force}");
    try {
      // Not force
      if (!force && _connection != null) {
        if (_connection?.device.id != deviceId || _connection?.status != DeviceConnectionState.connected) {
          return null;
        }

        // connected
        var pongAt = _connection?.pongAt;
        var shouldPing = (pongAt == null || pongAt.isBefore(DateTime.now().subtract(const Duration(seconds: 5))));
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
        var shouldPing = (pongAt == null || pongAt.isBefore(DateTime.now().subtract(const Duration(seconds: 5))));
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
      await _connectToDevice(deviceId);
      return _connection;
    } finally {
      mutex = false;
    }
  }
}
