import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/http/api/device.dart';
import 'package:friend_private/main.dart';
import 'package:friend_private/pages/home/firmware_update.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/device.dart';
import 'package:friend_private/widgets/confirmation_dialog.dart';
import 'package:instabug_flutter/instabug_flutter.dart';

class DeviceProvider extends ChangeNotifier implements IDeviceServiceSubsciption {
  CaptureProvider? captureProvider;

  bool isConnecting = false;
  bool isConnected = false;
  bool isDeviceV2Connected = false;
  BtDevice? connectedDevice;
  BtDevice? pairedDevice;
  StreamSubscription<List<int>>? _bleBatteryLevelListener;
  int batteryLevel = -1;
  bool _hasLowBatteryAlerted = false;
  Timer? _reconnectionTimer;
  int connectionCheckSeconds = 4;

  bool _havingNewFirmware = false;
  bool get havingNewFirmware => _havingNewFirmware && pairedDevice != null && isConnected;

  // Current and latest firmware versions for UI display
  String get currentFirmwareVersion => pairedDevice?.firmwareRevision ?? 'Unknown';
  String _latestFirmwareVersion = '';
  String get latestFirmwareVersion => _latestFirmwareVersion;

  Timer? _disconnectNotificationTimer;

  DeviceProvider() {
    ServiceManager.instance().device.subscribe(this, this);
  }

  void setProviders(CaptureProvider provider) {
    captureProvider = provider;
    notifyListeners();
  }

  void setConnectedDevice(BtDevice? device) async {
    connectedDevice = device;
    pairedDevice = device;
    await getDeviceInfo();
    print('setConnectedDevice: $device');
    notifyListeners();
  }

