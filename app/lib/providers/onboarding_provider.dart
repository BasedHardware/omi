import 'dart:async';
import 'dart:io';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permission_decision.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/devices/pairing_failure.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/audio/foreground.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/analytics/product_telemetry.dart';

class OnboardingProvider extends BaseProvider with MessageNotifierMixin implements IDeviceServiceSubsciption {
  DeviceProvider? deviceProvider;
  DeviceConnectFailureShownFailureReason? pairingFailureReason;
  int pairingFailureVersion = 0;

  void dismissPairingFailure() {
    pairingFailureReason = null;
    notifyListeners();
  }

  bool isClicked = false;
  bool isConnected = false;
  int batteryPercentage = -1;
  String deviceName = '';
  DeviceType? deviceType;
  String deviceId = '';
  String? connectingToDeviceId;
  List<BtDevice> deviceList = [];
  List<BtDevice> savedDeviceList = [];
  Timer? _didNotMakeItTimer;
  Timer? _connectSettleTimer;

  /// A tap-to-connect is connected and in its settle, before it persists the device and calls
  /// goNext. [isConnected] stays true afterwards, so it cannot tell a settling attempt apart.
  bool get isSettlingConnection => _connectSettleTimer != null;
  int _scanEpoch = 0;
  bool _reportNativeScanBlocks = false;
  final OnboardingPermissionDecisionLog _permissionDecisions = OnboardingPermissionDecisionLog();
  String? _lastPairingBlockKey;
  int _osAndroidSdk = 0;
  int _osIosVersion = 0;
  bool _osFactsLoaded = false;
  VoidCallback? _removeScanBlockedListener;
  bool _isDisposed = false;
  bool enableInstructions = false;
  Map<String, BtDevice> foundDevicesMap = {};

  OnboardingProvider() {
    _syncSavedDevices();
    _removeScanBlockedListener = BleBridge.instance.addScanBlockedListener(_onNativeScanBlocked);
    unawaited(_ensureOsFacts());
  }

  List<BtDevice> get visibleDeviceList {
    final visibleDevices = <BtDevice>[];
    for (final savedDevice in savedDeviceList) {
      final onlineDevice = foundDevicesMap[savedDevice.id];
      visibleDevices.add(onlineDevice ?? savedDevice);
    }
    for (final device in deviceList) {
      if (!visibleDevices.any((visibleDevice) => visibleDevice.id == device.id)) {
        visibleDevices.add(device);
      }
    }
    return visibleDevices;
  }

  bool isSavedDevice(BtDevice device) => savedDeviceList.any((savedDevice) => savedDevice.id == device.id);

  bool isDeviceOnline(BtDevice device) => foundDevicesMap.containsKey(device.id);

  int get nearbyDeviceCount => deviceList.length;

