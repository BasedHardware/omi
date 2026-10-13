import 'dart:async';

import 'package:omi/services/devices/charge_start_tracker.dart';
import 'package:omi/services/devices/fully_charged_alert_gate.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';
import 'dart:io';

import 'package:flutter/material.dart';

import 'package:omi/ui/omi_routes.dart';
import 'package:omi/backend/http/api/device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/omiglass_ota_update.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/native_link_reconciler.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/telemetry/client_telemetry.dart';
import 'package:omi/services/battery_widget_service.dart';
import 'package:omi/services/wals/wal_syncs.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/firmware_update_build_policy.dart';
import 'package:omi/utils/firmware_update_check_session.dart';
import 'package:omi/utils/firmware_update_prompt_coordinator.dart';
import 'package:omi/utils/analytics/device_health_telemetry.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
import 'package:uuid/uuid.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';

typedef BleDiagnosticsLoader = Future<BleDeviceDiagnostics> Function(String deviceId);
typedef FindDeviceRunner = Future<bool> Function(BtDevice device);

class DeviceProvider extends ChangeNotifier implements IDeviceServiceSubsciption {
  CaptureProvider? captureProvider;
  LocalRecordingsProvider? localRecordingsProvider;

  bool isConnecting = false;
  bool isConnected = false;
  bool isDeviceStorageSupport = false;
  bool supportsMultiFileSync = SharedPreferencesUtil().deviceSupportsMultiFileSync;

  // Latest on-device ring-buffer storage snapshot (firmware 3.0.20+ only).
  // Surfaced on the Auto Sync page as a storage-usage indicator. Null when the
  // device predates the ring protocol or hasn't been read yet.
  RingStatus? _ringStatus;
  RingStatus? get ringStatus => _ringStatus;

  BtDevice? connectedDevice;
  BtDevice? pairedDevice;

  /// Capability-normalized identity for capture/home restarts.
  ///
  /// `getDeviceInfo()` reclassifies image-stream hardware as
  /// [DeviceType.openglass] on [pairedDevice]. Home and speech-profile
  /// restarts must prefer that over the advertising-time [connectedDevice]
  /// so the Omi-button gate matches Device Settings.
  BtDevice? get capabilityNormalizedDevice {
    final connected = connectedDevice;
    final paired = pairedDevice;
    if (paired != null && (connected == null || paired.id == connected.id)) {
      return paired;
    }
    return connected ?? paired;
  }

  DateTime? _deviceSessionStartedAt;
  String? _deviceSessionOperationId;
  final BleDiagnosticsLoader _bleDiagnosticsLoader;
  final FindDeviceRunner _findDeviceRunner;
  final Future<DeviceConnection?> Function(String) _chargingConnectionLoader;
  final CaptureWedgeMonitor _wedgeMonitor;
  final Set<String> _intentionalDisconnectDevices = {};

  void markDisconnectIntentional(String deviceId) {
    _intentionalDisconnectDevices.add(deviceId);
    _wedgeMonitor.dismissDeviceEpisode(deviceId);
  }

  Future<bool>? _findDeviceRequest;
  StreamSubscription<List<int>>? _bleBatteryLevelListener;
  StreamSubscription? _bleChargingStatusListener;
  int batteryLevel = -1;
  bool isCharging = false;
  final _chargeStarts = ChargeStartTracker();
  late final FullyChargedAlertGate _fullyChargedAlert;
  int _lastNotifiedBatteryLevel = -1;
  DateTime? _lastBatteryNotifyTime;
  bool _hasLowBatteryAlerted = false;
  bool _havingNewFirmware = false;
  bool get havingNewFirmware =>
      _havingNewFirmware && pairedDevice != null && isConnected && _allowsFirmwareUpdateForPairedDevice;

  // Track firmware update state to prevent showing dialog during updates
  final FirmwareUpdateCheckSessionGuard _firmwareUpdateCheckSessionGuard = FirmwareUpdateCheckSessionGuard();
  FirmwareUpdateCheckSession? _checkingFirmwareSession;
  String? _firmwareUpdateDeviceId;
  final FirmwareUpdatePromptCoordinator _firmwareUpdatePromptCoordinator = FirmwareUpdatePromptCoordinator();
  bool _pairingLostDialogShowing = false;
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
  Timer? _disconnectRescanTimer;
  Timer? _firmwarePromptTimer;
  Timer? _deviceHealthTimer;
  bool _isDisposed = false;
  final Debouncer _disconnectDebouncer = Debouncer(delay: const Duration(milliseconds: 500));
  final Debouncer _connectDebouncer = Debouncer(delay: const Duration(milliseconds: 100));

  void Function(BtDevice device)? onDeviceConnected;
  void Function(BtDevice device, int fileCount, int totalBytes)? onOfflineDataDetected;

  /// Bumped on [clearUserData]. Capture at admission; never re-read after an
  /// await. Adopting the live counter would publish a retired connect into the
  /// session that replaced it.
  int _sessionGeneration = 0;

  /// Connect continuation admitted under this generation. WAL attach,
  /// coordinator wake, and capture streaming must use this token, not
  /// `_sessionGeneration` at callback time. -1 means no admitted connect.
  int _admittedConnectGeneration = -1;
  late final NativeLinkReconciler nativeLink = NativeLinkReconciler(this);
  (DeviceConnection, int)? _admittedLink;
  // When a resume reconcile arms a readoption, admissions for that device are
  // constrained to the pairing the reconcile probed: the persisted pairing
  // must still name that device when an admission or its async continuation
  // runs, or a pairing persisted in the windows between (an input picker
  // seeding another microphone) is silently overwritten. Armed before the
  // link starts forming, so the constraint holds for whichever connected
  // event queues the admission.
  String? _readoptExpectedPair;

  DeviceProvider({
    BleDiagnosticsLoader? bleDiagnosticsLoader,
    FindDeviceRunner? findDeviceRunner,
    CaptureWedgeMonitor? captureWedgeMonitor,
    Future<DeviceConnection?> Function(String)? chargingConnectionLoader,
    DateTime Function()? clock,
    Duration Function()? monotonicNow,
    Duration? fullyChargedMinimumDwell,
    FullyChargedNotification? fullyChargedNotification,
    FullyChargedLevelMismatch? fullyChargedLevelMismatch,
  })  : _bleDiagnosticsLoader = bleDiagnosticsLoader ?? BleHostApi().getDeviceDiagnostics,
        _findDeviceRunner = findDeviceRunner ?? _defaultFindDeviceRunner,
        _chargingConnectionLoader = chargingConnectionLoader ?? ServiceManager.instance().device.ensureConnection,
        _wedgeMonitor = captureWedgeMonitor ?? CaptureWedgeMonitor.instance {
    _fullyChargedAlert = FullyChargedAlertGate(
      now: clock ?? DateTime.now,
      monotonicNow: monotonicNow,
      minimumDwell: fullyChargedMinimumDwell ?? FullyChargedAlertGate.minimumOnChargerDwell,
      onFullyCharged: (level) {
        final deviceId = _fullyChargedAlert.lastFiredDeviceId;
        if (deviceId == null) return;
        if (fullyChargedNotification != null) {
          fullyChargedNotification(level);
          _fullyChargedAlert.markPresented(deviceId);
          return;
        }
        unawaited(_presentFullyChargedNotification(deviceId));
      },
      onLevelMismatch: ({required int notifiedAtLevel, required int correctedLevel}) {
        _recordFullyChargedLevelMismatch(notifiedAtLevel: notifiedAtLevel, correctedLevel: correctedLevel);
        fullyChargedLevelMismatch?.call(notifiedAtLevel: notifiedAtLevel, correctedLevel: correctedLevel);
      },
    );
    ServiceManager.instance().device.subscribe(this, this);
    BleBridge.instance.pairingLostCallback = _handlePairingLost;
  }

