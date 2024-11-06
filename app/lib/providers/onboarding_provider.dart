import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/providers/device_provider.dart';
import 'package:friend_private/services/devices.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/analytics/analytics_manager.dart';
import 'package:friend_private/utils/audio/foreground.dart';
import 'package:permission_handler/permission_handler.dart';

class OnboardingProvider extends BaseProvider with MessageNotifierMixin implements IDeviceServiceSubsciption {
  DeviceProvider? deviceProvider;
  bool isClicked = false;
  bool isConnected = false;
  int batteryPercentage = -1;
  String deviceName = '';
  String deviceId = '';
  String? connectingToDeviceId;
  List<BtDevice> deviceList = [];
  late Timer _didNotMakeItTimer;
  Timer? _findDevicesTimer;
  bool enableInstructions = false;
  Map<String, BtDevice> foundDevicesMap = {};

  //----------------- Onboarding Permissions -----------------
  bool hasBluetoothPermission = false;
  bool hasLocationPermission = false;
  bool hasNotificationPermission = false;
  bool hasBackgroundPermission = false; // Android only
  bool isLoading = false;

  Future updatePermissions() async {
    hasBluetoothPermission = await Permission.bluetooth.isGranted;
    hasLocationPermission = await Permission.location.isGranted;
    hasNotificationPermission = await Permission.notification.isGranted;
    SharedPreferencesUtil().notificationsEnabled = hasNotificationPermission;
    SharedPreferencesUtil().locationEnabled = hasLocationPermission;
    notifyListeners();
  }

  void setLoading(bool value) {
    isLoading = value;
    notifyListeners();
  }

  void updateBluetoothPermission(bool value) {
    hasBluetoothPermission = value;
    notifyListeners();
  }

  void updateLocationPermission(bool value) {
    hasLocationPermission = value;
    SharedPreferencesUtil().locationEnabled = value;
    AnalyticsManager().setUserAttribute('Location Enabled', SharedPreferencesUtil().locationEnabled);
    notifyListeners();
  }

  void updateNotificationPermission(bool value) {
    hasNotificationPermission = value;
    SharedPreferencesUtil().notificationsEnabled = value;
    AnalyticsManager().setUserAttribute('Notifications Enabled', SharedPreferencesUtil().notificationsEnabled);
    notifyListeners();
  }

  void updateBackgroundPermission(bool value) {
    hasBackgroundPermission = value;
    AnalyticsManager().setUserAttribute('Background Permission Enabled', hasBackgroundPermission);
    notifyListeners();
  }

  Future askForBluetoothPermissions() async {
    FlutterBluePlus.setLogLevel(LogLevel.info, color: true);
    if (Platform.isIOS) {
      PermissionStatus bleStatus = await Permission.bluetooth.request();
      debugPrint('bleStatus: $bleStatus');
      updateBluetoothPermission(bleStatus.isGranted);
    } else {
      if (Platform.isAndroid) {
        if (FlutterBluePlus.adapterStateNow != BluetoothAdapterState.on) {
          try {
            await FlutterBluePlus.turnOn();
          } catch (e) {
            if (e is FlutterBluePlusException) {
              if (e.code == 11) {
                //  onShowDialog();
              }
            }
          }
        }
      }
      PermissionStatus bleScanStatus = await Permission.bluetoothScan.request();
      PermissionStatus bleConnectStatus = await Permission.bluetoothConnect.request();
      // PermissionStatus locationStatus = await Permission.location.request();
      updateBluetoothPermission(bleConnectStatus.isGranted && bleScanStatus.isGranted);
    }
    notifyListeners();
  }

  Future askForNotificationPermissions() async {
    var isAllowed = await NotificationService.instance.requestNotificationPermissions();
    updateNotificationPermission(isAllowed);
    notifyListeners();
  }

  Future askForBackgroundPermissions() async {
    await FlutterForegroundTask.requestIgnoreBatteryOptimization();
    var isAllowed = await ForegroundUtil().isIgnoringBatteryOptimizations;
    updateBackgroundPermission(isAllowed);
    notifyListeners();
  }

  Future<(bool, PermissionStatus)> askForLocationPermissions() async {
    if (await Permission.location.serviceStatus.isDisabled) {
      debugPrint('Location service is disabled');
      return (false, PermissionStatus.permanentlyDenied);
    } else {
      var res = await Permission.locationWhenInUse.request();
      return (true, res);
    }
  }

  Future<bool> alwaysAllowLocation() async {
    PermissionStatus locationStatus = await Permission.locationAlways.request();
    debugPrint('alwaysAllowLocation permission status: $locationStatus');
    updateLocationPermission(locationStatus.isGranted);
    return locationStatus.isGranted;
  }
  //----------------- Onboarding Permissions -----------------

  void setDeviceProvider(DeviceProvider provider) {
    deviceProvider = provider;
  }