  Future getDeviceInfo() async {
    if (connectedDevice != null) {
      if (pairedDevice?.firmwareRevision != null && pairedDevice?.firmwareRevision != 'Unknown') {
        return;
      }
      var connection = await ServiceManager.instance().device.ensureConnection(connectedDevice!.id);
      pairedDevice = await connectedDevice!.getDeviceInfo(connection);
      SharedPreferencesUtil().btDevice = pairedDevice!;
    } else {
      if (SharedPreferencesUtil().btDevice.id.isEmpty) {
        pairedDevice = BtDevice.empty();
      } else {
        pairedDevice = SharedPreferencesUtil().btDevice;
      }
    }
    notifyListeners();
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

  Future<List<int>> _getStorageList(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageList();
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
    if (connectedDevice == null) {
      return;
    }
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = await _getBleBatteryLevelListener(
      connectedDevice!.id,
      onBatteryLevelChange: (int value) {
        batteryLevel = value;
        if (batteryLevel < 20 && !_hasLowBatteryAlerted) {
          _hasLowBatteryAlerted = true;
          NotificationService.instance.createNotification(
            title: "Low Battery Alert",
            body: "Your device is running low on battery. Time for a recharge! 🔋",
          );
        } else if (batteryLevel > 20) {
          _hasLowBatteryAlerted = true;
        }
        notifyListeners();
      },
    );
    notifyListeners();
  }

  Future periodicConnect(String printer) async {
    debugPrint("period connect");
    _reconnectionTimer?.cancel();
    _reconnectionTimer = Timer.periodic(Duration(seconds: connectionCheckSeconds), (t) async {
      debugPrint("period connect...");
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
      await ServiceManager.instance().device.discover(desirableDeviceId: SharedPreferencesUtil().btDevice.id);
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
        // SharedPreferencesUtil().btDevice = connectedDevice!;
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
          setIsDeviceV2Connected();
          // SharedPreferencesUtil().btDevice = cDevice;
          SharedPreferencesUtil().deviceName = cDevice.name;
          MixpanelManager().deviceConnected();
          setIsConnected(true);
        }
        print('device is not null $cDevice');
      }
      updateConnectingStatus(false);
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
    _havingNewFirmware = false;
    setConnectedDevice(null);
    setIsDeviceV2Connected();
    setIsConnected(false);
    updateConnectingStatus(false);

    captureProvider?.updateRecordingDevice(null);

    // Wals
    ServiceManager.instance().wal.getSyncs().sdcard.setDevice(null);

    print('after resetState inside initiateConnectionListener');

    InstabugLog.logInfo('Omi Device Disconnected');
    _disconnectNotificationTimer?.cancel();
    _disconnectNotificationTimer = Timer(const Duration(seconds: 30), () {
      NotificationService.instance.createNotification(
        title: 'Your Omi Device Disconnected',
        body: 'Please reconnect to continue using your Omi.',
      );
    });
    MixpanelManager().deviceDisconnected();

    // Retired 1s to prevent the race condition made by standby power of ble device
    Future.delayed(const Duration(seconds: 1), () {
      periodicConnect('coming from onDisconnect');
    });
  }

  Future<(String, bool, String)> shouldUpdateFirmware() async {
    if (pairedDevice == null || connectedDevice == null) {
      return ('No paired device is connected', false, '');
    }

    var device = pairedDevice!;
    var latestFirmwareDetails = await getLatestFirmwareVersion(
      deviceModelNumber: device.modelNumber,
      firmwareRevision: device.firmwareRevision,
      hardwareRevision: device.hardwareRevision,
      manufacturerName: device.manufacturerName,
    );

    return await DeviceUtils.shouldUpdateFirmware(
        currentFirmware: device.firmwareRevision, latestFirmwareDetails: latestFirmwareDetails);
  }

  void _onDeviceConnected(BtDevice device) async {
    debugPrint('_onConnected inside: $connectedDevice');
    _disconnectNotificationTimer?.cancel();
    NotificationService.instance.clearNotification(1);
    setConnectedDevice(device);

    setIsDeviceV2Connected();
    setIsConnected(true);
    await initiateBleBatteryListener();
    if (batteryLevel != -1 && batteryLevel < 20) {
      _hasLowBatteryAlerted = false;
    }
    updateConnectingStatus(false);
    await captureProvider?.streamDeviceRecording(device: device);

    await getDeviceInfo();
    SharedPreferencesUtil().deviceName = device.name;

    // Wals
    ServiceManager.instance().wal.getSyncs().sdcard.setDevice(device);

    notifyListeners();

    // Check firmware updates
    _checkFirmwareUpdates();
  }

  void _checkFirmwareUpdates() async {
    await checkFirmwareUpdates();

    // Show firmware update dialog if needed
    if (_havingNewFirmware) {
      // Use a small delay to ensure the UI is ready
      Future.delayed(const Duration(milliseconds: 500), () {
        final context = MyApp.navigatorKey.currentContext;
        if (context != null) {
          showFirmwareUpdateDialog(context);
        }
      });
    }
  }

  Future checkFirmwareUpdates() async {
    int retryCount = 0;
    const maxRetries = 3;
    const retryDelay = Duration(seconds: 3);

    while (retryCount < maxRetries) {
      try {
        var (message, hasUpdate, version) = await shouldUpdateFirmware();
        _havingNewFirmware = hasUpdate;
        _latestFirmwareVersion = version.isNotEmpty ? version : message;
        notifyListeners();
        return hasUpdate; // Return whether there's an update
      } catch (e) {
        retryCount++;
        debugPrint('Error checking firmware update (attempt $retryCount): $e');

        if (retryCount == maxRetries) {
          debugPrint('Max retries reached, giving up');
          _havingNewFirmware = false;
          notifyListeners();
          break;
        }

        await Future.delayed(retryDelay);
      }
    }
    return;
  }

  void showFirmwareUpdateDialog(BuildContext context) {
    if (!_havingNewFirmware || !SharedPreferencesUtil().showFirmwareUpdateDialog) {
      return;
    }

    bool dontShowAgain = false;

    showDialog(
      context: context,
      builder: (context) => ConfirmationDialog(
        title: 'Firmware Update Available',
        description:
            'A new firmware update (${_latestFirmwareVersion}) is available for your Omi device. Would you like to update now?',
        checkboxText: "Don't show me again",
        checkboxValue: dontShowAgain,
        onCheckboxChanged: (value) {
          dontShowAgain = value ?? false;
        },
        confirmText: 'Update',
        cancelText: 'Later',
        onConfirm: () {
          if (dontShowAgain) {
            SharedPreferencesUtil().showFirmwareUpdateDialog = false;
          }
          Navigator.of(context).pop();
          // Navigate to firmware update page
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (context) => FirmwareUpdate(device: pairedDevice),
            ),
          );
        },
        onCancel: () {
          if (dontShowAgain) {
            SharedPreferencesUtil().showFirmwareUpdateDialog = false;
          }
          Navigator.of(context).pop();
        },
      ),
    );
  }

  Future setIsDeviceV2Connected() async {
    if (connectedDevice == null) {
      isDeviceV2Connected = false;
    } else {
      var storageFiles = await _getStorageList(connectedDevice!.id);
      isDeviceV2Connected = storageFiles.isNotEmpty;
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
        _onDeviceConnected(connection.device);
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
  void onDevices(List<BtDevice> devices) async {}

  @override
  void onStatusChanged(DeviceServiceStatus status) {}
}