  bool _isCurrent(int generation) => !_isDisposed && generation >= 0 && generation == _sessionGeneration;

  void _detachAccountOwnedDeviceBindings() {
    try {
      final syncs = ServiceManager.instance().wal.getSyncs();
      syncs.setDevice(null);
      syncs.sdcard.setDevice(null);
      syncs.flashPage.setDevice(null);
      syncs.storage.setDevice(null);
      syncs.ring.setDevice(null);
    } catch (_) {
      // Tests and early construction may not have WAL ready.
    }
    captureProvider?.updateRecordingDevice(null);
  }

  /// Invalidates in-flight connect, firmware, and auto-sync work. The BLE link
  /// is hardware and is not torn down; WAL attach, coordinator wake, and other
  /// account publication from the retired generation must not land.
  void clearUserData() {
    _sessionGeneration++;
    _admittedLink = null;
    _readoptExpectedPair = null;
    _deviceHealthTimer?.cancel();
    _deviceHealthTimer = null;
    _admittedConnectGeneration = -1;
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = null;
    _bleChargingStatusListener?.cancel();
    _bleChargingStatusListener = null;
    _fullyChargedAlert.reset();
    _discoveryTimer?.cancel();
    _discoveryTimer = null;
    _disconnectDebouncer.cancel();
    _connectDebouncer.cancel();
    _findDeviceRequest = null;
    _intentionalDisconnectDevices.clear();
    _wedgeMonitor.reset();
    _firmwareUpdateCheckSessionGuard.invalidate();
    _firmwareUpdatePromptCoordinator.invalidatePresentation();
    _checkingFirmwareSession = null;
    _havingNewFirmware = false;
    _latestFirmwareVersion = '';
    _latestStableFirmwareVersion = '';
    _latestOmiGlassFirmwareDetails = {};
    _ringStatus = null;
    isConnecting = false;
    _detachAccountOwnedDeviceBindings();
    notifyListeners();
  }

  void _handlePairingLost() {
    final generation = _sessionGeneration;
    ServiceManager.instance().device.requireStaleBondRecovery();
    _discoveryTimer?.cancel();
    updateConnectingStatus(false);
    final pairedDeviceId = SharedPreferencesUtil().btDevice.id;
    if (pairedDeviceId.isNotEmpty) {
      unawaited(ServiceManager.instance().device.disconnectDevice(pairedDeviceId));
    }
    _showPairingLostDialog(generation);
  }

  void _showPairingLostDialog(int generation) {
    if (_pairingLostDialogShowing) return;

    void present() {
      if (!_isCurrent(generation) || _pairingLostDialogShowing) return;
      final context = globalNavigatorKey.currentContext;
      if (context == null || !context.mounted) {
        WidgetsBinding.instance.addPostFrameCallback((_) => present());
        return;
      }

      _pairingLostDialogShowing = true;
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        // One answer only (acknowledge), so an alert, not a confirmation.
        builder: (dialogContext) => OmiAlertDialog(
          title: dialogContext.l10n.bluetooth,
          message: dialogContext.l10n.deviceUnpairedMessage,
          actions: [
            OmiDialogAction(
              label: dialogContext.l10n.gotIt,
              isDefault: true,
              onPressed: () => Navigator.of(dialogContext).pop(),
            ),
          ],
        ),
      ).whenComplete(() => _pairingLostDialogShowing = false);
    }

