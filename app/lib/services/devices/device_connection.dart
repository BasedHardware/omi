import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/frame_connection.dart';
import 'package:omi/services/devices/apple_watch_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/omi_connection.dart';
import 'package:omi/services/devices/plaud_connection.dart';
import 'package:omi/services/devices/bee_connection.dart';
import 'package:omi/services/devices/fieldy_connection.dart';
import 'package:omi/services/devices/friend_pendant_connection.dart';
import 'package:omi/services/devices/limitless_connection.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/devices/transports/ble_transport.dart';
import 'package:omi/services/devices/transports/companion_device_transport.dart';
import 'package:omi/services/devices/transports/watch_transport.dart';
import 'package:omi/services/devices/transports/frame_transport.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';

class DeviceConnectionFactory {
  static DeviceConnection? create(BtDevice device) {
    DeviceTransport transport;

    // Create transport based on device locator
    final locator = device.locator;
    if (locator == null) return null;

    switch (locator.kind) {
      case TransportKind.bluetooth:
        final deviceId = locator.bluetoothId;
        if (deviceId == null) return null;
        final bleDevice = BluetoothDevice.fromId(deviceId);
        if (Platform.isAndroid) {
          transport = CompanionDeviceTransport(bleDevice);
        } else {
          transport = BleTransport(bleDevice);
        }
        break;

      case TransportKind.watchConnectivity:
        transport = WatchTransport();
        break;

      default:
        return null;
    }

    // Create device connection with transport
    switch (device.type) {
      case DeviceType.omi:
      case DeviceType.openglass:
        return OmiDeviceConnection(device, transport);
      case DeviceType.bee:
        return BeeDeviceConnection(device, transport);
      case DeviceType.plaud:
        return PlaudDeviceConnection(device, transport);
      case DeviceType.frame:
        if (locator.kind == TransportKind.bluetooth) {
          final deviceId = locator.bluetoothId;
          if (deviceId == null) return null;
          transport = FrameTransport(deviceId);
        }
        return FrameDeviceConnection(device, transport);
      case DeviceType.appleWatch:
        return AppleWatchDeviceConnection(device, transport);
      case DeviceType.fieldy:
        return FieldyDeviceConnection(device, transport);
      case DeviceType.friendPendant:
        return FriendPendantDeviceConnection(device, transport);
      case DeviceType.limitless:
        return LimitlessDeviceConnection(device, transport);
    }
  }
}

class DeviceConnectionException implements Exception {
  String cause;
  DeviceConnectionException(this.cause);
}

abstract class DeviceConnection {
  BtDevice device;
  DeviceTransport transport;
  DateTime? _pongAt;
  int? _features;

  DeviceConnectionState _connectionState = DeviceConnectionState.disconnected;

  DeviceConnectionState get status => _connectionState;

  DeviceConnectionState get connectionState => _connectionState;

  @protected
  set connectionState(DeviceConnectionState state) => _connectionState = state;

  Function(String deviceId, DeviceConnectionState state)? _connectionStateChangedCallback;

  DateTime? get pongAt => _pongAt;

  StreamSubscription<DeviceTransportState>? _transportStateSubscription;

  DeviceConnection(
    this.device,
    this.transport,
  ) {
    // Listen to transport state changes
    _transportStateSubscription = transport.connectionStateStream.listen((transportState) {
      final deviceState = _mapTransportStateToDeviceState(transportState);
      if (_connectionState != deviceState) {
        _connectionState = deviceState;
        _connectionStateChangedCallback?.call(device.id, _connectionState);
      }
    });
  }

  DeviceConnectionState _mapTransportStateToDeviceState(DeviceTransportState transportState) {
    switch (transportState) {
      case DeviceTransportState.connected:
        return DeviceConnectionState.connected;
      case DeviceTransportState.disconnected:
      case DeviceTransportState.connecting:
      case DeviceTransportState.disconnecting:
        return DeviceConnectionState.disconnected;
    }
  }