  // Method to handle taps on devices
  Future<void> handleTap({
    required BtDevice device,
    required bool isFromOnboarding,
    VoidCallback? goNext,
  }) async {
    if (device.name.toLowerCase() == 'openglass' || device.type == DeviceType.openglass) {
      notifyInfo('OPENGLASS_NOT_SUPPORTED');
      return;
    }
    try {
      if (isClicked) return; // if any item is clicked, don't do anything
      isClicked = true; // Prevent further clicks
      connectingToDeviceId = device.id; // Mark this device as being connected to
      notifyListeners();
      var c = await ServiceManager.instance().device.ensureConnection(device.id, force: true);
      debugPrint('Connected to device: ${device.name}');
      deviceId = device.id;
      //  device = await device.getDeviceInfo(c);
      await SharedPreferencesUtil().btDeviceSet(device);
      deviceName = device.name;
      var cDevice = await _getConnectedDevice(deviceId);
      if (cDevice != null) {
        deviceProvider!.setConnectedDevice(cDevice);
        // SharedPreferencesUtil().btDevice = cDevice;
        SharedPreferencesUtil().deviceName = cDevice.name;
        deviceProvider!.setIsConnected(true);
      }
      await deviceProvider?.scanAndConnectToDevice();
      var connectedDevice = deviceProvider!.connectedDevice;
      batteryPercentage = deviceProvider!.batteryLevel;
      isConnected = true;
      isClicked = false; // Allow clicks again after finishing the operation
      connectingToDeviceId = null; // Reset the connecting device
      notifyListeners();
      stopScanDevices();
      await Future.delayed(const Duration(seconds: 2));
      SharedPreferencesUtil().btDevice = connectedDevice!;
      SharedPreferencesUtil().deviceName = connectedDevice.name;
      foundDevicesMap.clear();
      deviceList.clear();
      if (isFromOnboarding) {
        goNext!();
      } else {
        notifyInfo('DEVICE_CONNECTED');
      }
    } catch (e) {
      debugPrint('Error connecting to device: $e');
      foundDevicesMap.remove(device.id);
      deviceList.removeWhere((element) => element.id == device.id);
      isClicked = false; // Allow clicks again after finishing the operation
      connectingToDeviceId = null; // Reset the connecting device
      deviceProvider!.setIsConnected(false);
      notifyListeners();
    }

    notifyListeners();
  }

  void deviceAlreadyUnpaired() {
    batteryPercentage = -1;
    isConnected = false;
    deviceName = '';
    deviceId = '';
    notifyListeners();
  }

  void stopScanDevices() {
    _findDevicesTimer?.cancel();
  }

  Future<void> scanDevices({
    required VoidCallback onShowDialog,
  }) async {
    if (SharedPreferencesUtil().btDevice.id.isEmpty) {
      // it means the device has been unpaired
      deviceAlreadyUnpaired();
    }
    // check if bluetooth is enabled on both platforms
    if (!hasBluetoothPermission) {
      await askForBluetoothPermissions();
      if (!hasBluetoothPermission) {
        onShowDialog();
      }
    }

    _didNotMakeItTimer = Timer(const Duration(seconds: 10), () {
      enableInstructions = true;
      notifyListeners();
    });

    ServiceManager.instance().device.subscribe(this, this);

    _findDevicesTimer?.cancel();
    _findDevicesTimer = Timer.periodic(const Duration(seconds: 4), (t) async {
      if (deviceProvider?.isConnected ?? false) {
        t.cancel();
        return;
      }

      ServiceManager.instance().device.discover();
    });
  }

  // TODO: thinh, use connection directly
  Future<BtDevice?> _getConnectedDevice(String deviceId) async {
    if (deviceId.isEmpty) {
      return null;
    }
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.device;
  }

  @override
  void dispose() {
    _findDevicesTimer?.cancel();
    _didNotMakeItTimer.cancel();
    ServiceManager.instance().device.unsubscribe(this);
    super.dispose();
  }

  @override
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    // TODO: implement onDeviceConnectionStateChanged
  }

  @override
  void onDevices(List<BtDevice> devices) {
    List<BtDevice> foundDevices = devices;

    // Update foundDevicesMap with new devices and remove the ones not found anymore
    Map<String, BtDevice> updatedDevicesMap = {};
    for (final device in foundDevices) {
      // If it's a new device, add it to the map. If it already exists, this will just update the entry.
      updatedDevicesMap[device.id] = device;
    }
    // Remove devices that are no longer found
    foundDevicesMap.keys.where((id) => !updatedDevicesMap.containsKey(id)).toList().forEach(foundDevicesMap.remove);

    // Merge the new devices into the current map to maintain order
    foundDevicesMap.addAll(updatedDevicesMap);
    // Convert the values of the map back to a list
    List<BtDevice> orderedDevices = foundDevicesMap.values.toList();
    if (orderedDevices.isNotEmpty) {
      deviceList = orderedDevices;
      notifyListeners();
      _didNotMakeItTimer.cancel();
    }
  }

  @override
  void onStatusChanged(DeviceServiceStatus status) {
    // TODO: implement onStatusChanged
  }
}
