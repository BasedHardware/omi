import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/services/frame_connection.dart';
import 'package:friend_private/services/friend_connection.dart';
import 'package:friend_private/services/notification_service.dart';

class DeviceConnectionFactory {
  static DeviceConnection? create(
    BTDeviceStruct device,
    BluetoothDevice bleDevice,
  ) {
    if (device.type == null) {
      return null;
    }
    switch (device.type!) {
      case DeviceType.friend:
        return FriendDeviceConnection(device, bleDevice);
      case DeviceType.openglass:
        return FriendDeviceConnection(device, bleDevice);
      case DeviceType.frame:
        return FrameDeviceConnection(device, bleDevice);
      default:
        return null;
    }
  }
}

abstract class DeviceConnection {
  BTDeviceStruct device;
  BluetoothDevice bleDevice;
  DateTime? _pongAt;

  DeviceConnectionState _connectionState = DeviceConnectionState.disconnected;

  List<BluetoothService> _services = [];

  DeviceConnectionState get status => _connectionState;

  DeviceConnectionState get connectionState => _connectionState;

  DateTime? get pongAt => _pongAt;

  late StreamSubscription<BluetoothConnectionState> _connectionStateSubscription;

  DeviceConnection(
    this.device,
    this.bleDevice,
  );

  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
  }) async {
    if (_connectionState == DeviceConnectionState.connected) {
      throw Exception("Connection already established, please disconnect before start new connection");
    }

    // Connect
    _connectionStateSubscription = bleDevice.connectionState.listen((BluetoothConnectionState state) async {
      _onBleConnectionStateChanged(state, onConnectionStateChanged);
    });

    await FlutterBluePlus.adapterState.where((val) => val == BluetoothAdapterState.on).first;
    await bleDevice.connect();
    await bleDevice.connectionState.where((val) => val == BluetoothConnectionState.connected).first;

    // Mtu
    if (Platform.isAndroid && bleDevice.mtuNow < 512) {
      await bleDevice.requestMtu(512); // This might fix the code 133 error
    }

    // Check connection
    await ping();

    // Discover services
    _services = await bleDevice.discoverServices();
  }

  void _onBleConnectionStateChanged(
      BluetoothConnectionState state, Function(String deviceId, DeviceConnectionState state)? callback) async {
    if (state == BluetoothConnectionState.disconnected && _connectionState == DeviceConnectionState.connected) {
      _connectionState = DeviceConnectionState.disconnected;
      await disconnect(callback: callback);
      return;
    }

    if (state == BluetoothConnectionState.connected && _connectionState == DeviceConnectionState.disconnected) {
      _connectionState = DeviceConnectionState.connected;
      if (callback != null) {
        callback(device.id, _connectionState);
      }
    }
  }

  Future<void> disconnect({Function(String deviceId, DeviceConnectionState state)? callback}) async {
    _connectionState = DeviceConnectionState.disconnected;
    if (callback != null) {
      callback(device.id, _connectionState);
    }
    await bleDevice.disconnect();
    _connectionStateSubscription.cancel();
    _services.clear();
  }

  Future<bool> ping() async {
    try {
      int rssi = await bleDevice.readRssi();
      device.rssi = rssi;
      _pongAt = DateTime.now();
      return true;
    } catch (e) {
      debugPrint('Error reading RSSI: $e');
    }

    return false;
  }

  void read() {}

  void write() {}

  Future<BluetoothService?> getService(String uuid) async {
    return _services.firstWhereOrNull((service) => service.uuid.str128.toLowerCase() == uuid);
  }

  BluetoothCharacteristic? getCharacteristic(BluetoothService service, String uuid) {
    return service.characteristics.firstWhereOrNull(
      (characteristic) => characteristic.uuid.str128.toLowerCase() == uuid.toLowerCase(),
    );
  }

  // Mimic @app/lib/utils/device_base.dart
  Future<bool> isConnected();

  Future<int> retrieveBatteryLevel() async {
    if (await isConnected()) {
      return await performRetrieveBatteryLevel();
    }
    _showDeviceDisconnectedNotification();
    return -1;
  }

  Future<int> performRetrieveBatteryLevel();

  Future<StreamSubscription<List<int>>?> getBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    if (await isConnected()) {
      return await performGetBleBatteryLevelListener(onBatteryLevelChange: onBatteryLevelChange);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  });

  Future<StreamSubscription?> getBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    if (await isConnected()) {
      return await performGetBleAudioBytesListener(onAudioBytesReceived: onAudioBytesReceived);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  });

  Future<BleAudioCodec> getAudioCodec() async {
    if (await isConnected()) {
      return await performGetAudioCodec();
    }
    _showDeviceDisconnectedNotification();
    return BleAudioCodec.pcm8;
  }

  Future<BleAudioCodec> performGetAudioCodec();
//storage here

  Future<List<int>> getStorageList() async {
    if (await isConnected()) {
      return await performGetStorageList();
    }
    _showDeviceDisconnectedNotification();
    return Future.value(<int>[]);
  }

  Future<List<int>> performGetStorageList();

  Future<bool> performWriteToStorage(int numFile);

  Future<bool> writeToStorage(int numFile) async {
    if (await isConnected()) {
      return await performWriteToStorage(numFile);
    }
    _showDeviceDisconnectedNotification();
    return Future.value(false);
  }

  Future<StreamSubscription?> getBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    if (await isConnected()) {
      return await performGetBleStorageBytesListener(onStorageBytesReceived: onStorageBytesReceived);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  });

  Future cameraStartPhotoController() async {
    if (await isConnected()) {
      return await performCameraStartPhotoController();
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future performCameraStartPhotoController();

  Future cameraStopPhotoController() async {
    if (await isConnected()) {
      return await performCameraStopPhotoController();
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future performCameraStopPhotoController();

  Future<bool> hasPhotoStreamingCharacteristic() async {
    if (await isConnected()) {
      return await performHasPhotoStreamingCharacteristic();
    }
    _showDeviceDisconnectedNotification();
    return false;
  }

  Future<bool> performHasPhotoStreamingCharacteristic();

  Future<StreamSubscription?> getImageListener({
    required void Function(Uint8List base64JpgData) onImageReceived,
  }) async {
    if (await isConnected()) {
      return await performGetImageListener(onImageReceived: onImageReceived);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription?> performGetImageListener({
    required void Function(Uint8List base64JpgData) onImageReceived,
  });

  Future<StreamSubscription<List<int>>?> getAccelListener({
    void Function(int)? onAccelChange,
  }) async {
    if (await isConnected()) {
      return await performGetAccelListener(onAccelChange: onAccelChange);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  });

  void _showDeviceDisconnectedNotification() {
    NotificationService.instance.createNotification(
      title: '${device.name} Disconnected',
      body: 'Please reconnect to continue using your ${device.name}.',
    );
  }
}
