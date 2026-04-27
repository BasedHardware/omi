import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/omiglass_ota_update.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/omi_connection.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/battery_widget_service.dart';
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
  bool isDeviceStorageSupport = false;
  bool supportsMultiFileSync = SharedPreferencesUtil().deviceSupportsMultiFileSync;
  BtDevice? connectedDevice;
  BtDevice? pairedDevice;
  StreamSubscription<List<int>>? _bleBatteryLevelListener;
  StreamSubscription? _bleChargingStatusListener;
  int batteryLevel = -1;
  bool isCharging = false;
  int _lastNotifiedBatteryLevel = -1;
  DateTime? _lastBatteryNotifyTime;
  bool _hasLowBatteryAlerted = false;
  bool _havingNewFirmware = false;
  bool get havingNewFirmware => _havingNewFirmware && pairedDevice != null && isConnected;

  // Track firmware update state to prevent showing dialog during updates
  bool _isCheckingFirmware = false;
  bool _isFirmwareDialogShowing = false;
  bool _isFirmwareUpdateInProgress = false;
  bool get isFirmwareUpdateInProgress => _isFirmwareUpdateInProgress;

  // Current and latest firmware versions for UI display
  String get currentFirmwareVersion => pairedDevice?.firmwareRevision ?? 'Unknown';
  String _latestFirmwareVersion = '';
  String get latestFirmwareVersion => _latestFirmwareVersion;

  // Latest stable firmware version (for rollback comparison)
  String _latestStableFirmwareVersion = '';
  String get latestStableFirmwareVersion => _latestStableFirmwareVersion;

  // OmiGlass firmware update details from GitHub releases
  Map<String, dynamic> _latestOmiGlassFirmwareDetails = {};
  Map<String, dynamic> get latestOmiGlassFirmwareDetails => _latestOmiGlassFirmwareDetails;

  Timer? _discoveryTimer;
  final Debouncer _disconnectDebouncer = Debouncer(delay: const Duration(milliseconds: 500));
  final Debouncer _connectDebouncer = Debouncer(delay: const Duration(milliseconds: 100));

  void Function(BtDevice device)? onDeviceConnected;
  void Function(BtDevice device, int fileCount, int totalBytes)? onOfflineDataDetected;

  DeviceProvider() {
    ServiceManager.instance().device.subscribe(this, this);
  }

  void setProviders(CaptureProvider provider) {
    captureProvider = provider;
    notifyListeners();
  }

  Future<void> setConnectedDevice(BtDevice? device) async {
    connectedDevice = device;
    pairedDevice = device;
    await getDeviceInfo();
    Logger.debug('setConnectedDevice: $device');
    notifyListeners();
  }

  Future getDeviceInfo() async {
    if (connectedDevice != null) {
      if (pairedDevice?.firmwareRevision != null && pairedDevice?.firmwareRevision != 'Unknown') {
        SharedPreferencesUtil().btDevice = pairedDevice!;
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

  Future _bleDisconnectDevice(BtDevice btDevice) async {
    await ServiceManager.instance().device.disconnectDevice();
  }

  Future<int> _retrieveBatteryLevel(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return -1;
    }
    return connection.retrieveBatteryLevel();
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
        BatteryWidgetService().updateBatteryInfo(
          deviceName: connectedDevice?.name ?? '',
          batteryLevel: value,
          deviceType: connectedDevice?.type.name ?? 'omi',
          isConnected: true,
        );
        if (batteryLevel < 20 && !_hasLowBatteryAlerted) {
          _hasLowBatteryAlerted = true;
          final ctx = globalNavigatorKey.currentContext;
          NotificationService.instance.createNotification(
            title: ctx?.l10n.lowBatteryAlertTitle ?? "Low Battery Alert",
            body: ctx?.l10n.lowBatteryAlertBody ?? "Your device is running low on battery. Time for a recharge! 🔋",
          );
        } else if (batteryLevel > 20) {
          _hasLowBatteryAlerted = false;
        }
        // Throttle notifyListeners to reduce battery drain from excessive UI rebuilds
        // Only notify when: first reading, >=5% change, 15min elapsed, or crosses 20% threshold
        final delta = (_lastNotifiedBatteryLevel - value).abs();
        final elapsed = _lastBatteryNotifyTime == null
            ? const Duration(minutes: 999)
            : DateTime.now().difference(_lastBatteryNotifyTime!);
        final crossedLowBatteryThreshold =
            (value < 20 && _lastNotifiedBatteryLevel >= 20) || (value >= 20 && _lastNotifiedBatteryLevel < 20);
        final shouldNotify =
            _lastNotifiedBatteryLevel == -1 || delta >= 5 || elapsed.inMinutes >= 15 || crossedLowBatteryThreshold;
        if (shouldNotify) {
          _lastNotifiedBatteryLevel = value;
          _lastBatteryNotifyTime = DateTime.now();
          notifyListeners();
        }
      },
    );
    notifyListeners();
  }

  Future<void> initiateChargingStatusListener() async {
    if (connectedDevice == null) return;
    _bleChargingStatusListener?.cancel();

    var connection = await ServiceManager.instance().device.ensureConnection(connectedDevice!.id);
    if (connection == null) return;
    if (connection is! OmiDeviceConnection) return;

    final currentStatus = await connection.readChargingStatus();
    if (isCharging != currentStatus) {
      isCharging = currentStatus;
      notifyListeners();
    }

    _bleChargingStatusListener = await connection.getChargingStatusListener(
      onChargingStatusChange: (bool charging) {
        if (isCharging != charging) {
          isCharging = charging;
          notifyListeners();
        }
      },
    );
  }

  /// Updates battery level with throttling logic. Returns true if notifyListeners was called.
  /// This method is exposed for testing the throttling behavior.
  @visibleForTesting
  bool updateBatteryLevelForTesting(int value, {DateTime? now}) {
    batteryLevel = value;
    final currentTime = now ?? DateTime.now();

    // Throttle notifyListeners to reduce battery drain from excessive UI rebuilds
    // Only notify when: first reading, >=5% change, 15min elapsed, or crosses 20% threshold
    final delta = (_lastNotifiedBatteryLevel - value).abs();
    final elapsed =
        _lastBatteryNotifyTime == null ? const Duration(minutes: 999) : currentTime.difference(_lastBatteryNotifyTime!);
    final crossedLowBatteryThreshold =
        (value < 20 && _lastNotifiedBatteryLevel >= 20) || (value >= 20 && _lastNotifiedBatteryLevel < 20);
    final shouldNotify =
        _lastNotifiedBatteryLevel == -1 || delta >= 5 || elapsed.inMinutes >= 15 || crossedLowBatteryThreshold;
    if (shouldNotify) {
      _lastNotifiedBatteryLevel = value;
      _lastBatteryNotifyTime = currentTime;
      notifyListeners();
      return true;
    }
    return false;
  }

  /// Resets battery throttling state for testing.
  @visibleForTesting
  void resetBatteryThrottlingForTesting() {
    _lastNotifiedBatteryLevel = -1;
    _lastBatteryNotifyTime = null;
  }

  /// Kicks off a single connection attempt. Native handles auto-reconnect after this.
  Future<void> initiateConnection(String caller, {bool boundDeviceOnly = false}) async {
    final pairedDeviceId = SharedPreferencesUtil().btDevice.id;

    // Already connected — nothing to do
    if (isConnected || connectedDevice != null) return;

    // No paired device (onboarding) — start periodic scanning so devices
    // turned on after the page loads are still discovered.
    if (pairedDeviceId.isEmpty) {
      if (boundDeviceOnly) return;
      _startDiscoveryScanning();
      return;
    }

    // Known device — use ensureConnection which creates the NativeBleTransport,
    // then connects natively. If native is already connected, it just re-notifies Dart.
    // force: true ensures we retry even if a previous attempt left a stale connection.
    try {
      await ServiceManager.instance().device.ensureConnection(pairedDeviceId, force: true);
    } catch (e) {
      // Timeout or transport failure — native keeps trying in the background.
      // NativeBleTransport's BleBridge registration persists, so auto-reconnect still works.
      Logger.debug('initiateConnection ($caller): ensureConnection failed: $e');
    }
  }

  void _startDiscoveryScanning() {
    _discoveryTimer?.cancel();
    _runDiscoveryScan();
    _discoveryTimer = Timer.periodic(const Duration(seconds: 10), (_) => _runDiscoveryScan());
  }

  Future<void> _runDiscoveryScan() async {
    if (SharedPreferencesUtil().btDevice.id.isNotEmpty || isConnected) {
      _discoveryTimer?.cancel();
      return;
    }
    final deviceService = ServiceManager.instance().device;
    if (deviceService is DeviceService && deviceService.status == DeviceServiceStatus.ready) {
      try {
        await deviceService.discover();
      } catch (e) {
        Logger.debug('_runDiscoveryScan: discover failed: $e');
      }
    }
  }

  Future scanAndConnectToDevice() async {
    updateConnectingStatus(true);
    if (isConnected && connectedDevice != null) {
      updateConnectingStatus(false);
      return;
    }

    final pairedDeviceId = SharedPreferencesUtil().btDevice.id;
    if (pairedDeviceId.isEmpty) {
      updateConnectingStatus(false);
      return;
    }

    try {
      var connection = await ServiceManager.instance().device.ensureConnection(pairedDeviceId, force: true);
      if (connection != null) {
        await setConnectedDevice(connection.device);
        setisDeviceStorageSupport();
        SharedPreferencesUtil().deviceName = connection.device.name;
        MixpanelManager().deviceConnected();
        setIsConnected(true);
      }
    } catch (e) {
      Logger.debug('scanAndConnectToDevice: connection failed: $e');
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
      _discoveryTimer?.cancel();
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBatteryLevelListener?.cancel();
    _bleChargingStatusListener?.cancel();
    _discoveryTimer?.cancel();
    _disconnectDebouncer.cancel();
    _connectDebouncer.cancel();
    ServiceManager.instance().device.unsubscribe(this);
    super.dispose();
  }

  void onDeviceDisconnected() async {
    Logger.debug('onDisconnected inside: $connectedDevice');
    _havingNewFirmware = false;
    _isFirmwareDialogShowing = false;
    _bleChargingStatusListener?.cancel();
    isCharging = false;
    setConnectedDevice(null);
    setisDeviceStorageSupport();
    setIsConnected(false);
    updateConnectingStatus(false);

    captureProvider?.updateRecordingDevice(null);

    // Wals
    ServiceManager.instance().wal.getSyncs().sdcard.setDevice(null);
    ServiceManager.instance().wal.getSyncs().flashPage.setDevice(null);

    PlatformManager.instance.crashReporter.logInfo('Omi Device Disconnected');

    MixpanelManager().deviceDisconnected();
    BatteryWidgetService().updateBatteryInfo(
      deviceName: SharedPreferencesUtil().deviceName,
      batteryLevel: -1,
      deviceType: 'omi',
      isConnected: false,
    );
  }

  Future<(String, bool, String, Map)> shouldUpdateFirmware() async {
    if (pairedDevice == null || connectedDevice == null) {
      return ('No paired device is connected', false, '', {});
    }

    var device = pairedDevice!;
    var latestFirmwareDetails = await getLatestFirmwareVersion(
      deviceModelNumber: device.modelNumber,
      firmwareRevision: device.firmwareRevision,
      hardwareRevision: device.hardwareRevision,
      manufacturerName: device.manufacturerName,
    );

    var (message, hasUpdate, version) = await DeviceUtils.shouldUpdateFirmware(
      currentFirmware: device.firmwareRevision,
      latestFirmwareDetails: latestFirmwareDetails,
    );
    return (message, hasUpdate, version, latestFirmwareDetails);
  }

  void _onDeviceConnected(BtDevice device) async {
    Logger.debug('_onConnected inside: $connectedDevice');
    setConnectedDevice(device);

    if (captureProvider != null) {
      captureProvider?.updateRecordingDevice(device);
    }

    setisDeviceStorageSupport();
    setIsConnected(true);

    // Read initial battery level
    int currentLevel = await _retrieveBatteryLevel(device.id);
    if (currentLevel != -1) {
      batteryLevel = currentLevel;
      BatteryWidgetService().updateBatteryInfo(
        deviceName: device.name,
        batteryLevel: currentLevel,
        deviceType: device.type.name,
        isConnected: true,
      );
    }

    // Then set up listeners for battery changes and charging status
    await initiateBleBatteryListener();
    await initiateChargingStatusListener();
    if (batteryLevel != -1 && batteryLevel < 20) {
      _hasLowBatteryAlerted = false;
    }
    updateConnectingStatus(false);
    await captureProvider?.streamDeviceRecording(device: device);

    await getDeviceInfo();
    SharedPreferencesUtil().deviceName = device.name;

    // Wals
    ServiceManager.instance().wal.getSyncs().sdcard.setDevice(device);
    ServiceManager.instance().wal.getSyncs().flashPage.setDevice(device);
    ServiceManager.instance().wal.getSyncs().storage.setDevice(device);

    // Auto-sync: check if device has offline files (new multi-file firmware)
    _checkAndStartAutoSync(device);

    notifyListeners();

    // Check firmware updates
    _checkFirmwareUpdates();

    if (Platform.isAndroid) {
      _ensureCompanionAssociation(device);
    }

    onDeviceConnected?.call(device);
  }

  /// Check firmware version to determine multi-file sync support.
  /// Firmware >= 3.0.17 supports the new LittleFS multi-file protocol.
  static bool _isFirmwareVersionSupported(String? version) {
    if (version == null || version.isEmpty || version == 'Unknown') return false;
    final parts = version.split('.').map((p) => int.tryParse(p) ?? 0).toList();
    if (parts.length < 3) return false;
    // Compare against 3.0.17
    if (parts[0] > 3) return true;
    if (parts[0] < 3) return false;
    if (parts[1] > 0) return true;
    if (parts[1] < 0) return false;
    return parts[2] >= 17;
  }

  Future<void> _checkAndStartAutoSync(BtDevice device) async {
    try {
      // Use firmware version as the reliable signal for multi-file support
      // Read from pairedDevice which has firmwareRevision populated by getDeviceInfo()
      supportsMultiFileSync = _isFirmwareVersionSupported(pairedDevice?.firmwareRevision ?? device.firmwareRevision);
      SharedPreferencesUtil().deviceSupportsMultiFileSync = supportsMultiFileSync;
      notifyListeners();

      if (!supportsMultiFileSync) return;

      var connection = await ServiceManager.instance().device.ensureConnection(device.id);
      if (connection == null) return;

      final status = await connection.getStorageFileStats();
      if (status == null || status.fileCount == 0) return;

      Logger.debug('DeviceProvider: Auto-sync detected ${status.fileCount} files (${status.totalUsedBytes} bytes)');
      onOfflineDataDetected?.call(device, status.fileCount, status.totalUsedBytes);
    } catch (e) {
      Logger.debug('DeviceProvider: Auto-sync check failed: $e');
    }
  }

  Future<void> _ensureCompanionAssociation(BtDevice device) async {
    try {
      if (SharedPreferencesUtil().companionAssociationPrompted) return;
      if (await BleHostApi().hasCompanionDeviceAssociation()) return;
      final ctx = globalNavigatorKey.currentContext;
      if (ctx == null || !ctx.mounted) return;
      SharedPreferencesUtil().companionAssociationPrompted = true;
      await showDialog(
        context: ctx,
        builder: (context) => AlertDialog(
          title: Text(context.l10n.improveConnectionTitle),
          content: Text(context.l10n.improveConnectionContent),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(context.l10n.improveConnectionAction, style: const TextStyle(color: Colors.white)),
            ),
          ],
        ),
      );
    } catch (e) {
      Logger.debug('CompanionDevice association check failed: $e');
    }
  }

  void _handleDeviceConnected(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return;
    }
    _onDeviceConnected(connection.device);
  }

  void _checkFirmwareUpdates() async {
    if (_isFirmwareUpdateInProgress || _isCheckingFirmware) {
      return;
    }

    _isCheckingFirmware = true;
    try {
      await checkFirmwareUpdates();

      // Show firmware update dialog if needed
      if (_havingNewFirmware) {
        // Use a small delay to ensure the UI is ready
        Future.delayed(const Duration(milliseconds: 500), () {
          final context = globalNavigatorKey.currentContext;
          if (context != null) {
            showFirmwareUpdateDialog(context);
          }
        });
      }
    } finally {
      _isCheckingFirmware = false;
    }
  }

  bool get _isOmiGlassDevice {
    if (pairedDevice == null) return false;
    if (pairedDevice!.type == DeviceType.openglass) return true;
    final name = pairedDevice!.name.toLowerCase();
    return name.contains('openglass') || name.contains('omiglass') || name.contains('glass');
  }

  Future checkFirmwareUpdates() async {
    int retryCount = 0;
    const maxRetries = 3;
    const retryDelay = Duration(seconds: 3);

    while (retryCount < maxRetries) {
      try {
        var (message, hasUpdate, version, firmwareDetails) = await shouldUpdateFirmware();
        _havingNewFirmware = hasUpdate;
        _latestFirmwareVersion = version.isNotEmpty ? version : message;

        // For OmiGlass devices, populate the firmware details for the OTA UI
        if (_isOmiGlassDevice && firmwareDetails.isNotEmpty) {
          // Map backend response to OmiGlass OTA UI expected format
          final versionStr = firmwareDetails['version']?.toString() ?? '';
          final cleanVersion = versionStr.startsWith('v') ? versionStr.substring(1) : versionStr;
          final changelog = firmwareDetails['changelog'];
          final changelogStr = changelog is List ? changelog.join('\n') : (changelog?.toString() ?? '');

          _latestOmiGlassFirmwareDetails = {
            'version': cleanVersion,
            'download_url': firmwareDetails['zip_url'] ?? '',
            'changelog': changelogStr,
          };
        }

        // Fetch latest stable version for rollback comparison
        try {
          var stableDetails = await getStableFirmwareVersion(deviceModelNumber: pairedDevice?.modelNumber ?? '');
          var stableVersion = stableDetails['version']?.toString() ?? '';
          if (stableVersion.startsWith('v')) stableVersion = stableVersion.substring(1);
          _latestStableFirmwareVersion = stableVersion;
        } catch (e) {
          Logger.debug('Error fetching stable firmware version: $e');
        }

        notifyListeners();
        return hasUpdate;
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

  // Track if user is currently viewing a firmware update page
  bool _isOnFirmwareUpdatePage = false;
  void setOnFirmwareUpdatePage(bool value) {
    _isOnFirmwareUpdatePage = value;
  }

  void showFirmwareUpdateDialog(BuildContext context) {
    if (!_havingNewFirmware ||
        !SharedPreferencesUtil().showFirmwareUpdateDialog ||
        _isFirmwareUpdateInProgress ||
        _isFirmwareDialogShowing ||
        _isOnFirmwareUpdatePage) {
      return;
    }

    _isFirmwareDialogShowing = true;
    showDialog(
      context: context,
      builder: (context) => ConfirmationDialog(
        title: context.l10n.firmwareUpdateAvailable,
        description: context.l10n.firmwareUpdateAvailableDescription(_latestFirmwareVersion),
        confirmText: context.l10n.update,
        cancelText: context.l10n.later,
        onConfirm: () {
          Navigator.of(context).pop();
          setFirmwareUpdateInProgress(true);
          if (_isOmiGlassDevice) {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (context) =>
                    OmiGlassOtaUpdate(device: pairedDevice, latestFirmwareDetails: _latestOmiGlassFirmwareDetails),
              ),
            );
          } else {
            Navigator.of(context).push(MaterialPageRoute(builder: (context) => FirmwareUpdate(device: pairedDevice)));
          }
        },
        onCancel: () {
          Navigator.of(context).pop();
        },
      ),
    ).then((_) {
      _isFirmwareDialogShowing = false;
    });
  }

  Future setisDeviceStorageSupport() async {
    if (connectedDevice == null) {
      isDeviceStorageSupport = false;
    } else {
      var storageFiles = await _getStorageList(connectedDevice!.id);
      isDeviceStorageSupport = storageFiles.isNotEmpty;
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
      case DeviceConnectionState.connecting:
        break;
      case DeviceConnectionState.disconnected:
        _connectDebouncer.cancel();
        // Check if this is the paired device or currently connected device
        // Coz connectedDevice and pairedDevice are the same but connectedDevice becomes null after disconnect
        if (deviceId == connectedDevice?.id || deviceId == pairedDevice?.id) {
          _disconnectDebouncer.run(onDeviceDisconnected);
        }
        break;
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
    setFirmwareUpdateInProgress(true);
    _bleDisconnectDevice(connectedDevice!);
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