  Future<void> connect({
    void Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
    bool autoConnect = false,
  }) async {
    if (_connectionState == DeviceConnectionState.connected) {
      throw DeviceConnectionException("Connection already established, please disconnect before start new connection");
    }

    // Set callback for connection state changes
    _connectionStateChangedCallback = onConnectionStateChanged;

    try {
      // Use transport to connect
      await transport.connect(autoConnect: autoConnect);

      // Check connection
      await ping();

      // Update device info
      device = await device.getDeviceInfo(this);
    } catch (e) {
      throw DeviceConnectionException("Transport connection failed: ${e.toString()}");
    }
  }

  Future<void> disconnect() async {
    _connectionState = DeviceConnectionState.disconnected;
    if (_connectionStateChangedCallback != null) {
      _connectionStateChangedCallback!(device.id, _connectionState);
      _connectionStateChangedCallback = null;
    }

    await transport.disconnect();
    await _transportStateSubscription?.cancel();
    _transportStateSubscription = null;
  }

  Future<void> unpair() async {}

  Future<bool> ping() async {
    try {
      final result = await transport.ping();
      if (result) {
        _pongAt = DateTime.now();
      }
      return result;
    } catch (e) {
      debugPrint('Transport ping failed: $e');
      return false;
    }
  }

  void read() {}

  void write() {}

