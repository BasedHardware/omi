import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device_info.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

class DeviceProvider extends ChangeNotifier implements IDeviceServiceSubsciption {
  CaptureProvider? captureProvider;

  bool isConnecting = false;
  bool isConnected = false;
  BtDevice? connectedDevice;
  BtDeviceInfo? deviceInfo;
  StreamSubscription<List<int>>? _bleBatteryLevelListener;
  int batteryLevel = -1;
  Timer? _reconnectionTimer;
  int connectionCheckSeconds = 4;

  Timer? _disconnectNotificationTimer;

  DeviceProvider() {
    ServiceManager.instance().device.subscribe(this, this);
  }

  void setProviders(CaptureProvider provider) {
    captureProvider = provider;
    notifyListeners();
  }

  void setConnectedDevice(BtDevice? device) {
    connectedDevice = device;
    print('setConnectedDevice: $device');
    notifyListeners();
  }

  Future<BtDeviceInfo> getDeviceInfo() async {
    if (connectedDevice == null) {
      if (SharedPreferencesUtil().btDevice.id.isEmpty) {
        return BtDeviceInfo('Unknown', 'Unknown', 'Unknown', 'Unknown', DeviceType.friend);
      } else {
        deviceInfo = SharedPreferencesUtil().btDevice.info!;
        return deviceInfo!;
      }
    } else {
      var connection = await ServiceManager.instance().device.ensureConnection(connectedDevice!.id);
      if (connection == null) {
        return connectedDevice!.getDeviceInfo(null);
      }
      deviceInfo = await connectedDevice!.getDeviceInfo(connection);
      notifyListeners();
      return deviceInfo!;
    }
  }

