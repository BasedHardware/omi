import 'dart:async';

import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_asset_image.dart';
import 'package:omi/pages/onboarding/apple_watch_permission_page.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/devices/connectors/apple_watch_connection.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/apple_watch_setup_bottom_sheet.dart';
import 'package:omi/widgets/rayban_meta_setup_sheet.dart';

/// The platform owners device discovery reaches. Production leaves every field null and uses the
/// existing host APIs, device service and sheets; tests pass fakes.
class DeviceDiscoveryHosts {
  const DeviceDiscoveryHosts({
    this.watch,
    this.rayBan,
    this.ensureConnection,
    this.discover,
    this.showAppleWatchSetup,
    this.showAppleWatchPermission,
    this.showRayBanSetup,
  });

  final WatchRecorderHostAPI Function()? watch;
  final RayBanMetaHostAPI Function()? rayBan;
  final Future<DeviceConnection?> Function(String deviceId, {bool force})? ensureConnection;
  final Future<void> Function({int timeout})? discover;
  final Future<void> Function(BuildContext context, AppleWatchSetupBottomSheet sheet)? showAppleWatchSetup;
  final Future<void> Function(BuildContext context, AppleWatchDeviceConnection connection, VoidCallback onGranted)?
      showAppleWatchPermission;
  final Future<bool> Function(BuildContext context)? showRayBanSetup;
}

/// Tap routing, scanning and the post-connection warning for the device discovery list. The classic
/// [FoundDevices]/[FindDevicesPage] and the native Connect surface both delegate here, so the two
/// presentations share one behaviour. BLE scanning and connection stay with [OnboardingProvider],
/// the device service and the existing host APIs; this class only sequences them.
///
/// [context] is the owning widget's element, captured once: its `mounted` answers safely after the
/// owner is gone.
class DeviceDiscoveryController {
  DeviceDiscoveryController({
    required BuildContext context,
    required this.isFromOnboarding,
    required this.goNext,
    this.onRescan,
    this.hosts = const DeviceDiscoveryHosts(),
  }) : _context = context;

  final BuildContext _context;
  final DeviceDiscoveryHosts hosts;

  /// Kept current by the owner's didUpdateWidget, like the widget fields they replace.
  bool isFromOnboarding;
  VoidCallback goNext;

  /// Scans again; offered on an offline saved device's "Try Again".
  Future<void> Function()? onRescan;

  OnboardingProvider get _provider => Provider.of<OnboardingProvider>(_context, listen: false);

  /// A missing Bluetooth (or, on Android 11 and older, location) permission goes through the one
  /// global recovery prompt, [BluetoothGuidanceListener]: "Permissions required" with Open
  /// Settings. Discovery never draws its own Bluetooth dialog (onboarding-home #12).
  Future<void> scan() async {
    void publishGuidance() {
      if (_context.mounted) unawaited(BluetoothReadiness.instance.ensureReady(BluetoothUse.discovery));
    }

    await _provider.scanDevices(onShowDialog: publishGuidance, onShowLocationDialog: publishGuidance);
  }

  /// Cancels the running scan, hides the "nothing found" help and scans again. [onReset] runs
  /// between the two, where the owner redraws.
  Future<void> rescan({VoidCallback? onReset}) async {
    OmiHaptics.selection();
    final provider = _provider;
    provider.cancelActiveScan();
    provider.enableInstructions = false;
    onReset?.call();
    await scan();
  }

  /// Routes a tap on [device]: an offline saved device explains how to wake it, Apple Watch and
  /// Ray-Ban Meta run their setup first, and anything else connects through the provider.
  Future<void> tap(BtDevice device) async {
    final provider = _provider;
    if (provider.isClicked) return;
    OmiHaptics.selection();
    if (provider.isSavedDevice(device) && !provider.isDeviceOnline(device)) {
      _showOffline(device);
      return;
    }
    if (device.type == DeviceType.appleWatch) {
      await _handleAppleWatchOnboarding(device, provider);
    } else if (device.type == DeviceType.raybanMeta) {
      await _handleRayBanMetaOnboarding(device, provider);
    } else {
      await provider.handleTap(device: device, isFromOnboarding: isFromOnboarding, goNext: goNext);

      if (!_context.mounted) return;

      // Show firmware warning after successful connection
      if (provider.isConnected) {
        final connectedDevice = provider.deviceProvider?.connectedDevice ?? device;
        await showFirmwareWarningIfNeeded(connectedDevice);
      }
    }
  }

  /// [tap] for a projection captured earlier: the device must still be in the visible list, and the
  /// current entry for its id is the one connected. A device that left the list is ignored.
  Future<void> tapVisible(String deviceId) async {
    final current = _provider.visibleDeviceList.firstWhereOrNull((device) => device.id == deviceId);
    if (current == null) return;
    await tap(current);
  }

