import 'dart:async';
import 'dart:nativewrappers/_internal/vm/lib/ffi_allocation_patch.dart';

import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/ble/gatt_utils.dart';

abstract class IDeviceService {
  void start();
  void stop();
  void discover({String? desirableDeviceId, int timeout = 5});
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

abstract class DeviceServiceSubsciption {
  void onDevices(List<BTDeviceStruct> devices);
  void onStatusChanged(DeviceServiceStatus status);
  void onDesirableDevice(BTDeviceStruct device);
  void onDesirableDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state);
}

class DeviceService implements IDeviceService {
  DeviceServiceStatus _status = DeviceServiceStatus.init;
  List<BTDeviceStruct> _devices = [];
  List<ScanResult> _bleDevices = [];

  final Map<Object, DeviceServiceSubsciption> _subscriptions = {};

  String? _desirableDeviceId;
  DeviceConnectionState _connectionState = DeviceConnectionState.disconnected;

  List<BTDeviceStruct> get devices => _devices;

  DeviceServiceStatus get status => _status;

  @override
  Future<void> discover({
    String? desirableDeviceId,
    int timeout = 5,
  }) async {
    if (_status != DeviceServiceStatus.ready) {
      throw Exception("Device service is not ready, may busying or stop");
    }

    if (!(await FlutterBluePlus.isSupported)) {
      throw Exception("Bluetooth is not supported");
    }

    if (FlutterBluePlus.isScanningNow) {
      throw Exception("Device service is scanning");
    }

    // Desirable device
    _desirableDeviceId = desirableDeviceId;

    // Listen to scan results, always re-emits previous results
    var discoverSubscription = FlutterBluePlus.scanResults.listen(
      (results) async {
        _bleDevices = results.where((r) => r.device.platformName.isNotEmpty).toList();
        _bleDevices.sort((a, b) => b.rssi.compareTo(a.rssi));

        // Set devices
        _devices = _bleDevices.map<BTDeviceStruct>((deviceResult) {
          DeviceType? deviceType;
          if (deviceResult.advertisementData.serviceUuids.contains(Guid(friendServiceUuid))) {
            deviceType = DeviceType.friend;
          } else if (deviceResult.advertisementData.serviceUuids.contains(Guid(frameServiceUuid))) {
            deviceType = DeviceType.frame;
          }
          if (deviceType != null) {
            deviceTypeMap[deviceResult.device.remoteId.toString()] = deviceType;
          } else if (deviceTypeMap.containsKey(deviceResult.device.remoteId.toString())) {
            deviceType = deviceTypeMap[deviceResult.device.remoteId.toString()];
          }
          return BTDeviceStruct(
            name: deviceResult.device.platformName,
            id: deviceResult.device.remoteId.str,
            rssi: deviceResult.rssi,
            type: deviceType,
          );
        }).toList();
        onDevices(devices);

        // Check desirable device
        if (_desirableDeviceId != null) {
          for (var device in devices) {
            // next
            if (device.id != _desirableDeviceId) {
              continue;
            }

            onDesirableDevice(device);
            break;
          }

          // Connect automatically
          await _connectToDevice(_desirableDeviceId!);
        }
      },
      onError: (e) {
        debugPrint('bleFindDevices error: $e');
      },
    );
    FlutterBluePlus.cancelWhenScanComplete(discoverSubscription);

    // Only look for devices that implement Friend or Frame main service
    _status = DeviceServiceStatus.scanning;
    await FlutterBluePlus.startScan(
      timeout: Duration(seconds: timeout),
      withServices: [Guid(friendServiceUuid), Guid(frameServiceUuid)],
    );
    _status = DeviceServiceStatus.ready;
  }

  Future<void> _connectToDevice(String id) async {
    for (var bleDevice in _bleDevices) {
      var device = bleDevice.device;
      // next
      if (device.remoteId.str != _desirableDeviceId) {
        continue;
      }

      var subscription = device.connectionState.listen((BluetoothConnectionState state) async {
        _connectionState = DeviceConnectionState.disconnected;
        if (state == BluetoothConnectionState.connected) {
          _connectionState = DeviceConnectionState.connected;
        }
        onDesirableDeviceConnectionStateChanged(device.remoteId.str, _connectionState);
      });
      device.cancelWhenDisconnected(subscription, delayed: true, next: true);
      await device.connect();
      break;
    }

    return;
  }

  void subscribe(DeviceServiceSubsciption subscription, Object context) {
    _subscriptions.remove(context);
    _subscriptions.putIfAbsent(context, () => subscription);

    // Retains
    subscription.onDevices(_devices);
    subscription.onStatusChanged(_status);
  }

  void unsubscribe(Object context) {
    _subscriptions.remove(context);
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

    if (FlutterBluePlus.isScanning()) {
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

  void onDesirableDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    for (var s in _subscriptions.values) {
      s.onDesirableDeviceConnectionStateChanged(deviceId, state);
    }
  }

  void onDevices(List<BTDeviceStruct> devices) {
    for (var s in _subscriptions.values) {
      s.onDevices(devices);
    }
  }

  void onDesirableDevice(BTDeviceStruct device) {
    for (var s in _subscriptions.values) {
      s.onDesirableDevice(device);
    }
  }
}