    present();
  }

  void setProviders(CaptureProvider provider, LocalRecordingsProvider recordingsProvider) {
    captureProvider = provider;
    localRecordingsProvider = recordingsProvider;
    // Action targets only: device read models do not derive from these dependencies.
  }

  Future<void> setConnectedDevice(BtDevice? device) async {
    final generation = _sessionGeneration;
    final endedDevice = device == null ? (pairedDevice ?? connectedDevice) : null;
    final sessionStartedAt = _deviceSessionStartedAt;
    final sessionOperationId = _deviceSessionOperationId;
    final now = DateTime.now();
    final capture = captureProvider;
    final liveCaptureDevice = capture?.recordingDevice;
    final endedDeviceWasLiveCapture = endedDevice != null &&
        endedDevice.id == liveCaptureDevice?.id &&
        capture!.recordingState == RecordingState.deviceRecord &&
        !capture.isPaused &&
        !SharedPreferencesUtil().batchModeEnabled;
    final endedSessionWasIntentional = endedDevice != null && _intentionalDisconnectDevices.remove(endedDevice.id);
    final isNewConnection = device != null && connectedDevice?.id != device.id;
    connectedDevice = device;
    pairedDevice = device;
    if (isNewConnection) {
      if (_firmwareUpdateDeviceId != null && _firmwareUpdateDeviceId != device.id) {
        _firmwareUpdatePromptCoordinator.clearAvailableVersion(invalidateDeferral: true);
      }
      _firmwareUpdateDeviceId = device.id;
      _firmwareUpdateCheckSessionGuard.start(device.id);
      _deviceSessionStartedAt = now;
      _deviceSessionOperationId = const Uuid().v4();
    } else if (device == null) {
      _firmwareUpdateCheckSessionGuard.invalidate();
      _deviceSessionStartedAt = null;
      _deviceSessionOperationId = null;
    }
    await getDeviceInfo();
    if (!_isCurrent(generation)) return;
    if (isNewConnection) {
      PlatformManager.instance.analytics.deviceConnected(device);
    }
    if (device != null) {
      final firstPairedAt = await _markDevicePaired(device.id, generation);
      if (!_isCurrent(generation)) return;
      if (firstPairedAt != null) {
        PlatformManager.instance.analytics.devicePaired(firstPairedAt);
      }
    }
    if (endedDevice != null && sessionStartedAt != null) {
      if (endedDeviceWasLiveCapture) {
        _wedgeMonitor.onBleSessionEnded(
          deviceId: endedDevice.id,
          deviceType: endedDevice.type,
          duration: now.difference(sessionStartedAt),
          intentional: endedSessionWasIntentional,
        );
      }
      BleDisconnectEvent? disconnect;
      try {
        final diagnostics = await _bleDiagnosticsLoader(endedDevice.id);
        if (!_isCurrent(generation)) return;
        final sessionStartMs = sessionStartedAt.millisecondsSinceEpoch;
        for (final event in diagnostics.disconnectHistory.reversed) {
          if (event.timestamp >= sessionStartMs) {
            disconnect = event;
            break;
          }
        }
      } catch (_) {
        if (!_isCurrent(generation)) return;
        // Native diagnostics are best-effort; local timing still makes the event useful.
      }
      if (!_isCurrent(generation)) return;
      final sessionDuration = disconnect != null && disconnect.connectionDurationMs > 0
          ? Duration(milliseconds: disconnect.connectionDurationMs)
          : now.difference(sessionStartedAt);
      PlatformManager.instance.analytics.deviceSessionEnded(
        device: endedDevice,
        duration: sessionDuration,
        reason: disconnect?.reason,
        hciReasonCode: disconnect?.reasonCode,
      );
      try {
        ClientTelemetry.instance.observeDeviceSession(
          operationId: sessionOperationId ?? const Uuid().v4(),
          analyticsVendor: endedDevice.type.analyticsVendor,
          duration: sessionDuration,
          reason: disconnect?.reason,
          hciReasonCode: disconnect?.reasonCode,
          intentional: endedSessionWasIntentional,
          recoveryOutcome: endedSessionWasIntentional ? 'none' : 'unknown',
        );
      } catch (_) {}
    }
    if (!_isCurrent(generation)) return;
    Logger.debug('setConnectedDevice: $device');
    notifyListeners();
  }

  Future<String?> _markDevicePaired(String deviceId, int generation) async {
    if (!_isCurrent(generation)) return null;
    final preferences = SharedPreferencesUtil();
    final uid = preferences.uid;
    if (uid.isEmpty || deviceId.isEmpty) return null;

    final pairedDevicesKey = 'pairedDeviceIds:$uid';
    final pairedDeviceIds = preferences.getStringList(pairedDevicesKey);
    if (pairedDeviceIds.contains(deviceId)) return null;

    final firstPairedAtKey = 'firstPairedAt:$uid';
    var firstPairedAt = preferences.getString(firstPairedAtKey);
    if (firstPairedAt.isEmpty) {
      firstPairedAt = DateTime.now().toUtc().toIso8601String();
      await preferences.saveString(firstPairedAtKey, firstPairedAt);
      if (!_isCurrent(generation)) return null;
    }
    if (!await preferences.saveStringList(pairedDevicesKey, [...pairedDeviceIds, deviceId])) return null;
    if (!_isCurrent(generation) || preferences.uid != uid) return null;
    return firstPairedAt;
  }

  Future getDeviceInfo() async {
    final generation = _sessionGeneration;
    if (connectedDevice != null) {
      if (pairedDevice?.firmwareRevision != null && pairedDevice?.firmwareRevision != 'Unknown') {
        if (!_isCurrent(generation)) return;
        _persistPairedDevice();
        return;
      }
      var connection = await ServiceManager.instance().device.ensureConnection(connectedDevice!.id);
      if (!_isCurrent(generation)) return;
      pairedDevice = await connectedDevice?.getDeviceInfo(connection);
      if (!_isCurrent(generation)) return;
      _persistPairedDevice();
    } else {
      if (!_isCurrent(generation)) return;
      if (SharedPreferencesUtil().btDevice.id.isEmpty) {
        pairedDevice = BtDevice.empty();
      } else {
        pairedDevice = SharedPreferencesUtil().btDevice;
      }
    }
    if (!_isCurrent(generation)) return;
    notifyListeners();
  }

  /// Publishes the paired device to preferences unless a readoption armed a
  /// pairing constraint and the persisted pairing has since moved on: the
  /// armed publication belongs to the probe-time pairing, and writing here
  /// would silently overwrite the newer choice (an input picker's selection).
  void _persistPairedDevice() {
    if (_readoptPairMovedOn(pairedDevice!.id)) {
      Logger.debug('Skipping paired-device persist: pairing moved on from $_readoptExpectedPair');
      return;
    }
    SharedPreferencesUtil().btDevice = pairedDevice!;
  }

  /// True when a readoption armed a pairing constraint for [deviceId] and the
  /// persisted pairing no longer names it.
  bool _readoptPairMovedOn(String deviceId) =>
      _readoptExpectedPair == deviceId && SharedPreferencesUtil().btDevice.id != deviceId;

  /// Hardware find-device LED. Not account publication; left unfenced.
  Future<bool> findDevice() {
    final device = connectedDevice ?? pairedDevice;
    if (!isConnected ||
        device == null ||
        device.type != DeviceType.omi ||
        FirmwareUpdateBuildPolicy.current.isOpenGlassDevice(device)) {
      return Future.value(false);
    }

    final existingRequest = _findDeviceRequest;
    if (existingRequest != null) return existingRequest;

    late final Future<bool> request;
    request = _runFindDevice(device).whenComplete(() {
      if (identical(_findDeviceRequest, request)) {
        _findDeviceRequest = null;
      }
    });
    _findDeviceRequest = request;
    return request;
  }

  Future<bool> _runFindDevice(BtDevice device) async {
    try {
      return await _findDeviceRunner(device);
    } catch (e) {
      Logger.debug('DeviceProvider: Failed to play find-device pattern: $e');
      return false;
    }
  }

  static Future<bool> _defaultFindDeviceRunner(BtDevice device) async {
    final connection = await ServiceManager.instance().device.ensureConnection(device.id).timeout(
      const Duration(seconds: 5),
      onTimeout: () {
        Logger.debug('DeviceProvider: Timed out finding the active device connection');
        return null;
      },
    );
    return await connection?.playFindDevicePattern() ?? false;
  }

  Future _bleDisconnectDevice(BtDevice btDevice) async {
    await ServiceManager.instance().device.disconnectDevice(btDevice.id);
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

  initiateBleBatteryListener() async {
    final generation = _sessionGeneration;
    if (!_isCurrent(generation) || connectedDevice == null) {
      return;
    }
    final batteryDeviceId = connectedDevice!.id;
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = await _getBleBatteryLevelListener(
      batteryDeviceId,
      onBatteryLevelChange: (int value) {
        if (!_isCurrent(generation)) return;
        if (batteryLevel != value) {
          batteryLevel = value;
          BatteryWidgetService().updateBatteryInfo(
            deviceName: connectedDevice?.name ?? '',
            batteryLevel: value,
            deviceType: connectedDevice?.type.name ?? 'omi',
            isConnected: true,
          );
        }
        if (batteryLevel < 20 && !_hasLowBatteryAlerted) {
          _hasLowBatteryAlerted = true;
          final ctx = globalNavigatorKey.currentContext;
          unawaited(NotificationService.instance.createNotification(
            title: ctx?.l10n.lowBatteryAlertTitle ?? "Low Battery Alert",
            body: ctx?.l10n.lowBatteryAlertBody(value) ?? "Your battery is at $value%. Time for a recharge! 🔋",
          ));
        } else if (batteryLevel > 20) {
          _hasLowBatteryAlerted = false;
        }
        // Every callback is a sample. A stale 100 from before this charge cannot
        // notify; attribute it to the device this listener was opened for.
        _fullyChargedAlert.onBatterySample(batteryDeviceId, value);
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
    if (!_isCurrent(generation)) {
      _bleBatteryLevelListener?.cancel();
      _bleBatteryLevelListener = null;
      return;
    }
    notifyListeners();
  }

  Future<void> initiateChargingStatusListener({bool allowCaptureResume = true}) async {
    final generation = _sessionGeneration;
    if (!_isCurrent(generation) || connectedDevice == null) return;
    _bleChargingStatusListener?.cancel();

    var connection = await _chargingConnectionLoader(connectedDevice!.id);
    if (!_isCurrent(generation)) return;
    if (connection == null) return;
    // TODO(astra): non-Omi connections, including Friend Pendant, expose no charging-status API. (#5491)
    if (connection is! OmiDeviceConnection) return;

    final currentStatus = await connection.readChargingStatus();
    if (!_isCurrent(generation)) return;
    final allowInitialResume = allowCaptureResume && !SyncWakeScope.syncOnly;
    var initialObservationDone = currentStatus != null;
    // Failed reads are unknown: retain the last successful observation and UI state.
    if (currentStatus != null) {
      final chargeStarted = _chargeStarts.observe(connectedDevice!.id, currentStatus);
      // An initial read made by a sync wake is observation, not a charge-start event.
      if (chargeStarted && allowInitialResume) captureProvider?.onChargingStarted();
      final wasCharging = isCharging;
      if (isCharging != currentStatus) {
        isCharging = currentStatus;
        notifyListeners();
      }
      BatteryWidgetService().updateChargingState(currentStatus);
      _noteChargingForFullyChargedAlert(currentStatus, wasCharging: wasCharging);
    }

    _bleChargingStatusListener = await connection.getChargingStatusListener(
      onChargingStatusChange: (bool charging) {
        if (!_isCurrent(generation)) return;
        // Firmware notifies its current byte on subscribe. After a failed read,
        // that first sample inherits the initial read's observation-only gate.
        // A later scope must defer transport work, not consume an authorized
        // charge edge. Capture's scope-drop reconciliation owns that deferral.
        final allowResume = initialObservationDone || allowInitialResume;
        initialObservationDone = true;
        final chargeStarted = _chargeStarts.observe(connectedDevice!.id, charging);
        if (chargeStarted && allowResume) captureProvider?.onChargingStarted();
        final wasCharging = isCharging;
        if (isCharging != charging) {
          isCharging = charging;
          BatteryWidgetService().updateChargingState(charging);
          notifyListeners();
        }
        _noteChargingForFullyChargedAlert(charging, wasCharging: wasCharging);
      },
    );
    if (!_isCurrent(generation)) {
      _bleChargingStatusListener?.cancel();
      _bleChargingStatusListener = null;
    }
  }

  Future<void> _presentFullyChargedNotification(String deviceId) async {
    final generation = _sessionGeneration;
    final ctx = globalNavigatorKey.currentContext;
    final presented = await NotificationService.instance.createNotification(
      title: ctx?.l10n.batteryFullyChargedTitle ?? "Omi is fully charged",
      body: ctx?.l10n.batteryFullyChargedBody ?? "Your Omi device is fully charged. Feel free to unplug!",
    );
    if (!_isCurrent(generation) || !presented) return;
    _fullyChargedAlert.markPresented(deviceId);
  }

  void _recordFullyChargedLevelMismatch({required int notifiedAtLevel, required int correctedLevel}) {
    // No device-notification analytics event exists. Logged once per cycle,
    // only after createNotification's permission check. An attempt, not delivery.
    Logger.debug(
      'Fully charged notification mismatch attempt: fully_charged_notified_at_level=$notifiedAtLevel corrected_level=$correctedLevel',
    );
  }

  /// False→true restarts this device's dwell, including a reconnect. Link loss
  /// clears [isCharging] without counting as an unplug.
  void _noteChargingForFullyChargedAlert(bool charging, {required bool wasCharging}) {
    final deviceId = connectedDevice?.id;
    if (deviceId == null || deviceId.isEmpty) return;
    if (!charging) {
      _fullyChargedAlert.onUnplugged(deviceId);
      return;
    }
    if (!wasCharging || !_fullyChargedAlert.hasChargeWindowFor(deviceId)) {
      _fullyChargedAlert.onChargeStarted(deviceId);
    }
  }

  @visibleForTesting
  DateTime? get fullyChargedChargeStartedAt {
    final id = connectedDevice?.id;
    return id == null ? null : _fullyChargedAlert.chargeStartedAtFor(id);
  }

  @visibleForTesting
  bool get hasFullyChargedAlerted {
    final id = connectedDevice?.id;
    return id != null && _fullyChargedAlert.hasAlertedFor(id);
  }

  @visibleForTesting
  void onFullyChargedBatterySampleForTesting(int level, {DateTime? at}) {
    final id = connectedDevice?.id;
    if (id != null) _fullyChargedAlert.onBatterySample(id, level, at: at);
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
  /// Hardware connect is not account publication; `_handleDeviceConnected` is.
  Future<void> initiateConnection(String caller, {bool boundDeviceOnly = false}) async {
    if (_isDisposed) return;
    final pairedDeviceId = SharedPreferencesUtil().btDevice.id;
    if (pairedDeviceId.isNotEmpty) {
      unawaited(DeviceHealthTelemetry.maybeEmit(SharedPreferencesUtil().btDevice));
    }

    if (ServiceManager.instance().device.staleBondRecoveryRequired) {
      Logger.debug('initiateConnection ($caller): blocked until stale bond recovery');
      return;
    }

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
    if (_isDisposed) return;
    _discoveryTimer?.cancel();
    _runDiscoveryScan();
    _discoveryTimer = Timer.periodic(const Duration(seconds: 10), (_) => _runDiscoveryScan());
  }

  void stopDiscoveryScanning() {
    _discoveryTimer?.cancel();
    _discoveryTimer = null;
  }

  @visibleForTesting
  void startDiscoveryScanningForTesting() => _startDiscoveryScanning();

  @visibleForTesting
  bool get hasActiveDiscoveryTimer => _discoveryTimer?.isActive ?? false;

  Future<void> _runDiscoveryScan() async {
    if (SharedPreferencesUtil().btDevice.id.isNotEmpty || isConnected) {
      _discoveryTimer?.cancel();
      return;
    }
    final deviceService = ServiceManager.instance().device;
    if (deviceService.status == DeviceServiceStatus.ready) {
      try {
        await deviceService.discover();
      } catch (e) {
        Logger.debug('_runDiscoveryScan: discover failed: $e');
      }
    }
  }

  Future scanAndConnectToDevice() async {
    final generation = _sessionGeneration;
    updateConnectingStatus(true);
    if (!_isCurrent(generation)) return;
    if (isConnected && connectedDevice != null) {
      updateConnectingStatus(false);
      return;
    }

    ServiceManager.instance().device.clearStaleBondRecoveryRequirement();

    final pairedDeviceId = SharedPreferencesUtil().btDevice.id;
    if (pairedDeviceId.isEmpty) {
      if (!_isCurrent(generation)) return;
      updateConnectingStatus(false);
      return;
    }

    try {
      var connection = await ServiceManager.instance().device.ensureConnection(pairedDeviceId, force: true);
      if (!_isCurrent(generation)) return;
      if (connection != null) {
        await setConnectedDevice(connection.device);
        if (!_isCurrent(generation)) return;
        await setisDeviceStorageSupport();
        if (!_isCurrent(generation)) return;
        SharedPreferencesUtil().deviceName = connection.device.name;
        setIsConnected(true);
      }
    } catch (e) {
      if (!_isCurrent(generation)) return;
      Logger.debug('scanAndConnectToDevice: connection failed: $e');
    }

    if (!_isCurrent(generation)) return;
    updateConnectingStatus(false);
    notifyListeners();
  }

  void updateConnectingStatus(bool value) {
    isConnecting = value;
    notifyListeners();
  }

  void setIsConnected(bool value) {
    isConnected = value;
    // Every path that drops the mirror must allow the live link to be re-admitted.
    if (!value) _admittedLink = null;
    if (isConnected) {
      _discoveryTimer?.cancel();
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _isDisposed = true;
    _sessionGeneration++;
    nativeLink.dispose();
    _deviceHealthTimer?.cancel();
    _deviceHealthTimer = null;
    _admittedConnectGeneration = -1;
    _firmwareUpdatePromptCoordinator.invalidatePresentation();
    if (BleBridge.instance.pairingLostCallback == _handlePairingLost) {
      BleBridge.instance.pairingLostCallback = null;
    }
    _bleBatteryLevelListener?.cancel();
    _bleChargingStatusListener?.cancel();
    _fullyChargedAlert.dispose();
    _discoveryTimer?.cancel();
    _disconnectRescanTimer?.cancel();
    _firmwarePromptTimer?.cancel();
    _deviceHealthTimer?.cancel();
    _disconnectDebouncer.cancel();
    _connectDebouncer.cancel();
    ServiceManager.instance().device.unsubscribe(this);
    super.dispose();
  }

  void onDeviceDisconnected() async {
    final generation = _sessionGeneration;
    // Capture before setConnectedDevice(null) clears both device references.
    final disconnectedDeviceId = pairedDevice?.id ?? connectedDevice?.id;
    Logger.debug('onDisconnected inside: $connectedDevice');
    _havingNewFirmware = false;
    _firmwareUpdatePromptCoordinator.invalidatePresentation();
    _bleChargingStatusListener?.cancel();
    // Link loss is not an unplug. Keep this device's alert; another device does not inherit it.
    if (disconnectedDeviceId != null) _fullyChargedAlert.onLinkLost(disconnectedDeviceId);
    isCharging = false;
    BatteryWidgetService().updateChargingState(false);
    unawaited(setConnectedDevice(null));
    unawaited(setisDeviceStorageSupport());
    setIsConnected(false);
    updateConnectingStatus(false);

    // Recovery changes the link, not the user's capture intent. Retain the
    // session (and Resume control) while native reports the physical link down.
    if (disconnectedDeviceId == null || !BleBridge.instance.preservesCaptureIntent(disconnectedDeviceId)) {
      captureProvider?.updateRecordingDevice(null);
    }

    // Batch mode: the native writer finalizes the in-progress recording on
    // disconnect (.bin.part -> .bin). Rescan shortly after the rename completes
    // so the new recording shows up in the conversations list.
    Future.delayed(const Duration(seconds: 1), () {
      if (!_isCurrent(generation)) return;
      localRecordingsProvider?.refresh();
    });

    // Wals
    try {
      ServiceManager.instance().wal.getSyncs().sdcard.setDevice(null);
      ServiceManager.instance().wal.getSyncs().flashPage.setDevice(null);
    } catch (_) {
      // Tests and early construction may not have WAL ready.
    }

    if (!_isCurrent(generation)) return;

    PlatformManager.instance.crashReporter.logInfo('Omi Device Disconnected');

    unawaited(_trackDeviceDisconnected(disconnectedDeviceId, generation));
    BatteryWidgetService().updateBatteryInfo(
      deviceName: SharedPreferencesUtil().deviceName,
      batteryLevel: -1,
      deviceType: 'omi',
      isConnected: false,
    );

    // #3328: do not create a user-facing disconnect / "wear your Omi" push.
    // Onboard storage keeps recording across BLE drops; backend daily wear
    // reminder is also off.

    // Notify interactive device onboarding of disconnect
    captureProvider?.deviceOnboardingProvider?.onDeviceDisconnected();
  }

  /// Emits the enriched Device Disconnected analytics event with the reason
  /// native persisted for this disconnect. Both platforms persist the event
  /// before notifying Dart, so the freshest history entry is the one that
  /// triggered this callback; diagnostics are best-effort and degrade to
  /// `unknown` when the read fails (non-BLE devices, early teardown).
  Future<void> _trackDeviceDisconnected(String? deviceId, int generation) async {
    BleDisconnectEvent? latest;
    if (deviceId != null && deviceId.isNotEmpty) {
      try {
        final diagnostics = await _bleDiagnosticsLoader(deviceId);
        if (!_isCurrent(generation)) return;
        final history = diagnostics.disconnectHistory;
        if (history.isNotEmpty) latest = history.last;
      } catch (_) {
        if (!_isCurrent(generation)) return;
        // Native diagnostics are best-effort; emit without reason detail.
      }
    }
    if (!_isCurrent(generation)) return;
    PlatformManager.instance.analytics.deviceDisconnected(
      reason: latest?.reason,
      reasonCode: latest?.reasonCode,
      appState: latest?.appState,
    );
  }

  Future<(String, bool, String, Map)> shouldUpdateFirmware() async {
    if (pairedDevice == null || connectedDevice == null) {
      return ('No paired device is connected', false, '', {});
    }

    var device = pairedDevice!;
    if (device.firmwareRevision.isEmpty) {
      // BLE read of the firmware-revision characteristic failed. Skip the
      // upgrade check rather than asking the backend what's "newer than
      // unknown" — that path returns a misleading legacy version.
      return ('Unable to determine current firmware version', false, '', {});
    }
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

  void _onDeviceConnected(BtDevice device, int generation) async {
    final syncOnly = SyncWakeScope.syncOnly;
    Logger.debug('_onConnected inside: $connectedDevice');
    if (!_isCurrent(generation)) return;
    final deviceSetup = setConnectedDevice(device);
    final connectionSession = _firmwareUpdateCheckSessionGuard.capture();
    await deviceSetup;
    if (!_isCurrent(generation)) return;
    if (connectionSession == null || !_isCurrentDeviceSession(connectionSession)) {
      Logger.debug('Discarding device setup continuation from a stale connection session');
      return;
    }
    // A readoption's authorization is only as fresh as its last check: device
    // setup awaits BLE work, and a pairing persisted during that window (an
    // input picker seeding another microphone) must not get battery, capture,
    // and WAL side effects started for the retired pairing.
    if (_readoptPairMovedOn(device.id)) {
      Logger.debug('Discarding device setup continuation of ${device.id}: pairing moved on during setup');
      return;
    }

    final normalizedDevice = pairedDevice ?? device;
    if (captureProvider != null) {
      captureProvider?.updateRecordingDevice(normalizedDevice);
    }

    await setisDeviceStorageSupport();
    if (!_isCurrent(generation)) return;
    setIsConnected(true);

    // Read initial battery level
    int currentLevel = await _retrieveBatteryLevel(device.id);
    if (!_isCurrent(generation)) return;
    if (_readoptPairMovedOn(device.id)) {
      Logger.debug('Discarding readoption of ${device.id}: pairing moved on before side effects');
      return;
    }
    if (currentLevel != -1) {
      batteryLevel = currentLevel;
      BatteryWidgetService().updateBatteryInfo(
        deviceName: device.name,
        batteryLevel: currentLevel,
        deviceType: device.type.name,
        isConnected: true,
      );
    }

    // Anchor the charge-start edge before subscribing to battery so a
    // subscribe snapshot is a sample after the edge, not a stale cache.
    await initiateChargingStatusListener(allowCaptureResume: !syncOnly);
    if (!_isCurrent(generation)) return;
    await initiateBleBatteryListener();
    if (!_isCurrent(generation)) return;
    if (batteryLevel != -1 && batteryLevel < 20) {
      _hasLowBatteryAlerted = false;
    }
    updateConnectingStatus(false);
    if (!syncOnly) await captureProvider?.streamDeviceRecording(device: normalizedDevice);
    if (!_isCurrent(generation)) return;

    await getDeviceInfo();
    if (!_isCurrent(generation)) return;
    if (_readoptPairMovedOn(device.id)) {
      Logger.debug('Discarding readoption of ${device.id}: pairing moved on before final publication');
      return;
    }
    SharedPreferencesUtil().deviceName = device.name;

    // getDeviceInfo() may have reclassified the discovery object — an Omi-typed
    // Glass unit becomes DeviceType.openglass once hasImageStream is read. Push
    // the capability-normalized paired device so consumers of the recording
    // device (e.g. the Omi button-actions gate) see the same identity as
    // pairedDevice instead of the raw advertising-time object.
    final normalizedPairedDevice = pairedDevice ?? normalizedDevice;
    if (captureProvider != null) {
      captureProvider?.updateRecordingDevice(normalizedPairedDevice);
    }

    // Wals — pass the firmware resolved by getDeviceInfo() above so background
    // discovery routes ring-buffer devices correctly; `device` here is the raw
    // connect object whose firmwareRevision is often still 'Unknown'.
    // Use the admitted connect token, never a fresh `_sessionGeneration` read:
    // recapturing here would attach WAL drain and wake the coordinator into
    // the session that replaced this connect.
    if (!_isCurrent(generation) || _admittedConnectGeneration != generation) return;
    final syncs = ServiceManager.instance().wal.getSyncs();
    syncs.setDevice(device, firmwareVersion: currentFirmwareVersion);
    syncs.sdcard.setDevice(device);
    syncs.flashPage.setDevice(device);
    syncs.storage.setDevice(device);
    syncs.ring.setDevice(device);

    // Device connection and inventory are a recovery wake, even when the
    // home page is not mounted. The coordinator serializes it with every
    // other foreground trigger and applies the auto-sync preference itself.
    unawaited(RecordingTransferCoordinator.instance.wake(WakeTrigger.deviceConnected));

    // Auto-sync: check if device has offline files
    unawaited(_checkAndStartAutoSync(device, generation));
    if (pairedDevice != null) unawaited(DeviceHealthTelemetry.maybeEmit(pairedDevice!));
    final healthDevice = pairedDevice;
    _deviceHealthTimer ??= Timer.periodic(const Duration(hours: 1), (_) {
      if (!_isCurrent(generation)) return;
      final current = pairedDevice ?? healthDevice;
      if (current != null) unawaited(DeviceHealthTelemetry.maybeEmit(current));
    });

    notifyListeners();

    // Check firmware updates
    _checkFirmwareUpdates(generation);

    if (Platform.isAndroid) {
      unawaited(_ensureCompanionAssociation(device, generation));
    }

    onDeviceConnected?.call(device);

    // Notify interactive device onboarding of reconnect
    captureProvider?.deviceOnboardingProvider?.onDeviceReconnected();
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

  Future<void> _checkAndStartAutoSync(BtDevice device, int generation) async {
    if (!_isCurrent(generation)) return;
    try {
      // Use firmware version as the reliable signal for multi-file support
      // Read from pairedDevice which has firmwareRevision populated by getDeviceInfo()
      final fwVersion = pairedDevice?.firmwareRevision ?? device.firmwareRevision;
      supportsMultiFileSync = _isFirmwareVersionSupported(fwVersion);
      SharedPreferencesUtil().deviceSupportsMultiFileSync = supportsMultiFileSync;
      notifyListeners();

      if (!supportsMultiFileSync) return;

      var connection = await ServiceManager.instance().device.ensureConnection(device.id);
      if (!_isCurrent(generation)) return;
      if (connection == null) return;

      // fw >= 3.0.20 speaks the ring-buffer protocol; auto-detect via the 16-byte
      // ring status read instead of the multi-file file-list endpoint (which the
      // ring firmware no longer serves).
      if (WalSyncs.isRingBufferFirmware(fwVersion)) {
        final ringStatus = await connection.getRingStatus();
        if (!_isCurrent(generation)) return;
        final info = connection.lastRingInfo;
        final coherent = _coherentRingStatus(ringStatus, info);
        if (coherent != null) {
          _ringStatus = coherent;
          notifyListeners();
        }
        if (coherent == null || coherent.unreadPackets <= 0) return;
        Logger.debug(
          'DeviceProvider: Ring auto-sync detected ${coherent.unreadPackets} unread packets (${coherent.usedBytes} bytes)',
        );
        onOfflineDataDetected?.call(device, coherent.unreadPackets, coherent.usedBytes);
        return;
      }

      final status = await connection.getStorageFileStats();
      if (!_isCurrent(generation)) return;
      if (status == null || status.fileCount == 0) return;

      Logger.debug('DeviceProvider: Auto-sync detected ${status.fileCount} files (${status.totalUsedBytes} bytes)');
      onOfflineDataDetected?.call(device, status.fileCount, status.totalUsedBytes);
    } catch (e) {
      if (!_isCurrent(generation)) return;
      Logger.debug('DeviceProvider: Auto-sync check failed: $e');
    }
  }

  /// Refresh the on-device ring-buffer storage snapshot for the storage-usage
  /// indicator. No-op on firmware < 3.0.20 (the ring protocol isn't served) or
  /// when there's no active connection. Safe to call from UI (e.g. on page open).
  Future<void> refreshRingStorageStatus() async {
    final generation = _sessionGeneration;
    try {
      final fwVersion = pairedDevice?.firmwareRevision ?? connectedDevice?.firmwareRevision;
      if (!WalSyncs.isRingBufferFirmware(fwVersion)) return;
      final deviceId = pairedDevice?.id ?? connectedDevice?.id;
      if (deviceId == null) return;
      final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (!_isCurrent(generation)) return;
      if (connection == null) return;
      final info = await connection.getRingInfo();
      if (!_isCurrent(generation)) return;
      final status = await connection.getRingStatus();
      if (!_isCurrent(generation)) return;
      final coherent = _coherentRingStatus(status, info ?? connection.lastRingInfo);
      if (coherent != null) {
        _ringStatus = coherent;
        notifyListeners();
      }
    } catch (e) {
      if (!_isCurrent(generation)) return;
      Logger.debug('DeviceProvider: refreshRingStorageStatus failed: $e');
    }
  }

  static RingStatus? _coherentRingStatus(RingStatus? status, RingInfo? info) {
    if (info == null) return status;
    final pkt = info.packetSize > 0 ? info.packetSize : 444;
    final infoUnread = info.unreadPackets;
    final infoFree = (info.capacityPackets - infoUnread).clamp(0, info.capacityPackets) * pkt;
    if (status == null) {
      return RingStatus(usedBytes: infoUnread * pkt, unreadPackets: infoUnread, freeBytes: infoFree, rtcValid: 0);
    }
    final free = status.freeBytes > 0 ? status.freeBytes : infoFree;
    return RingStatus(
      usedBytes: status.usedBytes,
      unreadPackets: status.unreadPackets,
      freeBytes: free,
      rtcValid: status.rtcValid,
    );
  }

  Future<void> _ensureCompanionAssociation(BtDevice device, int generation) async {
    if (!_isCurrent(generation)) return;
    try {
      if (SharedPreferencesUtil().companionAssociationPrompted) return;
      if (await BleHostApi().hasCompanionDeviceAssociation()) return;
      if (!_isCurrent(generation)) return;
      final ctx = globalNavigatorKey.currentContext;
      if (ctx == null || !ctx.mounted) return;
      SharedPreferencesUtil().companionAssociationPrompted = true;
      await showOmiAlert(
        ctx,
        title: ctx.l10n.improveConnectionTitle,
        message: ctx.l10n.improveConnectionContent,
        okLabel: ctx.l10n.improveConnectionAction,
      );
    } catch (e) {
      if (!_isCurrent(generation)) return;
      Logger.debug('CompanionDevice association check failed: $e');
    }
  }

  void _handleDeviceConnected(String deviceId, int generation, {bool requirePersistedPair = false}) async {
    if (!_isCurrent(generation)) return;
    _admittedConnectGeneration = generation;
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (!_isCurrent(generation)) return;
    if (connection == null) {
      return;
    }
    // A readoption authorized the persisted pairing at probe time, but this
    // admission waited on DeviceService: pairing may have moved on (an input
    // picker persisting a different microphone) and publishing the old device
    // would overwrite that choice in preferences and start its side effects.
    if ((requirePersistedPair || _readoptExpectedPair == deviceId) && SharedPreferencesUtil().btDevice.id != deviceId) {
      Logger.debug('Discarding readoption of $deviceId: pairing moved on before admission');
      return;
    }
    // One admission per physical connect: overlapping connected events (a
    // native connect still initializing, a resume reconcile) must not run
    // connect side effects twice.
    final link = (connection, connection.connectionEpoch);
    if (_admittedLink == link) return;
    _admittedLink = link;
    _onDeviceConnected(connection.device, generation);
  }

  void _checkFirmwareUpdates(int generation) async {
    if (!_isCurrent(generation)) return;
    if (!_allowsFirmwareUpdateForPairedDevice) {
      _havingNewFirmware = false;
      _firmwareUpdatePromptCoordinator.clearAvailableVersion(invalidateDeferral: true);
      return;
    }
    final checkSession = _firmwareUpdateCheckSessionGuard.capture();
    if (checkSession == null || !_isCurrentFirmwareCheckSession(checkSession)) {
      return;
    }
    if (_isFirmwareUpdateInProgress ||
        (_checkingFirmwareSession != null && _firmwareUpdateCheckSessionGuard.isCurrent(_checkingFirmwareSession!))) {
      return;
    }

    _checkingFirmwareSession = checkSession;
    try {
      final hasUpdate = await checkFirmwareUpdates(session: checkSession, generation: generation);
      if (!_isCurrent(generation) || !_isCurrentFirmwareCheckSession(checkSession)) {
        Logger.debug('Discarding firmware update prompt from a stale device session');
        return;
      }

      // Show firmware update dialog if needed
      if (hasUpdate && _havingNewFirmware) {
        // Use a small delay to ensure the UI is ready
        Future.delayed(const Duration(milliseconds: 500), () {
          if (!_isCurrent(generation) || !_isCurrentFirmwareCheckSession(checkSession)) return;
          final context = globalNavigatorKey.currentContext;
          if (context != null && context.mounted) {
            showFirmwareUpdateDialog(context);
          }
        });
      }
    } finally {
      if (identical(_checkingFirmwareSession, checkSession)) {
        _checkingFirmwareSession = null;
      }
    }
  }

  bool _isCurrentFirmwareCheckSession(FirmwareUpdateCheckSession session) {
    return _isCurrentDeviceSession(session) && isConnected;
  }

  bool _isCurrentDeviceSession(FirmwareUpdateCheckSession session) {
    return _firmwareUpdateCheckSessionGuard.isCurrent(session) &&
        connectedDevice?.id == session.deviceId &&
        pairedDevice?.id == session.deviceId;
  }

  bool get _isOmiGlassDevice => FirmwareUpdateBuildPolicy.current.isOpenGlassDevice(pairedDevice);

  bool get _allowsFirmwareUpdateForPairedDevice =>
      FirmwareUpdateBuildPolicy.current.allowsFirmwareUpdateForDevice(pairedDevice);

  Future<bool> checkFirmwareUpdates({FirmwareUpdateCheckSession? session, int? generation}) async {
    generation ??= _sessionGeneration;
    if (!_isCurrent(generation)) return false;
    final checkSession = session ?? _firmwareUpdateCheckSessionGuard.capture();
    if (checkSession == null || !_isCurrentFirmwareCheckSession(checkSession)) {
      return false;
    }
    if (!_allowsFirmwareUpdateForPairedDevice) {
      _havingNewFirmware = false;
      _firmwareUpdatePromptCoordinator.clearAvailableVersion(invalidateDeferral: true);
      return false;
    }
    int retryCount = 0;
    const maxRetries = 3;
    const retryDelay = Duration(seconds: 3);

    while (retryCount < maxRetries) {
      if (!_isCurrent(generation) || !_isCurrentFirmwareCheckSession(checkSession)) {
        return false;
      }
      try {
        var (message, hasUpdate, version, firmwareDetails) = await shouldUpdateFirmware();
        if (!_isCurrent(generation) || !_isCurrentFirmwareCheckSession(checkSession)) {
          Logger.debug('Discarding firmware update result from a stale device session');
          return false;
        }

        final latestFirmwareVersion = version.isNotEmpty ? version : message;
        Map<String, dynamic>? latestOmiGlassFirmwareDetails;

        // For OmiGlass devices, populate the firmware details for the OTA UI
        if (_isOmiGlassDevice && firmwareDetails.isNotEmpty) {
          // Map backend response to OmiGlass OTA UI expected format
          final versionStr = firmwareDetails['version']?.toString() ?? '';
          final cleanVersion = versionStr.startsWith('v') ? versionStr.substring(1) : versionStr;
          final changelog = firmwareDetails['changelog'];
          final changelogStr = changelog is List ? changelog.join('\n') : (changelog?.toString() ?? '');

          latestOmiGlassFirmwareDetails = {
            'version': cleanVersion,
            'download_url': firmwareDetails['zip_url'] ?? '',
            'changelog': changelogStr,
          };
        }

        // Fetch latest stable version for rollback comparison
        String? latestStableFirmwareVersion;
        try {
          var stableDetails = await getStableFirmwareVersion(deviceModelNumber: pairedDevice?.modelNumber ?? '');
          if (!_isCurrent(generation) || !_isCurrentFirmwareCheckSession(checkSession)) {
            Logger.debug('Discarding stable firmware result from a stale device session');
            return false;
          }
          var stableVersion = stableDetails['version']?.toString() ?? '';
          if (stableVersion.startsWith('v')) stableVersion = stableVersion.substring(1);
          latestStableFirmwareVersion = stableVersion;
        } catch (e) {
          if (!_isCurrent(generation) || !_isCurrentFirmwareCheckSession(checkSession)) {
            Logger.debug('Discarding firmware update result from a stale device session');
            return false;
          }
          Logger.debug('Error fetching stable firmware version: $e');
        }

        if (!_isCurrent(generation) || !_isCurrentFirmwareCheckSession(checkSession)) {
          return false;
        }
        _havingNewFirmware = hasUpdate;
        _latestFirmwareVersion = latestFirmwareVersion;
        if (hasUpdate) {
          _firmwareUpdatePromptCoordinator.setAvailableVersion(latestFirmwareVersion);
        } else {
          _firmwareUpdatePromptCoordinator.clearAvailableVersion();
        }
        if (latestOmiGlassFirmwareDetails != null) {
          _latestOmiGlassFirmwareDetails = latestOmiGlassFirmwareDetails;
        }
        if (latestStableFirmwareVersion != null) {
          _latestStableFirmwareVersion = latestStableFirmwareVersion;
        }
        notifyListeners();
        return hasUpdate;
      } catch (e) {
        if (!_isCurrent(generation) || !_isCurrentFirmwareCheckSession(checkSession)) {
          Logger.debug('Discarding firmware check failure from a stale device session');
          return false;
        }
        retryCount++;
        Logger.debug('Error checking firmware update (attempt $retryCount): $e');

        if (retryCount == maxRetries) {
          Logger.debug('Max retries reached, giving up');
          _havingNewFirmware = false;
          _firmwareUpdatePromptCoordinator.clearAvailableVersion();
          notifyListeners();
          return false;
        }

        await Future.delayed(retryDelay);
        if (!_isCurrent(generation) || !_isCurrentFirmwareCheckSession(checkSession)) {
          return false;
        }
      }
    }
    return false;
  }

  // Track if user is currently viewing a firmware update page
  bool _isOnFirmwareUpdatePage = false;
  void setOnFirmwareUpdatePage(bool value) {
    _isOnFirmwareUpdatePage = value;
    if (value) {
      _firmwareUpdatePromptCoordinator.invalidatePresentation();
    }
  }

  void showFirmwareUpdateDialog(BuildContext context) {
    if (!_allowsFirmwareUpdateForPairedDevice ||
        !_havingNewFirmware ||
        !SharedPreferencesUtil().showFirmwareUpdateDialog ||
        _isFirmwareUpdateInProgress ||
        _isOnFirmwareUpdatePage) {
      return;
    }

    final prompt = _firmwareUpdatePromptCoordinator.beginPresentation();
    if (prompt == null) return;

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        final route = ModalRoute.of(dialogContext);
        final navigator = Navigator.of(dialogContext);
        _firmwareUpdatePromptCoordinator.attachDismissal(prompt, () {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!dialogContext.mounted || route == null || !route.isActive) return;
            if (route.isCurrent) {
              navigator.pop();
            } else {
              navigator.removeRoute(route);
            }
          });
        });

        return ConfirmationDialog(
          title: dialogContext.l10n.firmwareUpdateAvailable,
          description: dialogContext.l10n.firmwareUpdateAvailableDescription(_latestFirmwareVersion),
          confirmText: dialogContext.l10n.update,
          cancelText: dialogContext.l10n.later,
          onConfirm: () {
            if (!_firmwareUpdatePromptCoordinator.accept(prompt)) return;
            Logger.info('Firmware update prompt accepted');
            setFirmwareUpdateInProgress(true);
            if (_isOmiGlassDevice) {
              navigator.push(
                omiPageRoute(
                  builder: (context) =>
                      OmiGlassOtaUpdate(device: pairedDevice, latestFirmwareDetails: _latestOmiGlassFirmwareDetails),
                ),
              );
            } else {
              navigator.push(omiPageRoute(builder: (context) => FirmwareUpdate(device: pairedDevice)));
            }
          },
          onCancel: () {
            if (_firmwareUpdatePromptCoordinator.defer(prompt)) {
              Logger.info('Firmware update prompt deferred by user');
            }
          },
        );
      },
    ).whenComplete(() {
      _firmwareUpdatePromptCoordinator.complete(prompt);
    });
  }

  Future setisDeviceStorageSupport() async {
    final generation = _sessionGeneration;
    if (connectedDevice == null) {
      if (!_isCurrent(generation)) return;
      isDeviceStorageSupport = false;
    } else {
      var storageFiles = await _getStorageList(connectedDevice!.id);
      if (!_isCurrent(generation)) return;
      isDeviceStorageSupport = storageFiles.isNotEmpty;
    }
    if (!_isCurrent(generation)) return;
    notifyListeners();
  }

  /// Readopts a service link native already holds while the mirror shows the
  /// persisted pairing disconnected. The reconciler authorizes this at probe
  /// time — and arms the pairing constraint before the link forms — so every
  /// admission for this device revalidates the persisted pairing at admission
  /// and through the publication continuation.
  void readoptServiceLink(String deviceId) {
    if (_isDisposed) return;
    _readoptExpectedPair = deviceId;
    final generation = _sessionGeneration;
    _disconnectDebouncer.cancel();
    _connectDebouncer.run(() {
      if (!_isCurrent(generation)) return;
      _handleDeviceConnected(deviceId, generation, requirePersistedPair: true);
    });
  }

  /// Arms the readoption pairing constraint for [deviceId] before the link
  /// starts forming: whichever connected event queues the admission — the
  /// transport's own event or the reconciler's — it must still match the
  /// persisted pairing when it and its continuation run.
  void armReadoptPairConstraint(String deviceId) {
    if (_isDisposed) return;
    _readoptExpectedPair = deviceId;
  }

  @override
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) async {
    Logger.debug("provider > device connection state changed...$deviceId...$state...${connectedDevice?.id}");
    final generation = _sessionGeneration;
    switch (state) {
      case DeviceConnectionState.connected:
        _disconnectDebouncer.cancel();
        _connectDebouncer.run(() {
          if (!_isCurrent(generation)) return;
          _handleDeviceConnected(deviceId, generation);
        });
        break;
      case DeviceConnectionState.connecting:
        break;
      case DeviceConnectionState.disconnected:
        _connectDebouncer.cancel();
        // Check if this is the paired device or currently connected device
        // Coz connectedDevice and pairedDevice are the same but connectedDevice becomes null after disconnect
        if (deviceId == connectedDevice?.id || deviceId == pairedDevice?.id) {
          _disconnectDebouncer.run(() {
            if (!_isCurrent(generation)) return;
            onDeviceDisconnected();
          });
        }
        break;
    }
  }

  @override
  void onDevices(List<BtDevice> devices) async {}

  @override
  void onStatusChanged(DeviceServiceStatus status) {}

  prepareDFU() {
    if (!FirmwareUpdateBuildPolicy.current.allowsOmiFirmwareUpdate || connectedDevice == null) {
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
    if (inProgress) {
      _firmwareUpdatePromptCoordinator.invalidatePresentation();
    }
    notifyListeners();
  }
}
