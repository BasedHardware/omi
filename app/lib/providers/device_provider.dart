import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/logic/websocket_mixin.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/services/notification_service.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:permission_handler/permission_handler.dart';

class DeviceProvider extends ChangeNotifier with WebSocketMixin {
  CaptureProvider? captureProvider;

  bool isConnecting = false;
  bool isConnected = false;
  BTDeviceStruct? connectedDevice;
  StreamSubscription? statusSubscription;
  StreamSubscription<List<int>>? _bleBatteryLevelListener;
  int batteryLevel = -1;
  var timer;
  int connectionCheckSeconds = 4;

  Timer? _disconnectNotificationTimer;

  void setProvider(CaptureProvider provider) {
    captureProvider = provider;
    notifyListeners();
  }

  void setConnectedDevice(BTDeviceStruct? device) {
    connectedDevice = device;
    captureProvider?.updateConnectedDevice(device);
    notifyListeners();
  }

  Future initiateConnectionListener() async {
    print('initiateConnectionListener called');
    if (statusSubscription != null) return;
    if (connectedDevice == null) {
      connectedDevice = await getConnectedDevice();
      SharedPreferencesUtil().btDeviceStruct = connectedDevice!;
      SharedPreferencesUtil().deviceName = connectedDevice!.name;
      MixpanelManager().deviceConnected();
      if (connectedDevice == null) {
        print('connectedDevice is null, unable to connect as well');
        return;
      }
    }
    statusSubscription?.cancel();
    statusSubscription = getConnectionStateListener(
      deviceId: connectedDevice!.id,
      onDisconnected: () async {
        debugPrint('onDisconnected inside: $connectedDevice');
        setConnectedDevice(null);
        setIsConnected(false);
        updateConnectingStatus(false);
        periodicConnect('coming from onDisconnect');
        captureProvider?.resetState(restartBytesProcessing: false);
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
      },
      onConnected: ((device) {
        debugPrint('_onConnected inside: $connectedDevice');
        _disconnectNotificationTimer?.cancel();
        NotificationService.instance.clearNotification(1);
        setConnectedDevice(device);
        setIsConnected(true);
        updateConnectingStatus(false);
        captureProvider?.resetState(restartBytesProcessing: true, btDevice: connectedDevice);
        //  initiateBleBatteryListener();
        MixpanelManager().deviceConnected();
        SharedPreferencesUtil().btDeviceStruct = connectedDevice!;
        SharedPreferencesUtil().deviceName = connectedDevice!.name;
        notifyListeners();
      }),
    );
    notifyListeners();
  }

  initiateBleBatteryListener() async {
    if (_bleBatteryLevelListener != null) return;
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = await getBleBatteryLevelListener(
      connectedDevice!.id,
      onBatteryLevelChange: (int value) {
        batteryLevel = value;
      },
    );
    notifyListeners();
  }

  Future askForPermissions() async {
    if (Platform.isIOS) {
      final granted = await Permission.bluetooth.isGranted;
      if (granted) {
        return true;
      }
      PermissionStatus bleStatus = await Permission.bluetooth.request();
      debugPrint('bleStatus: $bleStatus');
      return bleStatus.isGranted;
    } else {
      PermissionStatus bleScanStatus = await Permission.bluetoothScan.request();
      PermissionStatus bleConnectStatus = await Permission.bluetoothConnect.request();
      // PermissionStatus locationStatus = await Permission.location.request();

      return bleConnectStatus.isGranted && bleScanStatus.isGranted; // && locationStatus.isGranted;
    }
  }

  Future periodicConnect(String printer) async {
    if (timer != null) return;
    timer = Timer.periodic(Duration(seconds: connectionCheckSeconds), (t) async {
      if (timer == null) return;
      // print(printer);
      // print('seconds: $connectionCheckSeconds');
      // print('triggered timer at ${DateTime.now()}');

      if (SharedPreferencesUtil().btDeviceStruct.id.isEmpty) {
        return;
      }
      // print("isConnected: $isConnected, isConnecting: $isConnecting, connectedDevice: $connectedDevice");
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

  Future scanAndConnectToDevice() async {
    updateConnectingStatus(true);
    if (isConnected) {
      if (connectedDevice == null) {
        connectedDevice = await getConnectedDevice();
        SharedPreferencesUtil().btDeviceStruct = connectedDevice!;
        SharedPreferencesUtil().deviceName = connectedDevice!.name;
        MixpanelManager().deviceConnected();
      }

      setIsConnected(true);
      updateConnectingStatus(false);
    } else {
      var device = await scanAndConnectDevice();
      if (device != null) {
        var cDevice = await getConnectedDevice();
        if (cDevice != null) {
          setConnectedDevice(cDevice);
          SharedPreferencesUtil().btDeviceStruct = cDevice;
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
    captureProvider?.resetState(restartBytesProcessing: true, btDevice: connectedDevice);
    // if (captureProvider?.webSocketConnected == false) {
    //   restartWebSocket();
    // }
    if (statusSubscription == null) {
      await initiateConnectionListener();
    }

    notifyListeners();
  }

  void restartWebSocket() {
    debugPrint('restartWebSocket');

    closeWebSocket();
    if (connectedDevice == null) {
      return;
    }
    captureProvider?.resetState(restartBytesProcessing: true);
    captureProvider?.streamAudioToWs(connectedDevice!.id, SharedPreferencesUtil().deviceCodec);
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
      timer?.cancel();
    } else {
      connectionCheckSeconds = 4;
    }
    notifyListeners();
  }

  @override
  void dispose() {
    statusSubscription?.cancel();
    _bleBatteryLevelListener?.cancel();
    timer?.cancel();
    super.dispose();
  }
}