  void _syncSavedDevices() {
    savedDeviceList = SharedPreferencesUtil().btDevices.where((device) => device.id.isNotEmpty).toList();
  }

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
    PlatformManager.instance.analytics.setUserAttribute('Location Enabled', SharedPreferencesUtil().locationEnabled);
    notifyListeners();
  }

  void updateNotificationPermission(bool value) {
    hasNotificationPermission = value;
    SharedPreferencesUtil().notificationsEnabled = value;
    PlatformManager.instance.analytics.setUserAttribute(
      'Notifications Enabled',
      SharedPreferencesUtil().notificationsEnabled,
    );
    notifyListeners();
  }

  void updateBackgroundPermission(bool value) {
    hasBackgroundPermission = value;
    PlatformManager.instance.analytics.setUserAttribute('Background Permission Enabled', hasBackgroundPermission);
    notifyListeners();
  }

  void updateMicrophonePermission(bool value) {
    hasMicrophonePermission = value;
    notifyListeners();
  }

  Future askForBluetoothPermissions() async {
    final attempt = ProductTelemetry.instance.start(
      ProductJourney.permission,
      surface: ProductSurface.onboarding,
    );
    try {
      if (Platform.isIOS) {
        PermissionStatus bleStatus = await Permission.bluetooth.request();
        Logger.debug('bleStatus: $bleStatus');
        updateBluetoothPermission(bleStatus.isGranted);
      } else {
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
      if (hasBluetoothPermission) {
        await BluetoothReadiness.instance.ensureReady(BluetoothUse.discovery);
      }
      attempt.complete(
        hasBluetoothPermission ? ProductOutcome.success : ProductOutcome.failure,
        failure: hasBluetoothPermission ? ProductFailure.none : ProductFailure.permissionDenied,
      );
    } catch (e) {
      attempt.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
      notifyListeners();
    }
    notifyListeners();
  }

  /// Whether Omi may scan for and connect to Bluetooth devices, read without prompting.
  Future<bool> readBluetoothPermission() async {
    final granted = Platform.isIOS
        ? await Permission.bluetooth.isGranted
        : await Permission.bluetoothScan.isGranted && await Permission.bluetoothConnect.isGranted;
    if (granted != hasBluetoothPermission) updateBluetoothPermission(granted);
    return granted;
  }

  /// Starts looking for nearby devices in the background, without prompts, when Bluetooth is
  /// already allowed. "Connect your Omi" then shows the device the moment it opens.
  Future<void> startQuietDeviceScan() async {
    if (_isDisposed || isConnected) return;
    if (!await readBluetoothPermission()) return;
    // Only when the radio is already on: an off adapter would raise the shared "Enable Bluetooth"
    // guidance over an unrelated step. "Connect your Omi" handles that case itself.
    try {
      if (BluetoothReadiness.parse(await BleHostApi().getBluetoothState()) != BluetoothAdapterState.on) return;
    } catch (_) {
      return;
    }
    if (_isDisposed) return;
    ServiceManager.instance().device.subscribe(this, this);
    await deviceProvider?.initiateConnection('OnboardingEarlyScan');
  }

  /// Ends a search screen's session: stops scanning and clears "nothing found", so the next search
  /// screen (onboarding's Connect Omi or the in-app pairing page, which share this provider) starts
  /// fresh instead of opening on a stale "No Omi Found".
  void endSearch() {
    cancelActiveScan();
    enableInstructions = false;
  }

  Future askForNotificationPermissions() async {
    final attempt = ProductTelemetry.instance.start(
      ProductJourney.permission,
      surface: ProductSurface.onboarding,
    );
    try {
      var isAllowed = await NotificationService.instance.requestNotificationPermissions();
      updateNotificationPermission(isAllowed);
      final status = await Permission.notification.status;
      _recordOnboardingPermission(
        permission: OnboardingPermissionResultPermission.notifications,
        granted: isAllowed,
        permanentlyDenied: !isAllowed && permissionStatusIsPermanentDenial(status),
      );
      attempt.complete(
        isAllowed ? ProductOutcome.success : ProductOutcome.failure,
        failure: isAllowed ? ProductFailure.none : ProductFailure.permissionDenied,
      );
      notifyListeners();
    } catch (e) {
      attempt.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
      notifyListeners();
      return false;
    }
  }

  Future askForBackgroundPermissions() async {
    final attempt = ProductTelemetry.instance.start(
      ProductJourney.permission,
      surface: ProductSurface.onboarding,
    );
    try {
      await FlutterForegroundTask.requestIgnoreBatteryOptimization();
      var isAllowed = await ForegroundUtil().isIgnoringBatteryOptimizations;
      updateBackgroundPermission(isAllowed);
      _recordOnboardingPermission(
        permission: OnboardingPermissionResultPermission.backgroundActivity,
        granted: isAllowed,
        permanentlyDenied: false,
      );
      attempt.complete(
        isAllowed ? ProductOutcome.success : ProductOutcome.failure,
        failure: isAllowed ? ProductFailure.none : ProductFailure.permissionDenied,
      );
      notifyListeners();
    } catch (e) {
      attempt.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
      return false;
    }
  }

  Future<(bool, PermissionStatus)> askForLocationPermissions() async {
    final attempt = ProductTelemetry.instance.start(
      ProductJourney.permission,
      surface: ProductSurface.onboarding,
    );
    try {
      if (await Permission.location.serviceStatus.isDisabled) {
        Logger.debug('Location service is disabled');
        attempt.complete(ProductOutcome.failure, failure: ProductFailure.permissionDenied);
        _recordOnboardingPermission(
          permission: OnboardingPermissionResultPermission.location,
          granted: false,
          permanentlyDenied: false,
          servicesDisabled: true,
        );
        return (false, PermissionStatus.denied);
      }
      var res = await Permission.locationWhenInUse.request();
      _recordOnboardingPermission(
        permission: OnboardingPermissionResultPermission.location,
        granted: res.isGranted,
        permanentlyDenied: permissionStatusIsPermanentDenial(res),
      );
      attempt.complete(
        res.isGranted ? ProductOutcome.success : ProductOutcome.failure,
        failure: res.isGranted ? ProductFailure.none : ProductFailure.permissionDenied,
      );
      return (true, res);
    } catch (e) {
      attempt.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
      return (false, PermissionStatus.denied);
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
    final attempt = ProductTelemetry.instance.start(
      ProductJourney.permission,
      surface: ProductSurface.onboarding,
    );
    try {
      PermissionStatus micStatus = await Permission.microphone.request();
      Logger.debug('micStatus: $micStatus');
      updateMicrophonePermission(micStatus.isGranted);
      attempt.complete(
        micStatus.isGranted ? ProductOutcome.success : ProductOutcome.failure,
        failure: micStatus.isGranted ? ProductFailure.none : ProductFailure.permissionDenied,
      );
      return micStatus.isGranted;
    } catch (e) {
      attempt.complete(ProductOutcome.failure, failure: ProductFailure.unknown);
      rethrow;
    }
  }
  //----------------- Onboarding Permissions -----------------

  void setDeviceProvider(DeviceProvider provider) {
    deviceProvider = provider;
  }

  // Method to handle taps on devices
  Future<void> handleTap({required BtDevice device, required bool isFromOnboarding, VoidCallback? goNext}) async {
    try {
      if (isClicked) return;
      pairingFailureReason = null;
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

      final connection = await ServiceManager.instance().device.ensureConnection(device.id, force: true);
      if (connection == null || connection.status != DeviceConnectionState.connected) {
        throw StateError('Device initialization did not complete');
      }
      Logger.debug('Connected to device: ${device.name}');
      deviceId = device.id;
      await SharedPreferencesUtil().btDeviceSet(device);
      _syncSavedDevices();
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
      _connectSettleTimer?.cancel();
      final settle = Completer<void>();
      _connectSettleTimer = Timer(const Duration(seconds: 2), () {
        if (!settle.isCompleted) settle.complete();
      });
      await settle.future;
      _connectSettleTimer = null;
      if (_isDisposed) return;
      SharedPreferencesUtil().btDevice = connectedDevice!;
      _syncSavedDevices();
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
      isClicked = false; // Allow clicks again after finishing the operation
      connectingToDeviceId = null; // Reset the connecting device
      deviceProvider?.setIsConnected(false);
      pairingFailureVersion++;
      pairingFailureReason =
          connectFailureReason(e, staleBond: ServiceManager.instance().device.staleBondRecoveryRequired);
      PlatformManager.instance.analytics.deviceConnectFailed(classifyDeviceConnectError(e));
      notifyError('DEVICE_CONNECT_FAILED');
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
    final epoch = ++_scanEpoch;
    _reportNativeScanBlocks = true;
    if (SharedPreferencesUtil().btDevice.id.isEmpty) {
      // it means the device has been unpaired
      deviceAlreadyUnpaired();
    }
    if (_isDisposed || epoch != _scanEpoch) return;
    await _ensureOsFacts();
    if (_isDisposed || epoch != _scanEpoch) return;

    // Subscribe before checking the adapter so a successful enable action can
    // retry discovery and publish its results back to this page.
    ServiceManager.instance().device.subscribe(this, this);

    // check if bluetooth is enabled on both platforms
    if (!hasBluetoothPermission) {
      await askForBluetoothPermissions();
      if (_isDisposed || epoch != _scanEpoch) return;
      if (!hasBluetoothPermission) {
        _emitPairingBlocked(
          pairingBlockBeforeScan(
            isAndroid: Platform.isAndroid,
            androidSdk: _osAndroidSdk,
            bluetoothGranted: false,
            locationGranted: hasLocationPermission,
            adapterOff: false,
          ),
        );
        _armInstructionsTimer(epoch, scanStarted: false);
        onShowDialog();
        return;
      }
    }

    // Android 11 and below: location permission required for BLE scanning
    if (PlatformService.isAndroid) {
      final deviceInfo = await DeviceInfoPlugin().androidInfo;
      _osAndroidSdk = deviceInfo.version.sdkInt;
      _osFactsLoaded = true;
      if (_isDisposed || epoch != _scanEpoch) return;
      if (deviceInfo.version.sdkInt <= 30) {
        final locationGranted = await Permission.locationWhenInUse.isGranted;
        updateLocationPermission(locationGranted);
        if (!locationGranted) {
          _emitPairingBlocked(DevicePairingBlockedReason.locationPermissionMissing);
          _armInstructionsTimer(epoch, scanStarted: false);
          onShowLocationDialog?.call();
          return;
        }
      }
    }

    if (!await BluetoothReadiness.instance.ensureReady(BluetoothUse.discovery)) {
      if (_isDisposed || epoch != _scanEpoch) return;
      _emitPairingBlocked(_pairingBlockForAdapter(BluetoothReadiness.instance.state),
          adapterState: BluetoothReadiness.instance.state);
      _armInstructionsTimer(epoch, scanStarted: false);
      return;
    }
    if (_isDisposed || epoch != _scanEpoch) return;

    _armInstructionsTimer(epoch, scanStarted: true);

    await deviceProvider?.initiateConnection("Onboarding");
  }

  /// Arms the delayed "No Omi Found" help (Scan Again, pairing guide, Contact Support). A blocked
  /// search arms it too, so the help never depends on discovery having started; only a scan that
  /// actually ran reports Device Scan Empty (a blocked one already reported Device Pairing Blocked).
  void _armInstructionsTimer(int epoch, {required bool scanStarted}) {
    _didNotMakeItTimer?.cancel();
    _didNotMakeItTimer = Timer(const Duration(seconds: deviceScanEmptyAfterSeconds), () {
      if (_isDisposed || epoch != _scanEpoch) return;
      if (scanStarted && shouldReportEmptyDeviceScan(deviceCount: deviceList.length)) {
        PlatformManager.instance.analytics.deviceScanEmpty(afterSeconds: deviceScanEmptyAfterSeconds);
      }
      enableInstructions = true;
      notifyListeners();
    });
  }

  void _recordOnboardingPermission({
    required OnboardingPermissionResultPermission permission,
    required bool granted,
    required bool permanentlyDenied,
    bool servicesDisabled = false,
  }) {
    if (!_permissionDecisions.claim(
      permission: permission,
      granted: granted,
      permanentlyDenied: permanentlyDenied,
      servicesDisabled: servicesDisabled,
    )) {
      return;
    }
    PlatformManager.instance.analytics.onboardingPermissionResult(
      permission: permission,
      granted: granted,
      permanentlyDenied: permanentlyDenied,
      servicesDisabled: servicesDisabled,
    );
  }

  Future<void> _ensureOsFacts() async {
    if (_osFactsLoaded) return;
    try {
      if (Platform.isAndroid) {
        _osAndroidSdk = (await DeviceInfoPlugin().androidInfo).version.sdkInt;
      } else if (Platform.isIOS) {
        _osIosVersion = iosMajorVersion((await DeviceInfoPlugin().iosInfo).systemVersion);
      }
    } catch (error) {
      Logger.debug('pairing OS facts unavailable: $error');
    }
    _osFactsLoaded = true;
  }

  void _onNativeScanBlocked(String reason) {
    if (!_reportNativeScanBlocks) return;
    _emitPairingBlocked(pairingBlockFromNativeScan(reason));
  }

  DevicePairingBlockedReason? _pairingBlockForAdapter(BluetoothAdapterState state) {
    return switch (state) {
      BluetoothAdapterState.unauthorized => pairingBlockBeforeScan(
          isAndroid: Platform.isAndroid,
          androidSdk: _osAndroidSdk,
          bluetoothGranted: hasBluetoothPermission,
          locationGranted: hasLocationPermission,
          adapterOff: false,
        ),
      BluetoothAdapterState.on => null,
      _ => DevicePairingBlockedReason.bluetoothOff,
    };
  }

  void _emitPairingBlocked(DevicePairingBlockedReason? reason, {BluetoothAdapterState? adapterState}) {
    if (reason == null) return;
    final key = '$_scanEpoch|${reason.wireName}';
    if (_lastPairingBlockKey == key) return;
    _lastPairingBlockKey = key;
    pairingFailureVersion++;
    pairingFailureReason = blockedFailureReason(reason, adapterState: adapterState);
    notifyListeners();
    PlatformManager.instance.analytics.devicePairingBlocked(
      reason: reason,
      androidSdk: _osAndroidSdk < 0 ? 0 : _osAndroidSdk,
      iosVersion: _osIosVersion < 0 ? 0 : _osIosVersion,
    );
  }

  void cancelActiveScan() {
    _reportNativeScanBlocks = false;
    pairingFailureReason = null;
    _scanEpoch++;
    _didNotMakeItTimer?.cancel();
    _didNotMakeItTimer = null;
    deviceProvider?.stopDiscoveryScanning();
  }

  @override
  void dispose() {
    _isDisposed = true;
    _removeScanBlockedListener?.call();
    _removeScanBlockedListener = null;
    cancelActiveScan();
    _connectSettleTimer?.cancel();
    _connectSettleTimer = null;
    ServiceManager.instance().device.unsubscribe(this);
    super.dispose();
  }

  @override
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    // TODO: implement onDeviceConnectionStateChanged
  }

  @override
  void onDevices(List<BtDevice> devices) {
    _syncSavedDevices();
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
    deviceList = orderedDevices;
    if (visibleDeviceList.isNotEmpty) {
      if (pairingFailureReason == DeviceConnectFailureShownFailureReason.notFoundOrDropped) {
        pairingFailureReason = null;
      }
      notifyListeners();
      _didNotMakeItTimer?.cancel();
    }
  }

  @override
  void onStatusChanged(DeviceServiceStatus status) {
    // TODO: implement onStatusChanged
  }
}
