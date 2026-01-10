import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/companion_device_manager.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/bluetooth/bluetooth_adapter.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:permission_handler/permission_handler.dart';

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
  bool hasScreenCapturePermission = false; // macOS/Windows only
  bool hasAccessibilityPermission = false; // macOS only
  bool isLoading = false;

  // Method channel for macOS/Windows permissions
  static const MethodChannel _screenCaptureChannel = MethodChannel('screenCapturePlatform');

  Future updatePermissions() async {
    if (PlatformService.isDesktop) {
      try {
        // Use macOS-specific permission checking
        String bluetoothStatus = await _screenCaptureChannel.invokeMethod('checkBluetoothPermission');
        hasBluetoothPermission = bluetoothStatus == 'granted';

        String locationStatus = await _screenCaptureChannel.invokeMethod('checkLocationPermission');
        hasLocationPermission = locationStatus == 'granted';

        // Use macOS-specific notification permission checking
        String notificationStatus = await _screenCaptureChannel.invokeMethod('checkNotificationPermission');
        hasNotificationPermission = notificationStatus == 'granted' || notificationStatus == 'provisional';

        // Add microphone permission checking
        String microphoneStatus = await _screenCaptureChannel.invokeMethod('checkMicrophonePermission');
        hasMicrophonePermission = microphoneStatus == 'granted';

        // Add screen capture permission checking
        String screenCaptureStatus = await _screenCaptureChannel.invokeMethod('checkScreenCapturePermission');
        hasScreenCapturePermission = screenCaptureStatus == 'granted';

        // Add accessibility permission checking
        String accessibilityStatus = await _screenCaptureChannel.invokeMethod('checkAccessibilityPermission');
        hasAccessibilityPermission = accessibilityStatus == 'granted';

        debugPrint(
            'Permissions update - Mic: $microphoneStatus, Screen: $screenCaptureStatus, Accessibility: $accessibilityStatus');
      } catch (e) {
        debugPrint('Error updating permissions on macOS: $e');
        // Fallback to standard permission checking
        hasBluetoothPermission = await Permission.bluetooth.isGranted;
        hasLocationPermission = await Permission.location.isGranted;
        hasNotificationPermission = await Permission.notification.isGranted;
        hasMicrophonePermission = await Permission.microphone.isGranted;
        // Screen capture permission not available through permission_handler on macOS
        hasScreenCapturePermission = false;
        hasAccessibilityPermission = false;
      }
    } else {
      // Mobile platforms (iOS/Android)
      hasBluetoothPermission = await Permission.bluetooth.isGranted;
      hasLocationPermission = await Permission.location.isGranted;
      hasNotificationPermission = await Permission.notification.isGranted;
      hasMicrophonePermission = await Permission.microphone.isGranted;
      // Screen capture and accessibility permissions not relevant on mobile platforms for this use case
      hasScreenCapturePermission = false;
      hasAccessibilityPermission = false;
    }

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

  void updateScreenCapturePermission(bool value) {
    hasScreenCapturePermission = value;
    notifyListeners();
  }

  void updateAccessibilityPermission(bool value) {
    hasAccessibilityPermission = value;
    notifyListeners();
  }

  Future askForBluetoothPermissions() async {
    if (!PlatformService.isWindows) {
      FlutterBluePlus.setLogLevel(LogLevel.info, color: true);
    }

    if (PlatformService.isDesktop) {
      try {
        String bluetoothStatus = await _screenCaptureChannel.invokeMethod('checkBluetoothPermission');
        if (bluetoothStatus == 'granted') {
          updateBluetoothPermission(true);
          return;
        }

        if (bluetoothStatus == 'undetermined') {
          bool granted = await _screenCaptureChannel.invokeMethod('requestBluetoothPermission');
          updateBluetoothPermission(granted);
          if (!granted) {
            AppSnackbar.showSnackbarError('Bluetooth permission is required to connect to your device.');
          }
        } else if (bluetoothStatus == 'denied' || bluetoothStatus == 'restricted') {
          updateBluetoothPermission(false);
          AppSnackbar.showSnackbarError('Bluetooth permission denied. Please grant permission in System Preferences.');
        } else {
          updateBluetoothPermission(false);
          AppSnackbar.showSnackbarError(
              'Bluetooth permission status: $bluetoothStatus. Please check System Preferences.');
        }
      } catch (e) {
        debugPrint('Error checking/requesting Bluetooth permission on macOS: $e');
        AppSnackbar.showSnackbarError('Failed to check Bluetooth permission: $e');
        updateBluetoothPermission(false);
      }
    } else if (Platform.isIOS) {
      PermissionStatus bleStatus = await Permission.bluetooth.request();
      debugPrint('bleStatus: $bleStatus');
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
      // PermissionStatus locationStatus = await Permission.location.request();
      updateBluetoothPermission(bleConnectStatus.isGranted && bleScanStatus.isGranted);
    }
    notifyListeners();
  }

  Future askForNotificationPermissions() async {
    if (PlatformService.isDesktop) {
      try {
        String notificationStatus = await _screenCaptureChannel.invokeMethod('checkNotificationPermission');
        debugPrint('notificationStatus: $notificationStatus');
        if (notificationStatus == 'granted') {
          updateNotificationPermission(true);
          return;
        }

        if (notificationStatus == 'undetermined') {
          bool granted = await _screenCaptureChannel.invokeMethod('requestNotificationPermission');
          updateNotificationPermission(granted);
          if (!granted) {
            AppSnackbar.showSnackbarError(
                'Notification permission denied. Please grant permission in System Preferences.');
          }
        } else if (notificationStatus == 'denied') {
          updateNotificationPermission(false);
          // Request permission which will redirect to settings if denied
          await _screenCaptureChannel.invokeMethod('requestNotificationPermission');
          AppSnackbar.showSnackbarError(
              'Notification permission denied. Please grant permission in System Preferences > Notifications.');
        } else if (notificationStatus == 'provisional') {
          updateNotificationPermission(true); // Provisional permissions are still functional
          debugPrint('Notification permission is provisional - notifications will be delivered quietly');
        } else {
          updateNotificationPermission(false);
          AppSnackbar.showSnackbarError(
              'Notification permission status: $notificationStatus. Please check System Preferences.');
        }
      } catch (e) {
        debugPrint('Error checking/requesting Notification permission on macOS: $e');
        AppSnackbar.showSnackbarError('Failed to check Notification permission: $e');
        updateNotificationPermission(false);
      }
    } else {
      // Existing logic for iOS/Android
      var isAllowed = await NotificationService.instance.requestNotificationPermissions();
      updateNotificationPermission(isAllowed);
    }
    notifyListeners();
  }

  Future askForBackgroundPermissions() async {
    await FlutterForegroundTask.requestIgnoreBatteryOptimization();
    var isAllowed = await ForegroundUtil().isIgnoringBatteryOptimizations;
    updateBackgroundPermission(isAllowed);
    notifyListeners();
  }

  Future<(bool, PermissionStatus)> askForLocationPermissions() async {
    if (PlatformService.isDesktop) {
      try {
        String locationStatus = await _screenCaptureChannel.invokeMethod('checkLocationPermission');
        debugPrint('locationStatus: $locationStatus');
        if (locationStatus == 'granted') {
          updateLocationPermission(true);
          return (true, PermissionStatus.granted);
        }

        if (locationStatus == 'undetermined') {
          bool granted = await _screenCaptureChannel.invokeMethod('requestLocationPermission');
          updateLocationPermission(granted);
          debugPrint('undetermined location permission granted: $granted');
          return (true, granted ? PermissionStatus.granted : PermissionStatus.denied);
        } else if (locationStatus == 'denied' || locationStatus == 'restricted') {
          updateLocationPermission(false);
          AppSnackbar.showSnackbarError(
              'Please grant location permission in Settings > Privacy & Security > Location Services');
          return (true, PermissionStatus.permanentlyDenied);
        } else {
          updateLocationPermission(false);
          return (true, PermissionStatus.denied);
        }
      } catch (e) {
        debugPrint('Error checking/requesting Location permission on macOS: $e');
        updateLocationPermission(false);
        return (false, PermissionStatus.denied);
      }
    } else {
      // Existing logic for iOS/Android
      if (await Permission.location.serviceStatus.isDisabled) {
        debugPrint('Location service is disabled');
        return (false, PermissionStatus.permanentlyDenied);
      } else {
        var res = await Permission.locationWhenInUse.request();
        return (true, res);
      }
    }
  }

  Future<bool> alwaysAllowLocation() async {
    if (PlatformService.isDesktop) {
      try {
        String locationStatus = await _screenCaptureChannel.invokeMethod('checkLocationPermission');
        bool granted = locationStatus == 'granted';
        updateLocationPermission(granted);
        return granted;
      } catch (e) {
        debugPrint('Error checking location permission on macOS: $e');
        updateLocationPermission(false);
        return false;
      }
    } else {
      PermissionStatus locationStatus = await Permission.locationAlways.request();
      debugPrint('alwaysAllowLocation permission status: $locationStatus');
      updateLocationPermission(locationStatus.isGranted);
      return locationStatus.isGranted;
    }
  }

  Future askForMicrophonePermissions() async {
    if (PlatformService.isDesktop) {
      try {
        String microphoneStatus = await _screenCaptureChannel.invokeMethod('checkMicrophonePermission');
        debugPrint('microphoneStatus: $microphoneStatus');
        if (microphoneStatus == 'granted') {
          updateMicrophonePermission(true);
          return true;
        }

        if (microphoneStatus == 'undetermined') {
          bool granted = await _screenCaptureChannel.invokeMethod('requestMicrophonePermission');
          updateMicrophonePermission(granted);
          if (!granted) {
            AppSnackbar.showSnackbarError('Microphone permission is required for recording.');
          }
          return granted;
        } else if (microphoneStatus == 'denied' || microphoneStatus == 'restricted') {
          updateMicrophonePermission(false);
          AppSnackbar.showSnackbarError(
              'Microphone permission denied. Please grant permission in System Preferences > Privacy & Security > Microphone.');
          return false;
        } else {
          updateMicrophonePermission(false);
          AppSnackbar.showSnackbarError(
              'Microphone permission status: $microphoneStatus. Please check System Preferences.');
          return false;
        }
      } catch (e) {
        debugPrint('Error checking/requesting Microphone permission on macOS: $e');
        AppSnackbar.showSnackbarError('Failed to check Microphone permission: $e');
        updateMicrophonePermission(false);
        return false;
      }
    } else {
      // Existing logic for iOS/Android
      PermissionStatus micStatus = await Permission.microphone.request();
      debugPrint('micStatus: $micStatus');
      updateMicrophonePermission(micStatus.isGranted);
      return micStatus.isGranted;
    }
  }

  Future askForScreenCapturePermissions() async {
    if (PlatformService.isDesktop) {
      try {
        String screenCaptureStatus = await _screenCaptureChannel.invokeMethod('checkScreenCapturePermission');
        debugPrint('screenCaptureStatus: $screenCaptureStatus');
        if (screenCaptureStatus == 'granted') {
          updateScreenCapturePermission(true);
          return true;
        }

        if (screenCaptureStatus == 'undetermined') {
          bool granted = await _screenCaptureChannel.invokeMethod('requestScreenCapturePermission');
          updateScreenCapturePermission(granted);
          if (!granted) {
            AppSnackbar.showSnackbarError('Screen capture permission is required for system audio recording.');
          }
          return granted;
        } else if (screenCaptureStatus == 'denied') {
          updateScreenCapturePermission(false);
          AppSnackbar.showSnackbarError(
              'Screen capture permission denied. Please grant permission in System Preferences > Privacy & Security > Screen Recording.');
          return false;
        } else {
          updateScreenCapturePermission(false);
          AppSnackbar.showSnackbarError(
              'Screen capture permission status: $screenCaptureStatus. Please check System Preferences.');
          return false;
        }
      } catch (e) {
        debugPrint('Error checking/requesting Screen Capture permission on macOS: $e');
        AppSnackbar.showSnackbarError('Failed to check Screen Capture permission: $e');
        updateScreenCapturePermission(false);
        return false;
      }
    } else {
      // Screen capture not relevant on mobile for this use case
      updateScreenCapturePermission(false);
      return false;
    }
  }

  Future askForAccessibilityPermissions() async {
    if (PlatformService.isDesktop) {
      try {
        String accessibilityStatus = await _screenCaptureChannel.invokeMethod('checkAccessibilityPermission');
        debugPrint('accessibilityStatus: $accessibilityStatus');
        if (accessibilityStatus == 'granted') {
          updateAccessibilityPermission(true);
          return true;
        }

        if (accessibilityStatus == 'undetermined') {
          bool granted = await _screenCaptureChannel.invokeMethod('requestAccessibilityPermission');
          updateAccessibilityPermission(granted);
          if (!granted) {
            AppSnackbar.showSnackbarError('Accessibility permission is required for detecting browser meetings.');
          }
          return granted;
        } else {
          updateAccessibilityPermission(false);
          AppSnackbar.showSnackbarError(
              'Accessibility permission status: $accessibilityStatus. Please check System Preferences.');
          return false;
        }
      } catch (e) {
        debugPrint('Error checking/requesting Accessibility permission on macOS: $e');
        AppSnackbar.showSnackbarError('Failed to check Accessibility permission: $e');
        updateAccessibilityPermission(false);
        return false;
      }
    } else {
      // Accessibility not relevant on mobile for this use case
      updateAccessibilityPermission(false);
      return false;
    }
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
    try {
      if (isClicked) return;
      isClicked = true;

      connectingToDeviceId = device.id;
      notifyListeners();

      if (PlatformService.isAndroid) {
        await _associateCompanionDevice(device);
      }

      await ServiceManager.instance().device.ensureConnection(device.id, force: true);
      debugPrint('Connected to device: ${device.name}');
      deviceId = device.id;
      await SharedPreferencesUtil().btDeviceSet(device);

      if (PlatformService.isAndroid) {
        await _startCompanionDevicePresenceObservation(device.id);
      }

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

  String _getServiceUuidForDevice(BtDevice device) {
    switch (device.type) {
      case DeviceType.limitless:
        return limitlessServiceUuid;
      case DeviceType.bee:
        return beeServiceUuid;
      case DeviceType.fieldy:
        return fieldyServiceUuid;
      case DeviceType.friendPendant:
        return friendPendantServiceUuid;
      case DeviceType.plaud:
        return plaudServiceUuid;
      case DeviceType.frame:
        return frameServiceUuid;
      case DeviceType.omi:
      case DeviceType.openglass:
      case DeviceType.appleWatch:
        return omiServiceUuid;
    }
  }

  Future<void> _associateCompanionDevice(BtDevice device) async {
    try {
      final companionService = CompanionDeviceManagerService.instance;

      // Check if already associated
      final isAssociated = await companionService.isDeviceAssociated(device.id);
      if (isAssociated) {
        debugPrint('CompanionDevice: Device ${device.id} already associated');
        return;
      }

      // Check if CompanionDeviceManager is supported
      if (!await companionService.isSupported()) {
        debugPrint('CompanionDevice: Not supported on this device');
        return;
      }

      debugPrint('CompanionDevice: Associating device ${device.id} (${device.name})');

      final serviceUuid = _getServiceUuidForDevice(device);

      final result = await companionService.associate(
        deviceAddress: device.id,
        deviceName: device.name,
        serviceUuid: serviceUuid,
      );

      if (result.success) {
        debugPrint('CompanionDevice: Association successful');
      } else {
        debugPrint('CompanionDevice: Association failed/cancelled: ${result.error}');
      }
    } catch (e) {
      debugPrint('CompanionDevice: Error during association: $e');
    }
  }

  Future<void> _startCompanionDevicePresenceObservation(String deviceId) async {
    try {
      final companionService = CompanionDeviceManagerService.instance;
      if (await companionService.isPresenceObservingSupported()) {
        if (await companionService.isDeviceAssociated(deviceId)) {
          await companionService.startObservingDevicePresence(deviceId);
        }
      }
    } catch (e) {
      debugPrint('CompanionDevice: Error starting presence observation: $e');
    }
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
    await deviceProvider?.periodicConnect("Come from Onboarding");
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