  // TODO: thinh, use connection directly
  Future<StreamSubscription<List<int>>?> _getBleBatteryLevelListener(
    String deviceId, {
    void Function(int)? onBatteryLevelChange,
  }) async {
    {
      var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection == null) {
        return Future.value(null);
      }
      return connection.getBleBatteryLevelListener(onBatteryLevelChange: onBatteryLevelChange);
    }
  }

  Future<BtDevice?> _getConnectedDevice() async {
    var deviceId = SharedPreferencesUtil().btDevice.id;
    if (deviceId.isEmpty) {
      return null;
    }
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.device;
  }

  initiateBleBatteryListener() async {
    if (_bleBatteryLevelListener != null) return;
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = await _getBleBatteryLevelListener(
      connectedDevice!.id,
      onBatteryLevelChange: (int value) {
        batteryLevel = value;
      },
    );
    notifyListeners();
  }

  Future periodicConnect(String printer) async {
    debugPrint("period connect");
    _reconnectionTimer?.cancel();
    _reconnectionTimer = Timer.periodic(Duration(seconds: connectionCheckSeconds), (t) async {
      debugPrint("period connect...");
      print(printer);
      print('seconds: $connectionCheckSeconds');
      print('triggered timer at ${DateTime.now()}');

      if (SharedPreferencesUtil().btDevice.id.isEmpty) {
        return;
      }
      print("isConnected: $isConnected, isConnecting: $isConnecting, connectedDevice: $connectedDevice");
      if ((!isConnected && connectedDevice == null)) {
        if (isConnecting) {
          return;
        }
        await scanAndConnectToDevice();
      } else {
        t.cancel();
      }
    });
  }

  Future<BtDevice?> _scanAndConnectDevice({bool autoConnect = true, bool timeout = false}) async {
    var device = await _getConnectedDevice();
    if (device != null) {
      return device;
    }

    int timeoutCounter = 0;
    while (true) {
      if (timeout && timeoutCounter >= 10) return null;
      await ServiceManager.instance().device.discover();
      if (connectedDevice != null) {
        return connectedDevice;
      }

      // If the device is not found, wait for a bit before retrying.
      await Future.delayed(const Duration(seconds: 2));
      timeoutCounter += 2;
    }
  }

  Future scanAndConnectToDevice() async {
    updateConnectingStatus(true);
    if (isConnected) {
      if (connectedDevice == null) {
        connectedDevice = await _getConnectedDevice();
        SharedPreferencesUtil().btDevice = connectedDevice!;
        SharedPreferencesUtil().deviceName = connectedDevice!.name;
        MixpanelManager().deviceConnected();
      }

      setIsConnected(true);
      updateConnectingStatus(false);
    } else {
      var device = await _scanAndConnectDevice();
      print('inside scanAndConnectToDevice $device in device_provider');
      if (device != null) {
        var cDevice = await _getConnectedDevice();
        if (cDevice != null) {
          setConnectedDevice(cDevice);
          SharedPreferencesUtil().btDevice = cDevice;
          SharedPreferencesUtil().deviceName = cDevice.name;
          MixpanelManager().deviceConnected();
          setIsConnected(true);
        }
        print('device is not null $cDevice');
      }
      updateConnectingStatus(false);
    }
    if (isConnected) {
      await initiateBleBatteryListener();
    }

    notifyListeners();
  }

  void updateConnectingStatus(bool value) {
    isConnecting = value;
    notifyListeners();
  }

  void setIsConnected(bool value) {
    isConnected = value;
    if (isConnected) {
      connectionCheckSeconds = 8;
      _reconnectionTimer?.cancel();
    } else {
      connectionCheckSeconds = 4;
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBatteryLevelListener?.cancel();
    _reconnectionTimer?.cancel();
    ServiceManager.instance().device.unsubscribe(this);
    super.dispose();
  }

  void onDeviceDisconnected() async {
    debugPrint('onDisconnected inside: $connectedDevice');
    setConnectedDevice(null);
    setIsConnected(false);
    updateConnectingStatus(false);
    await captureProvider?.stopStreamDeviceRecording(cleanDevice: true);
    captureProvider?.setAudioBytesConnected(false);
    print('after resetState inside initiateConnectionListener');

    InstabugLog.logInfo('Friend Device Disconnected');
    _disconnectNotificationTimer?.cancel();
    _disconnectNotificationTimer = Timer(const Duration(seconds: 30), () {
      NotificationService.instance.createNotification(
        title: 'Friend Device Disconnected',
        body: 'Please reconnect to continue using your Friend.',
      );
    });
    MixpanelManager().deviceDisconnected();

    // Retired 1s to prevent the race condition made by standby power of ble device
    Future.delayed(const Duration(seconds: 1), () {
      periodicConnect('coming from onDisconnect');
    });
  }

  void onDeviceReconnected(BtDevice device) async {
    debugPrint('_onConnected inside: $connectedDevice');
    _disconnectNotificationTimer?.cancel();
    NotificationService.instance.clearNotification(1);
    setConnectedDevice(device);
    setIsConnected(true);
    updateConnectingStatus(false);
    await captureProvider?.streamDeviceRecording(restartBytesProcessing: true, device: device);
    //  initiateBleBatteryListener();
    // The device is still disconnected for some reason
    if (connectedDevice != null) {
      MixpanelManager().deviceConnected();
      await getDeviceInfo();
      SharedPreferencesUtil().btDevice = connectedDevice!;
      SharedPreferencesUtil().deviceName = connectedDevice!.name;
    }
    notifyListeners();
  }

  @override
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) async {
    debugPrint("provider > device connection state changed...${deviceId}...${state}...${connectedDevice?.id}");
    switch (state) {
      case DeviceConnectionState.connected:
        var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
        if (connection == null) {
          return;
        }
        onDeviceReconnected(connection.device);
        break;
      case DeviceConnectionState.disconnected:
        if (deviceId == connectedDevice?.id) {
          onDeviceDisconnected();
        }
      default:
        debugPrint("Device connection state is not supported $state");
    }
  }

  @override
  void onDevices(List<BtDevice> devices) async {
    if (connectedDevice != null) {
      return;
    }

    if (devices.length <= 0) {
      return;
    }

    // Connect to first founded device
    var force = devices.first.id == SharedPreferencesUtil().btDevice.id;
    var connection = await ServiceManager.instance().device.ensureConnection(devices.first.id, force: force);
    if (connection == null) {
      return;
    }
    connectedDevice = connection.device;
  }

  @override
  void onStatusChanged(DeviceServiceStatus status) {
    // TODO: implement onStatusChanged
  }
}
