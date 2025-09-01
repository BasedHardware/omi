import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/http/api/device.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/confirmation_dialog.dart';

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
  DateTime? _reconnectAt;
  final int _connectionCheckSeconds = 15; // 10s periods, 5s for each scan

  bool _havingNewFirmware = false;
  bool get havingNewFirmware => _havingNewFirmware && pairedDevice != null && isConnected;

  // Track firmware update state to prevent showing dialog during updates
  bool _isFirmwareUpdateInProgress = false;
  bool get isFirmwareUpdateInProgress => _isFirmwareUpdateInProgress;

  // Current and latest firmware versions for UI display
  String get currentFirmwareVersion => pairedDevice?.firmwareRevision ?? 'Unknown';
  String _latestFirmwareVersion = '';
  String get latestFirmwareVersion => _latestFirmwareVersion;

  Timer? _disconnectNotificationTimer;
  final Debouncer _disconnectDebouncer = Debouncer(delay: const Duration(milliseconds: 500));
  final Debouncer _connectDebouncer = Debouncer(delay: const Duration(milliseconds: 100));

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
    Logger.debug('setConnectedDevice: $device');
    notifyListeners();
  }

  Future getDeviceInfo() async {
    if (connectedDevice != null) {
      if (pairedDevice?.firmwareRevision != null && pairedDevice?.firmwareRevision != 'Unknown') {
        return;
      }
      var connection = await ServiceManager.instance().device.ensureConnection(connectedDevice!.id);
      pairedDevice = await connectedDevice?.getDeviceInfo(connection);
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
  Future _bleDisconnectDevice(BtDevice btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    return await connection.disconnect();
  }

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
    _reconnectionTimer?.cancel();
    scan(t) async {
      debugPrint("Period connect seconds: $_connectionCheckSeconds, triggered timer at ${DateTime.now()}");
      if (_reconnectAt != null && _reconnectAt!.isAfter(DateTime.now())) {
        return;
      }
      Logger.debug("isConnected: $isConnected, isConnecting: $isConnecting, connectedDevice: $connectedDevice");
      if ((!isConnected && connectedDevice == null)) {
        if (isConnecting) {
          return;
        }
        await scanAndConnectToDevice();
      } else {
        t.cancel();
      }
    }

    _reconnectionTimer = Timer.periodic(Duration(seconds: _connectionCheckSeconds), scan);
    scan(_reconnectionTimer);
  }

  Future<BtDevice?> _scanConnectDevice() async {
    var device = await _getConnectedDevice();
    if (device != null) {
      return device;
    }

    await ServiceManager.instance().device.discover(desirableDeviceId: SharedPreferencesUtil().btDevice.id);

    // Waiting for the device connected (if any)
    await Future.delayed(const Duration(seconds: 2));
    if (connectedDevice != null) {
      return connectedDevice;
    }
    return null;
  }

  Future scanAndConnectToDevice() async {
    updateConnectingStatus(true);
    if (isConnected) {
      if (connectedDevice == null) {
        connectedDevice = await _getConnectedDevice();
        SharedPreferencesUtil().deviceName = connectedDevice!.name;
        MixpanelManager().deviceConnected();
      }

      setIsConnected(true);
      updateConnectingStatus(false);
      notifyListeners();
      return;
    }

    // else
    var device = await _scanConnectDevice();
    Logger.debug('inside scanAndConnectToDevice $device in device_provider');
    if (device != null) {
      var cDevice = await _getConnectedDevice();
      if (cDevice != null) {
        setConnectedDevice(cDevice);
        setIsDeviceV2Connected();
        SharedPreferencesUtil().deviceName = cDevice.name;
        MixpanelManager().deviceConnected();
        setIsConnected(true);
      }
      Logger.debug('device is not null $cDevice');
    }
    updateConnectingStatus(false);

    notifyListeners();
  }

  void updateConnectingStatus(bool value) {
    isConnecting = value;
    notifyListeners();
  }

  void setIsConnected(bool value) {
    isConnected = value;
    if (isConnected) {
      _reconnectionTimer?.cancel();
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBatteryLevelListener?.cancel();
    _reconnectionTimer?.cancel();
    _disconnectDebouncer.cancel();
    _connectDebouncer.cancel();
    ServiceManager.instance().device.unsubscribe(this);
    super.dispose();
  }

  void onDeviceDisconnected() async {
    Logger.debug('onDisconnected inside: $connectedDevice');
    _havingNewFirmware = false;
    setConnectedDevice(null);
    setIsDeviceV2Connected();
    setIsConnected(false);
    updateConnectingStatus(false);

    captureProvider?.updateRecordingDevice(null);

    // Wals
    ServiceManager.instance().wal.getSyncs().sdcard.setDevice(null);

    PlatformManager.instance.crashReporter.logInfo('Omi Device Disconnected');
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
    Logger.debug('_onConnected inside: $connectedDevice');
    _disconnectNotificationTimer?.cancel();
    NotificationService.instance.clearNotification(1);
    setConnectedDevice(device);

    if (captureProvider != null) {
      captureProvider?.updateRecordingDevice(device);
    }

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

  void _handleDeviceConnected(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return;
    }
    _onDeviceConnected(connection.device);
  }

  void _checkFirmwareUpdates() async {
    if (_isFirmwareUpdateInProgress) {
      return;
    }

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
        Logger.debug('Error checking firmware update (attempt $retryCount): $e');

        if (retryCount == maxRetries) {
          Logger.debug('Max retries reached, giving up');
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
    if (!_havingNewFirmware || !SharedPreferencesUtil().showFirmwareUpdateDialog || _isFirmwareUpdateInProgress) {
      return;
    }

    showDialog(
      context: context,
      builder: (context) => ConfirmationDialog(
        title: 'Firmware Update Available',
        description:
            'A new firmware update ($_latestFirmwareVersion) is available for your Omi device. Would you like to update now?',
        confirmText: 'Update',
        cancelText: 'Later',
        onConfirm: () {
          Navigator.of(context).pop();
          setFirmwareUpdateInProgress(true);
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (context) => FirmwareUpdate(device: pairedDevice),
            ),
          );
        },
        onCancel: () {
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
    Logger.debug("provider > device connection state changed...$deviceId...$state...${connectedDevice?.id}");
    switch (state) {
      case DeviceConnectionState.connected:
        _disconnectDebouncer.cancel();
        _connectDebouncer.run(() => _handleDeviceConnected(deviceId));
        break;
      case DeviceConnectionState.disconnected:
        _connectDebouncer.cancel();
        if (deviceId == connectedDevice?.id) {
          _disconnectDebouncer.run(onDeviceDisconnected);
        }
        break;
      default:
        Logger.debug("Device connection state is not supported $state");
    }
  }

  @override
  void onDevices(List<BtDevice> devices) async {}

  @override
  void onStatusChanged(DeviceServiceStatus status) {}

  prepareDFU() {
    if (connectedDevice == null) {
      return;
    }
    _bleDisconnectDevice(connectedDevice!);
    _reconnectAt = DateTime.now().add(Duration(seconds: 30));
  }

  // Reset firmware update state when update completes or fails
  void resetFirmwareUpdateState() {
    _isFirmwareUpdateInProgress = false;
    notifyListeners();
  }

  // Set firmware update state when starting an update
  void setFirmwareUpdateInProgress(bool inProgress) {
    _isFirmwareUpdateInProgress = inProgress;
    notifyListeners();
  }
}