  Future<void> _handleRayBanMetaOnboarding(BtDevice device, OnboardingProvider provider) async {
    try {
      final host = (hosts.rayBan ?? RayBanMetaHostAPI.new)();
      final mode = await host.getAvailabilityMode();

      var needsSetup = device.id == RayBanMetaDiscoverer.setupPlaceholderId;
      if (mode == 'full' && !needsSetup) {
        final registration = await host.getRegistrationState();
        final camera = await host.getCameraPermissionStatus();
        needsSetup = registration != 'registered' || camera != 'granted';
      } else if (mode != 'full') {
        // Audio-only fallback: always explain the limitation before connecting.
        needsSetup = true;
      }

      if (needsSetup) {
        if (!_context.mounted) return;
        final ready = await (hosts.showRayBanSetup ?? RayBanMetaSetupSheet.show)(_context);
        if (!ready || !_context.mounted) return;
      }

      var target = device;
      if (device.id == RayBanMetaDiscoverer.setupPlaceholderId) {
        // Registration just completed — rescan so the real glasses replace the
        // setup placeholder, then connect to them.
        await (hosts.discover ?? ({int timeout = 5}) => ServiceManager.instance().device.discover(timeout: timeout))(
            timeout: 5);
        final real = provider.deviceList.firstWhereOrNull(
          (d) => d.type == DeviceType.raybanMeta && d.id != RayBanMetaDiscoverer.setupPlaceholderId,
        );
        if (real == null) return;
        target = real;
      }

      await provider.handleTap(device: target, isFromOnboarding: isFromOnboarding, goNext: goNext);
    } catch (e) {
      Logger.debug('Error handling Ray-Ban Meta onboarding: $e');
      if (!_context.mounted) return;
      OmiFeedback.error(_context, _context.l10n.errorConnectingRayBanMeta(readableError(e)));
    }
  }

  Future<DeviceConnection?> _ensureConnection(String deviceId, {bool force = false}) =>
      (hosts.ensureConnection ?? ServiceManager.instance().device.ensureConnection)(deviceId, force: force);

  Future<void> _handleAppleWatchOnboarding(BtDevice device, OnboardingProvider provider) async {
    try {
      // First check if the watch is reachable
      final hostAPI = (hosts.watch ?? WatchRecorderHostAPI.new)();
      final bool isReachable = await hostAPI.isWatchReachable();

      if (!isReachable) {
        // Watch is not reachable - show bottom sheet to install/open app
        await _showWatchNotReachableBottomSheet(device.id);
        return;
      }

      // Watch is reachable - connect and check permissions
      await _ensureConnection(device.id, force: true);
      final connection = await _ensureConnection(device.id);

      if (connection is! AppleWatchDeviceConnection) {
        Logger.debug('Device is not an Apple Watch connection');
        return;
      }

      // Check permission and try to start recording immediately
      final bool recordingStarted = await connection.checkPermissionAndStartRecording();

      if (!recordingStarted) {
        await _showMicrophonePermissionPage(connection);
        if (!_context.mounted) return;
      } else {
        await _completeAppleWatchOnboarding(device, provider);
        if (!_context.mounted) return;
      }
    } catch (e) {
      Logger.debug('Error handling Apple Watch onboarding: $e');
      if (!_context.mounted) return;
      OmiFeedback.error(_context, _context.l10n.errorConnectingAppleWatch(readableError(e)));
    }
  }

  /// Show bottom sheet when Apple Watch is not reachable
  Future<void> _showWatchNotReachableBottomSheet(String deviceId) async {
    final provider = _provider;
    final device = provider.deviceList.firstWhereOrNull((d) => d.id == deviceId);
    if (device == null) {
      Logger.debug('Device with id $deviceId not found in provider list.');
      return;
    }

    final sheet = AppleWatchSetupBottomSheet(
      deviceId: deviceId,
      onConnected: () async {
        await _handleAppleWatchOnboarding(device, provider);
      },
    );
    final show = hosts.showAppleWatchSetup;
    if (show != null) {
      await show(_context, sheet);
    } else {
      await AppleWatchSetupBottomSheet.show(_context, sheet: sheet);
    }
  }

  Future<void> _showMicrophonePermissionPage(AppleWatchDeviceConnection connection) async {
    final provider = _provider;
    final device = provider.deviceList.firstWhereOrNull((d) => d.id == connection.device.id);
    if (device == null) {
      Logger.debug('Device with id ${connection.device.id} not found in provider list.');
      return;
    }

    Future<void> onGranted() async {
      await _completeAppleWatchOnboarding(device, provider);
    }

    final show = hosts.showAppleWatchPermission;
    if (show != null) {
      await show(_context, connection, onGranted);
    } else {
      await Navigator.of(_context).push(
        omiPageRoute(
          builder: (context) => AppleWatchPermissionPage(connection: connection, onPermissionGranted: onGranted),
        ),
      );
    }
    if (!_context.mounted) return;
  }

