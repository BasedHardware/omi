import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/bluetooth/bluetooth_adapter.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

class OnboardingProvider extends BaseProvider with MessageNotifierMixin implements IDeviceServiceSubsciption {
  DeviceProvider? deviceProvider;
  bool isClicked = false;
  bool isConnected = false;
  int batteryPercentage = -1;
  String deviceName = '';
  DeviceType? deviceType;
  String deviceId = '';
  String? connectingToDeviceId;
  List<BtDevice> deviceList = [];
  late Timer _didNotMakeItTimer;
  bool enableInstructions = false;
  Map<String, BtDevice> foundDevicesMap = {};

  //----------------- Onboarding Permissions -----------------
  bool hasBluetoothPermission = false;
  bool hasLocationPermission = false;
  bool hasNotificationPermission = false;
  bool hasBackgroundPermission = false; // Android only
  bool hasMicrophonePermission = false;
  bool isLoading = false;

  Future updatePermissions() async {
    hasBluetoothPermission = await Permission.bluetooth.isGranted;
    hasLocationPermission = await Permission.location.isGranted;
    hasNotificationPermission = await Permission.notification.isGranted;
    hasMicrophonePermission = await Permission.microphone.isGranted;

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

  void updateMicrophonePermission(bool value) {
    hasMicrophonePermission = value;
    notifyListeners();
  }

  Future askForBluetoothPermissions() async {
    FlutterBluePlus.setLogLevel(LogLevel.info, color: true);

    if (Platform.isIOS) {
      PermissionStatus bleStatus = await Permission.bluetooth.request();
      Logger.debug('bleStatus: $bleStatus');
      updateBluetoothPermission(bleStatus.isGranted);
    } else {
      if (Platform.isAndroid) {
        if (!(await BluetoothAdapter.isSupported) ||
            FlutterBluePlus.adapterStateNow != BluetoothAdapterStateHelper.on) {
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
      updateBluetoothPermission(bleConnectStatus.isGranted && bleScanStatus.isGranted);
      // Android 11 and below require location permission for BLE scanning
      if (PlatformService.isAndroid) {
        final deviceInfo = await DeviceInfoPlugin().androidInfo;
        if (deviceInfo.version.sdkInt <= 30) {
          PermissionStatus locationStatus = await Permission.locationWhenInUse.request();
          updateLocationPermission(locationStatus.isGranted);
        }
      }
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
      Logger.debug('Location service is disabled');
      return (false, PermissionStatus.permanentlyDenied);
    } else {
      var res = await Permission.locationWhenInUse.request();
      return (true, res);
    }
  }

  // iOS-only: ask for "Always" so background location updates work during
  // BGTask windows. Android relies on FOREGROUND_SERVICE_LOCATION instead and
  // never asks for ACCESS_BACKGROUND_LOCATION (Play Store prominent-disclosure
  // requirement).
  Future<bool> alwaysAllowLocation() async {
    if (!Platform.isIOS) return false;
    PermissionStatus locationStatus = await Permission.locationAlways.request();
    Logger.debug('alwaysAllowLocation permission status: $locationStatus');
    updateLocationPermission(locationStatus.isGranted);
    return locationStatus.isGranted;
  }

  Future askForMicrophonePermissions() async {
    PermissionStatus micStatus = await Permission.microphone.request();
    Logger.debug('micStatus: $micStatus');
    updateMicrophonePermission(micStatus.isGranted);
    return micStatus.isGranted;
  }
  //----------------- Onboarding Permissions -----------------

  void setDeviceProvider(DeviceProvider provider) {
    deviceProvider = provider;
  }

  // Method to handle taps on devices
  Future<void> handleTap({required BtDevice device, required bool isFromOnboarding, VoidCallback? goNext}) async {
    try {
      if (isClicked) return;
      isClicked = true;

      connectingToDeviceId = device.id;
      notifyListeners();

      // On Android, associate via CompanionDeviceManager BEFORE GATT connection.
      // Device must still be advertising for the system chooser to find it.
      // Stop our scan first so CompanionDeviceManager's scan doesn't conflict.
      if (Platform.isAndroid) {
        try {
          BleHostApi().stopScan();
          final associatedAddress = await BleHostApi().requestCompanionDeviceAssociation(device.id);
          Logger.debug('CompanionDeviceManager association result: $associatedAddress');
        } catch (e) {
          Logger.debug('CompanionDeviceManager association failed (non-fatal): $e');
        }
      }

      await ServiceManager.instance().device.ensureConnection(device.id, force: true);
      Logger.debug('Connected to device: ${device.name}');
      deviceId = device.id;
      await SharedPreferencesUtil().btDeviceSet(device);
      deviceName = device.name;
      deviceType = device.type;
      var cDevice = await _getConnectedDevice(deviceId);
      if (cDevice != null) {
        deviceProvider!.setConnectedDevice(cDevice);
        SharedPreferencesUtil().deviceName = cDevice.name;
        deviceProvider!.setIsConnected(true);
      }
      await deviceProvider?.scanAndConnectToDevice();
      var connectedDevice = deviceProvider!.connectedDevice;
      batteryPercentage = deviceProvider!.batteryLevel;
      isConnected = true;
      isClicked = false;
      connectingToDeviceId = null; // Reset the connecting device
      notifyListeners();
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
      Logger.debug('Error connecting to device: $e');
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
    deviceType = null;
    deviceId = '';
    notifyListeners();
  }

  // TODO: thinh, use connection directly
  Future<BtDevice?> _getConnectedDevice(String deviceId) async {
    if (deviceId.isEmpty) {
      return null;
    }
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.device;
  }

  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {
    if (SharedPreferencesUtil().btDevice.id.isEmpty) {
      // it means the device has been unpaired
      deviceAlreadyUnpaired();
    }

    // check if bluetooth is enabled on both platforms
    if (!hasBluetoothPermission) {
      await askForBluetoothPermissions();
      if (!hasBluetoothPermission) {
        onShowDialog();
        return;
      }
    }

    // Android 11 and below: location permission required for BLE scanning
    if (PlatformService.isAndroid) {
      final deviceInfo = await DeviceInfoPlugin().androidInfo;
      if (deviceInfo.version.sdkInt <= 30) {
        final locationGranted = await Permission.locationWhenInUse.isGranted;
        updateLocationPermission(locationGranted);
        if (!locationGranted) {
          onShowLocationDialog?.call();
          return;
        }
      }
    }

    _didNotMakeItTimer = Timer(const Duration(seconds: 10), () {
      enableInstructions = true;
      notifyListeners();
    });

    ServiceManager.instance().device.subscribe(this, this);
    await deviceProvider?.initiateConnection("Onboarding");
  }

  @override
  void dispose() {
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
