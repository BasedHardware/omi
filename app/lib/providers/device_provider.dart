import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/page.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/services/notification_service.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/ble/connected.dart';
import 'package:friend_private/utils/ble/scan.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:permission_handler/permission_handler.dart';

class DeviceProvider extends ChangeNotifier {
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
    notifyListeners();
  }

  Future initiateConnectionListener(GlobalKey<CapturePageState> capturePageKey) async {
    print('initiateConnectionListener called');
    if (statusSubscription != null) return;
    statusSubscription?.cancel();
    statusSubscription = getConnectionStateListener(
      deviceId: connectedDevice!.id,
      onDisconnected: () {
        debugPrint('onDisconnected inside: $connectedDevice');
        // capturePageKey.currentState?.resetState(restartBytesProcessing: false);
        setConnectedDevice(null);
        setIsConnected(false);
        captureProvider?.resetState(restartBytesProcessing: false, captureKey: capturePageKey);
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
        print('before resetState');
        // capturePageKey.currentState?.resetState(restartBytesProcessing: true, btDevice: connectedDevice);
        captureProvider?.resetState(
            restartBytesProcessing: true, btDevice: connectedDevice, captureKey: capturePageKey);
        print('after resetState');
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
        print('Battery Level: $value');
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

  Future periodicConnect(GlobalKey<CapturePageState> capturePageKey) async {
    timer = Timer.periodic(Duration(seconds: connectionCheckSeconds), (timer) async {
      // print('seconds: $connectionCheckSeconds');
      // print('triggered timer at ${DateTime.now()}');
      if (SharedPreferencesUtil().btDeviceStruct.id.isEmpty) {
        return;
      }
      if (!isConnected && !isConnecting) {
        print('Not connected and not connecting');
        await scanAndConnectToDevice(capturePageKey);
      }
    });
  }

  Future scanAndConnectToDevice(GlobalKey<CapturePageState> capturePageKey) async {
    print('Scanning and connecting to device');
    updateConnectingStatus(true);
    if (isConnected) {
      print('Already connected');
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
      print('Device connecting to: $device');
      if (device != null) {
        var cDevice = await getConnectedDevice();
        if (cDevice != null) {
          setConnectedDevice(device);
          SharedPreferencesUtil().btDeviceStruct = device;
          SharedPreferencesUtil().deviceName = device.name;
          MixpanelManager().deviceConnected();
          setIsConnected(true);
        }
      }
      updateConnectingStatus(false);
    }
    captureProvider?.resetState(restartBytesProcessing: true, btDevice: connectedDevice, captureKey: capturePageKey);
    if (statusSubscription == null) {
      await initiateConnectionListener(capturePageKey);
    }
    if (isConnected) {
      await initiateBleBatteryListener();
    }
    if (captureProvider?.webSocketConnected == false) {
      capturePageKey.currentState?.restartWebSocket();
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