  Future<void> _completeAppleWatchOnboarding(BtDevice device, OnboardingProvider provider) async {
    try {
      provider.deviceId = device.id;
      provider.deviceName = device.name;
      provider.isConnected = true;
      provider.isClicked = false;
      provider.connectingToDeviceId = null;

      await provider.deviceProvider?.scanAndConnectToDevice();

      if (!_context.mounted) return;

      // Show firmware warning if needed
      await showFirmwareWarningIfNeeded(device);

      if (!_context.mounted) return;

      if (isFromOnboarding) {
        goNext();
      } else {
        if (_context.mounted) Navigator.pop(_context);
      }
    } catch (e) {
      Logger.debug('Error completing Apple Watch onboarding: $e');
    }
  }

  /// The compatibility note shown once a device is connected. A critical warning (unsupported
  /// encrypted firmware) always shows and cannot be silenced; any other offers "Don't show again",
  /// which is persisted only when the reader acknowledges it.
  Future<void> showFirmwareWarningIfNeeded(BtDevice device) async {
    final warningMessage = device.getFirmwareWarningMessage();
    if (warningMessage.isEmpty) {
      return; // No warning needed for this device type
    }

    // Critical firmware warnings (e.g. unsupported encrypted firmware) always show,
    // regardless of prior acknowledgment. Only skip for non-critical compatibility notes.
    final isCritical = device.type == DeviceType.bee && device.isBeeFirmwareUnsupported;
    final prefKey = 'firmware_warning_acknowledged_${device.type.toString()}';

    if (!isCritical) {
      final alreadyAcknowledged = SharedPreferencesUtil().getBool(prefKey);
      if (alreadyAcknowledged) {
        return; // User already acknowledged this warning
      }
    }

    if (!_context.mounted) return;

    // Acknowledge-only: one "I Understand". A critical warning cannot be silenced; a compatibility
    // note offers "Don't show again".
    if (isCritical) {
      await showOmiAlert(
        _context,
        title: device.getFirmwareWarningTitle(),
        message: warningMessage,
        okLabel: _context.l10n.iUnderstand,
        barrierDismissible: false,
      );
      return;
    }

    // The native alert keeps the single "I Understand" with the same opt-out toggle; null keeps the
    // acknowledge-only card below.
    final l10n = _context.l10n;
    final native = !nativePresentationEnabled
        ? null
        : await showIosNativeModal(
            _context,
            title: device.getFirmwareWarningTitle(),
            dismissible: false,
            actions: [NativeRow('acknowledge', l10n.iUnderstand)],
            sections: [
              NativeSection('firmware_warning', [
                NativeRow('message', warningMessage, kind: 'label'),
                NativeRow('opt_out', l10n.dontShowAgain, kind: 'toggle', value: false),
              ]),
            ],
          );
    if (!_context.mounted) return;
    if (native != null) {
      if (native.action == 'acknowledge' && native.values['opt_out'] == true) {
        SharedPreferencesUtil().saveBool(prefKey, true);
      }
      return;
    }

    var dontShowAgain = false;
    await showDialog<void>(
      context: _context,
      barrierDismissible: false,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => OmiDialogCard(
          title: device.getFirmwareWarningTitle(),
          message: warningMessage,
          content: OmiCheckboxRow(
            label: dialogContext.l10n.dontShowAgain,
            value: dontShowAgain,
            onChanged: (value) => setDialogState(() => dontShowAgain = value),
          ),
          actions: [
            OmiDialogAction(
              label: dialogContext.l10n.iUnderstand,
              isDefault: true,
              onPressed: () {
                if (dontShowAgain) {
                  SharedPreferencesUtil().saveBool(prefKey, true);
                }
                Navigator.pop(dialogContext);
              },
            ),
          ],
        ),
      ),
    );
  }

  void _showOffline(BtDevice device) {
    final rescan = onRescan;
    OmiFeedback.error(
      _context,
      _context.l10n.deviceOfflineWakeHint(device.name),
      actionLabel: _context.l10n.tryAgain,
      onAction: rescan == null ? null : () => unawaited(rescan()),
    );
  }
}

/// The name a discovery row shows: a name several visible devices share gets its short id.
String discoveryDeviceLabel(OnboardingProvider provider, String name, String id) {
  final sameNameCount = provider.visibleDeviceList.where((d) => d.name == name).length;
  return sameNameCount > 1 ? '$name (${BtDevice.shortId(id)})' : name;
}

/// File URIs of bundled artwork for native rows. A row shows no thumbnail until its copy is ready;
/// [onReady] then lets the owner republish. Only static app assets cross (see [nativeAssetImageUri]).
class NativeAssetUris {
  NativeAssetUris(this._onReady);

  final VoidCallback _onReady;
  final _resolved = <String, String?>{};
  bool _disposed = false;

  String? operator [](String? asset) {
    if (asset == null) return null;
    if (_resolved.containsKey(asset)) return _resolved[asset];
    _resolved[asset] = null;
    unawaited(nativeAssetImageUri(asset).then((uri) {
      _resolved[asset] = uri;
      if (!_disposed && uri != null) _onReady();
    }));
    return null;
  }

  void dispose() => _disposed = true;
}