  Future<bool> isConnected() async {
    return await transport.isConnected();
  }

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
  }) async {
    final stream = transport.getCharacteristicStream(batteryServiceUuid, batteryLevelCharacteristicUuid);
    return stream.listen((value) {
      if (value.isNotEmpty && onBatteryLevelChange != null) {
        onBatteryLevelChange(value[0]);
      }
    });
  }

  Future<StreamSubscription?> getBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    if (await isConnected()) {
      return await performGetBleAudioBytesListener(onAudioBytesReceived: onAudioBytesReceived);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<List<int>> getBleButtonState() async {
    if (await isConnected()) {
      debugPrint('button state called');
      return await performGetButtonState();
    }
    debugPrint('button state error');
    return Future.value(<int>[]);
  }

  Future<List<int>> performGetButtonState();

  Future<StreamSubscription?> getBleButtonListener({
    required void Function(List<int>) onButtonReceived,
  }) async {
    if (await isConnected()) {
      return await performGetBleButtonListener(onButtonReceived: onButtonReceived);
    }
    return null;
  }

  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    final stream = transport.getCharacteristicStream(omiServiceUuid, audioDataStreamCharacteristicUuid);
    return stream.listen(onAudioBytesReceived);
  }

  Future<StreamSubscription?> performGetBleButtonListener({
    required void Function(List<int>) onButtonReceived,
  }) async {
    final stream = transport.getCharacteristicStream(buttonServiceUuid, buttonTriggerCharacteristicUuid);
    return stream.listen(onButtonReceived);
  }

  Future<BleAudioCodec> getAudioCodec() async {
    if (await isConnected()) {
      return await performGetAudioCodec();
    }
    _showDeviceDisconnectedNotification();
    return BleAudioCodec.pcm8;
  }

  Future<BleAudioCodec> performGetAudioCodec() async {
    final data = await transport.readCharacteristic(omiServiceUuid, audioCodecCharacteristicUuid);
    if (data.isNotEmpty) {
      final codecId = data[0];
      switch (codecId) {
        case 1:
          return BleAudioCodec.pcm8;
        case 20:
          return BleAudioCodec.opus;
        case 21:
          return BleAudioCodec.opusFS320;
        default:
          return BleAudioCodec.pcm8;
      }
    }
    return BleAudioCodec.pcm8;
  }

  Future<bool> performPlayToSpeakerHaptic(int mode) async {
    try {
      await transport
          .writeCharacteristic(speakerDataStreamServiceUuid, speakerDataStreamCharacteristicUuid, [mode & 0xFF]);
      return true;
    } catch (e) {
      debugPrint('Failed to play haptic: $e');
      return false;
    }
  }

  // storage here

  Future<List<int>> getStorageList() async {
    if (await isConnected()) {
      return await performGetStorageList();
    }
    _showDeviceDisconnectedNotification();
    return Future.value(<int>[]);
  }

  Future<List<int>> performGetStorageList() async {
    return await transport.readCharacteristic(storageDataStreamServiceUuid, storageReadControlCharacteristicUuid);
  }

  Future<bool> performWriteToStorage(int numFile, int command, int offset) async {
    try {
      final offsetBytes = [
        (offset >> 24) & 0xFF,
        (offset >> 16) & 0xFF,
        (offset >> 8) & 0xFF,
        offset & 0xFF,
      ];
      await transport.writeCharacteristic(storageDataStreamServiceUuid, storageDataStreamCharacteristicUuid,
          [command & 0xFF, numFile & 0xFF, offsetBytes[0], offsetBytes[1], offsetBytes[2], offsetBytes[3]]);
      return true;
    } catch (e) {
      debugPrint('Failed to write to storage: $e');
      return false;
    }
  }

  Future<bool> writeToStorage(int numFile, int command, int offset) async {
    if (await isConnected()) {
      return await performWriteToStorage(numFile, command, offset);
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
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async {
    if (await isConnected()) {
      return await performGetImageListener(onImageReceived: onImageReceived);
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
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

  Future<int> getFeatures() async {
    if (_features != null) return _features!;
    if (await isConnected()) {
      _features = await performGetFeatures();
      return _features!;
    }
    _showDeviceDisconnectedNotification();
    return 0;
  }

  Future<int> performGetFeatures();

  Future<void> setLedDimRatio(int ratio) async {
    if (await isConnected()) {
      return await performSetLedDimRatio(ratio);
    }
    _showDeviceDisconnectedNotification();
  }

  Future<void> performSetLedDimRatio(int ratio);

  Future<int?> getLedDimRatio() async {
    if (await isConnected()) {
      return await performGetLedDimRatio();
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<int?> performGetLedDimRatio();

  Future<void> setMicGain(int gain) async {
    if (await isConnected()) {
      return await performSetMicGain(gain);
    }
    _showDeviceDisconnectedNotification();
  }

  Future<void> performSetMicGain(int gain);

  Future<int?> getMicGain() async {
    if (await isConnected()) {
      return await performGetMicGain();
    }
    _showDeviceDisconnectedNotification();
    return null;
  }

  Future<int?> performGetMicGain();

  Future<bool> isWifiSyncSupported() async {
    if (await isConnected()) {
      return await performIsWifiSyncSupported();
    }
    return false;
  }

  Future<bool> performIsWifiSyncSupported() async {
    return false;
  }

  Future<bool> setupWifiSync(String ssid, String password, String serverIp, int port) async {
    if (await isConnected()) {
      return await performSetupWifiSync(ssid, password, serverIp, port);
    }
    _showDeviceDisconnectedNotification();
    return false;
  }

  Future<bool> performSetupWifiSync(String ssid, String password, String serverIp, int port) async {
    return false;
  }

  Future<bool> startWifiSync() async {
    if (await isConnected()) {
      return await performStartWifiSync();
    }
    _showDeviceDisconnectedNotification();
    return false;
  }

  Future<bool> performStartWifiSync() async {
    return false;
  }

  Future<bool> stopWifiSync() async {
    if (await isConnected()) {
      return await performStopWifiSync();
    }
    _showDeviceDisconnectedNotification();
    return false;
  }

  Future<bool> performStopWifiSync() async {
    return false;
  }

  Future<StreamSubscription?> getWifiSyncStatusListener({
    required void Function(int status) onStatusReceived,
  }) async {
    if (await isConnected()) {
      return await performGetWifiSyncStatusListener(onStatusReceived: onStatusReceived);
    }
    return null;
  }

  Future<StreamSubscription?> performGetWifiSyncStatusListener({
    required void Function(int status) onStatusReceived,
  }) async {
    return null;
  }

  void _showDeviceDisconnectedNotification() {
    NotificationService.instance.createNotification(
      title: '${device.name} Disconnected',
      body: 'Please reconnect to continue using your ${device.name}.',
    );
  }
}
