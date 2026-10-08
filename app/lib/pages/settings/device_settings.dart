import 'dart:async';

import 'package:omi/mobile/native_ui/ios_native_settings.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_asset_image.dart';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/omiglass_ota_update.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
import 'package:omi/pages/settings/device/device_control_sheets.dart';
import 'package:omi/pages/settings/device/device_info_groups.dart';
import 'package:omi/pages/settings/device/device_page_header.dart';
import 'package:omi/pages/settings/device_diagnostics.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/connectors/rayban_meta_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/firmware_update_build_policy.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// The one device page: status, controls, sync, firmware, device information and Forget Device.
///
/// Canonical implementation. It is reached from the Settings drawer, the capture "connect" flow,
/// the home-screen quick action, and (through the `ConnectedDevice` alias in
/// `pages/home/device.dart`) the header battery pill.
class DeviceSettings extends StatefulWidget {
  const DeviceSettings({super.key, this.connectionForTest});

  /// Test-only: resolves a device connection in place of [ServiceManager], so hermetic tests reach
  /// a fake device writer. Production always passes null.
  @visibleForTesting
  final Future<DeviceConnection?> Function(String deviceId)? connectionForTest;

  @override
  State<DeviceSettings> createState() => _DeviceSettingsState();
}

/// [Provider.of] for a provider the page can live without (streaming metrics, pending sync).
T? _maybeProvider<T>(BuildContext context, {bool listen = true}) {
  try {
    return Provider.of<T>(context, listen: listen);
  } on ProviderNotFoundException {
    return null;
  }
}

class _DeviceSettingsState extends State<DeviceSettings> {
  static const Duration _findDeviceRequestTimeout = Duration(seconds: 30);

  /// How long a native level control must rest before its latest value is written.
  static const Duration _nativeWriteDelay = Duration(milliseconds: 300);

  CaptureProvider? _captureProvider;

  double _dimRatio = 100.0;
  bool _isDimRatioLoaded = false;
  bool? _hasDimmingFeature;

  double _micGain = 5.0;
  bool _isMicGainLoaded = false;
  bool? _hasMicGainFeature;

  Timer? _debounce;
  Timer? _micGainDebounce;

  /// Pending native level writes by control. Each holds the latest value only; leaving the page
  /// writes it at once, so the final value always reaches the device.
  final _nativeWrites = <String, ({Timer timer, String deviceId, Future<void> Function() write})>{};
  bool _isFindingDevice = false;

  bool _autoSyncOfflineRecordings = SharedPreferencesUtil().autoSyncOfflineRecordings;
  bool _omiButtonActionsEnabled = SharedPreferencesUtil().omiButtonActionsEnabled;

  /// Ray-Ban Meta camera readiness, last answered; null until the first check completes.
  String? _rayBanMetaCameraStatus;
  String? _rayBanMetaCameraStatusDeviceId;
  bool _rayBanMetaCameraStatusRequested = false;
  int _rayBanMetaCameraStatusRequest = 0;

  /// The device owner the page last built with; a pending write for a device it no longer pairs
  /// (forgotten or unpaired while the page closes) is dropped instead of reconnecting it.
  DeviceProvider? _deviceProvider;

  /// The native device thumbnail: the bundled picture last requested, and its file URI once copied.
  String? _thumbnailAsset;
  String? _thumbnailUri;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      // Register for streaming metrics right away, so an early unmount cannot race the
      // async device-info fetch below and leak the listener.
      _captureProvider = _maybeProvider<CaptureProvider>(context, listen: false);
      _captureProvider?.addMetricsListener();
      await context.read<DeviceProvider>().getDeviceInfo();
      if (!mounted) return;
      _loadDeviceFeatures();
    });
  }

  @override
  void dispose() {
    _captureProvider?.removeMetricsListener();
    _debounce?.cancel();
    _micGainDebounce?.cancel();
    _flushNativeWrites();
    super.dispose();
  }

  Future<DeviceConnection?> _connection(String deviceId) =>
      widget.connectionForTest?.call(deviceId) ?? ServiceManager.instance().device.ensureConnection(deviceId);

  // Device features: LED dimming and mic gain.

  Future<void> _loadDeviceFeatures() async {
    final deviceProvider = context.read<DeviceProvider>();
    if (deviceProvider.pairedDevice == null) return;
    final connection = await _connection(deviceProvider.pairedDevice!.id);
    if (connection == null) return;
    final features = await connection.getFeatures();
    final hasDimming = (features & OmiFeatures.ledDimming) != 0;
    final hasMicGain = (features & OmiFeatures.micGain) != 0;
    if (!mounted) return;
    setState(() {
      _hasDimmingFeature = hasDimming;
      _hasMicGainFeature = hasMicGain;
    });

    final ratio = hasDimming ? await connection.getLedDimRatio() : null;
    if (!mounted) return;
    setState(() {
      if (ratio != null) _dimRatio = ratio.toDouble();
      _isDimRatioLoaded = true; // Loaded; without a value the default stays.
    });

    final gain = hasMicGain ? await connection.getMicGain() : null;
    if (!mounted) return;
    setState(() {
      if (gain != null) _micGain = gain.toDouble();
      _isMicGainLoaded = true;
    });
  }

  Future<void> _updateDimRatio(double value) async {
    final deviceId = context.read<DeviceProvider>().pairedDevice?.id;
    if (deviceId == null) return;
    await _writeDimRatio(deviceId, value.toInt());
  }

  Future<void> _updateMicGain(double value) async {
    final deviceId = context.read<DeviceProvider>().pairedDevice?.id;
    if (deviceId == null) return;
    await _writeMicGain(deviceId, value.toInt());
  }

  Future<void> _writeDimRatio(String deviceId, int ratio) async {
    final connection = await _connection(deviceId);
    await connection?.setLedDimRatio(ratio);
  }

  Future<void> _writeMicGain(String deviceId, int gain) async {
    final connection = await _connection(deviceId);
    await connection?.setMicGain(gain);
  }

  // Native level controls. Swift sends one value when a drag ends; Dart rounds it, shows it at
  // once and writes the latest value after a trailing [_nativeWriteDelay].

  void _scheduleNativeWrite(String control, String deviceId, Future<void> Function() write) {
    _nativeWrites.remove(control)?.timer.cancel();
    final timer = Timer(_nativeWriteDelay, () {
      _nativeWrites.remove(control);
      unawaited(write());
    });
    _nativeWrites[control] = (timer: timer, deviceId: deviceId, write: write);
  }

  void _flushNativeWrites() {
    final pending = _nativeWrites.values.toList();
    _nativeWrites.clear();
    for (final write in pending) {
      write.timer.cancel();
      if (write.deviceId == _deviceProvider?.pairedDevice?.id) unawaited(write.write());
    }
  }

  void _setNativeDimRatio(num value) {
    final deviceId = context.read<DeviceProvider>().pairedDevice?.id;
    if (deviceId == null) return;
    final ratio = value.round().clamp(0, 100);
    setState(() => _dimRatio = ratio.toDouble());
    _scheduleNativeWrite('led', deviceId, () => _writeDimRatio(deviceId, ratio));
  }

  void _setNativeMicGain(num value) {
    final deviceId = context.read<DeviceProvider>().pairedDevice?.id;
    if (deviceId == null) return;
    final gain = value.round().clamp(0, 8);
    setState(() => _micGain = gain.toDouble());
    _scheduleNativeWrite('mic_gain', deviceId, () => _writeMicGain(deviceId, gain));
  }

  /// A preset is an explicit choice, so it replaces any pending drag value and is written at once.
  Future<void> _applyNativeMicGainPreset(int gain) async {
    final deviceId = context.read<DeviceProvider>().pairedDevice?.id;
    if (deviceId == null) return;
    _nativeWrites.remove('mic_gain')?.timer.cancel();
    setState(() => _micGain = gain.toDouble());
    await _writeMicGain(deviceId, gain);
  }

  void _showBrightnessSheet() {
    showLedBrightnessSheet(
      context,
      initial: _dimRatio,
      onChanged: (value) {
        setState(() => _dimRatio = value);
        if (!(_debounce?.isActive ?? false)) {
          _debounce = Timer(const Duration(milliseconds: 300), () => _updateDimRatio(value));
        }
      },
      onChangeEnd: (value) {
        _debounce?.cancel();
        setState(() => _dimRatio = value);
        _updateDimRatio(value);
      },
    );
  }

  void _showMicGainSheet() {
    showMicGainSheet(
      context,
      initial: _micGain,
      onChanged: (value) {
        setState(() => _micGain = value);
        if (!(_micGainDebounce?.isActive ?? false)) {
          _micGainDebounce = Timer(const Duration(milliseconds: 300), () => _updateMicGain(value));
        }
      },
      onChangeEnd: (value) {
        _micGainDebounce?.cancel();
        setState(() => _micGain = value);
        _updateMicGain(value);
      },
    );
  }

  String _doubleTapActionLabel(int action) {
    switch (action) {
      case 1:
        return context.l10n.deviceOnboardingMuteUnmute;
      case 2:
        return context.l10n.starConversation;
      default:
        return context.l10n.endConversation;
    }
  }

  Future<void> _pickDoubleTapAction() async {
    final action = await showDoubleTapActionSheet(context, current: SharedPreferencesUtil().doubleTapAction);
    if (action == null || !mounted) return;
    setState(() => SharedPreferencesUtil().doubleTapAction = action);
  }

  Future<void> _findDevice(DeviceProvider provider) async {
    if (_isFindingDevice) return;
    setState(() => _isFindingDevice = true);

    var found = false;
    try {
      found = await provider.findDevice().timeout(_findDeviceRequestTimeout);
    } catch (e) {
      Logger.debug('DeviceSettings: Find-device request failed: $e');
    } finally {
      if (mounted) setState(() => _isFindingDevice = false);
    }

    if (mounted && !found) {
      OmiFeedback.error(
        context,
        context.l10n.anErrorOccurredTryAgain,
        actionLabel: context.l10n.tryAgain,
        onAction: () => _findDevice(provider),
      );
    }
  }

  // Ray-Ban Meta.

  /// The camera readiness label for the connected glasses, or null while it is checked. The first
  /// request per device starts the check; its answer rebuilds the page.
  String? _rayBanMetaCameraLabel(DeviceProvider provider) {
    final deviceId = provider.connectedDevice?.id;
    if (!_rayBanMetaCameraStatusRequested || _rayBanMetaCameraStatusDeviceId != deviceId) {
      _rayBanMetaCameraStatusRequested = true;
      // The previous answer stays until the new one arrives, as the classic FutureBuilder kept it.
      _rayBanMetaCameraStatusDeviceId = deviceId;
      final request = ++_rayBanMetaCameraStatusRequest;
      unawaited(_loadRayBanMetaCameraStatus(deviceId).then((status) {
        if (!mounted || request != _rayBanMetaCameraStatusRequest) return;
        setState(() => _rayBanMetaCameraStatus = status);
      }));
    }
    final status = _rayBanMetaCameraStatus;
    return status == null ? null : rayBanCameraLabel(context, status);
  }

  Future<String> _loadRayBanMetaCameraStatus(String? deviceId) async {
    try {
      if (deviceId == null) return 'unavailable';
      final connection = await _connection(deviceId);
      if (connection is! RayBanMetaDeviceConnection) return 'unavailable';
      return await connection.getCameraPermissionStatus();
    } catch (_) {
      return 'unavailable';
    }
  }

  Future<void> _captureRayBanMetaPhoto() async {
    try {
      final deviceId = context.read<DeviceProvider>().connectedDevice?.id;
      if (deviceId == null) return;
      final connection = await _connection(deviceId);
      if (connection is! RayBanMetaDeviceConnection) return;
      final cameraStatus = await connection.getCameraPermissionStatus();
      if (cameraStatus != 'granted') {
        if (mounted) OmiFeedback.info(context, context.l10n.raybanMetaImageCaptureUnavailable);
        return;
      }
      await connection.capturePhoto();
      if (mounted) OmiFeedback.confirm(context, context.l10n.raybanMetaPhotoRequested);
    } catch (e) {
      if (mounted) OmiFeedback.error(context, context.l10n.errorConnectingRayBanMeta(readableError(e)));
    }
  }

  // Firmware, sync and support.

  void _openProductUpdate(DeviceProvider provider) {
    final isOpenGlass = FirmwareUpdateBuildPolicy.current.isOpenGlassDevice(provider.connectedDevice);
    Logger.debug('ProductUpdate: type=${provider.connectedDevice?.type} isOpenGlass=$isOpenGlass');
    routeToPage(
      context,
      isOpenGlass
          ? OmiGlassOtaUpdate(
              device: provider.pairedDevice, latestFirmwareDetails: provider.latestOmiGlassFirmwareDetails)
          : FirmwareUpdate(device: provider.pairedDevice),
    );
  }

  Future<void> _confirmRollback(DeviceProvider provider) async {
    final confirmed = await showOmiConfirm(
      context,
      title: context.l10n.rollbackConfirmTitle,
      message: context.l10n.rollbackConfirmMessage(provider.latestStableFirmwareVersion),
      confirmLabel: context.l10n.rollBack,
    );
    if (!confirmed || !mounted) return;
    routeToPage(context, FirmwareUpdate(device: provider.pairedDevice, isRollback: true));
  }

  void _openOfflineSync(DeviceProvider provider) {
    if (!provider.isDeviceStorageSupport) {
      showOmiAlert(context, title: context.l10n.v2Undetected, message: context.l10n.v2UndetectedMessage);
      return;
    }
    routeToPage(context, provider.supportsMultiFileSync ? const AutoSyncPage() : const SyncPage());
  }

  Future<void> _openChargingHelp(DeviceProvider provider) async {
    final deviceName = provider.pairedDevice?.name ?? 'DevKit1';
    if (PlatformService.isIntercomSupported) {
      await IntercomManager.instance.displayChargingArticle(deviceName);
      return;
    }
    final String url;
    if (deviceName == 'Omi DevKit 2') {
      url = 'https://www.omi.me/pages/charging-devkit2';
    } else if (deviceName == 'Omi') {
      url = 'https://www.omi.me/pages/charging-omi';
    } else {
      url = 'https://www.omi.me/pages/charging';
    }
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  // Forget and unpair. Neither can be undone, so both confirm every time (ux-contract §4).

  Future<void> _clearStoredDevice() async {
    await SharedPreferencesUtil().btDeviceSet(BtDevice(id: '', name: '', type: DeviceType.omi, rssi: 0));
    SharedPreferencesUtil().deviceName = '';
  }

  void _leavePage() {
    if (mounted && Navigator.of(context).canPop()) Navigator.of(context).pop();
  }

  Future<void> _forgetDevice(DeviceProvider provider) async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.forgetDeviceConfirmTitle,
      message: l10n.forgetDeviceConfirmMessage,
      confirmLabel: l10n.forgetDevice,
      destructive: true,
    );
    if (!confirmed) return;

    // Read the id before the stored device is cleared.
    final deviceId = provider.connectedDevice?.id ?? SharedPreferencesUtil().btDevice.id;
    if (deviceId.isNotEmpty) provider.markDisconnectIntentional(deviceId);
    await _clearStoredDevice();
    // Fully tear down the connection, transport and native service.
    if (deviceId.isNotEmpty) {
      await ServiceManager.instance().device.forgetDevice(deviceId);
      try {
        BleHostApi().unmanageDevice(deviceId);
      } catch (_) {}
    }
    provider.setIsConnected(false);
    await provider.setConnectedDevice(null);
    provider.updateConnectingStatus(false);
    PlatformManager.instance.analytics.disconnectFriendClicked();
    if (!mounted) return;
    OmiFeedback.confirm(context, l10n.deviceForgottenMessage);
    _leavePage();
  }

  Future<void> _unpairLimitless(DeviceProvider provider) async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.unpairDeviceConfirmTitle,
      message: l10n.unpairDialogMessage,
      confirmLabel: l10n.unpair,
      destructive: true,
    );
    if (!confirmed) return;

    await _clearStoredDevice();
    final device = provider.connectedDevice;
    if (device != null) {
      provider.markDisconnectIntentional(device.id);
      final connection = await _connection(device.id);
      if (connection != null) {
        await connection.unpair();
        await connection.disconnect();
      }
    }
    provider.setIsConnected(false);
    provider.setConnectedDevice(null);
    provider.updateConnectingStatus(false);
    if (!mounted) return;
    OmiFeedback.info(context, l10n.deviceUnpairedMessage);
    _leavePage();
  }

  // Sections.

  Widget _customizationGroup(BtDevice? device, DeviceProvider provider) {
    final l10n = context.l10n;
    final isOmi = device?.type == DeviceType.omi;
    final supportsFind = isOmi && !FirmwareUpdateBuildPolicy.current.isOpenGlassDevice(device);
    final doubleTapRow = OmiSettingsRow(
      key: const ValueKey('device_double_tap'),
      leading: const FaIcon(FontAwesomeIcons.handPointer),
      title: l10n.doubleTap,
      value: _doubleTapActionLabel(SharedPreferencesUtil().doubleTapAction),
      onTap: _pickDoubleTapAction,
      showChevron: true,
    );
    return OmiSettingsGroup(
      header: l10n.customizationSection,
      children: [
        if (supportsFind)
          OmiSettingsRow(
            key: const Key('find_device_button'),
            leading: const FaIcon(FontAwesomeIcons.bullseye),
            title: l10n.findDevice,
            showChevron: false,
            trailing: _isFindingDevice ? const OmiSpinner(size: OmiSpinnerSize.small) : null,
            onTap: () => _findDevice(provider),
          ),
        if (isOmi) ...[
          OmiSettingsRow.toggle(
            key: const Key('omi_button_actions_toggle'),
            leading: const FaIcon(FontAwesomeIcons.handPointer),
            title: l10n.omiButtonActions,
            value: _omiButtonActionsEnabled,
            onChanged: (value) {
              setState(() => _omiButtonActionsEnabled = value);
              SharedPreferencesUtil().omiButtonActionsEnabled = value;
              if (!value) {
                // Drop any in-flight voice-command session so audio captured while actions
                // were enabled is not submitted after disabling.
                context.read<CaptureProvider>().cancelActiveVoiceSession();
              }
            },
          ),
          // Double tap is only configurable while Omi button actions are enabled.
          if (_omiButtonActionsEnabled) doubleTapRow,
        ] else
          doubleTapRow,
        if (_isDimRatioLoaded && _hasDimmingFeature == true)
          OmiSettingsRow(
            key: const ValueKey('device_led'),
            leading: const FaIcon(FontAwesomeIcons.lightbulb),
            title: l10n.ledBrightness,
            value: '${_dimRatio.round()}%',
            onTap: _showBrightnessSheet,
            showChevron: true,
          ),
        if (_isMicGainLoaded && _hasMicGainFeature == true)
          OmiSettingsRow(
            key: const ValueKey('device_mic_gain'),
            leading: const FaIcon(FontAwesomeIcons.microphone),
            title: l10n.micGain,
            value: micGainLevelLabel(context, _micGain.round()),
            onTap: _showMicGainSheet,
            showChevron: true,
          ),
      ],
    );
  }

  Widget _deviceGroup(DeviceProvider provider) {
    final l10n = context.l10n;
    const firmwarePolicy = FirmwareUpdateBuildPolicy.current;
    final paired = provider.pairedDevice;
    final connected = provider.connectedDevice;
    final isRayBan = paired?.type == DeviceType.raybanMeta;
    final pendingSeconds = _maybeProvider<SyncProvider>(context)?.missingWalsInSeconds ?? 0;
    final diagnosticsId = paired?.id ?? connected?.id;

    return OmiSettingsGroup(
      header: l10n.device,
      children: [
        // The interactive tutorial teaches CV1 button behaviour. DevKit, Glass and Neo share
        // DeviceType.omi, so gate on the GATT model as well.
        if (connected?.type == DeviceType.omi &&
            DeviceUtils.isOmiCv1(modelNumber: paired?.modelNumber, deviceName: connected?.name))
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.graduationCap),
            title: l10n.deviceTutorial,
            onTap: () => routeToPage(context, const InteractiveDeviceOnboardingWrapper(allowExit: true)),
          ),
        // Ray-Ban Meta: on-demand photo capture. The Meta AI app manages its firmware, so the
        // update rows are hidden for it.
        if (isRayBan)
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.camera),
            title: l10n.raybanMetaCapturePhoto,
            onTap: connected != null ? _captureRayBanMetaPhoto : null,
          ),
        if (!isRayBan && firmwarePolicy.allowsFirmwareUpdateForDevice(paired))
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.download),
            title: l10n.productUpdate,
            // An update needs the device itself, so without it the row says so and is inert.
            value: connected == null
                ? l10n.disconnected
                : provider.havingNewFirmware
                    ? l10n.available
                    : null,
            onTap: connected != null ? () => _openProductUpdate(provider) : null,
          ),
        // Roll back only when the current firmware differs from the latest stable.
        if (!isRayBan &&
            firmwarePolicy.allowsOmiFirmwareUpdate &&
            connected != null &&
            provider.latestStableFirmwareVersion.isNotEmpty &&
            paired?.firmwareRevision != provider.latestStableFirmwareVersion)
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.rotateLeft),
            title: l10n.rollbackToStableFirmware,
            onTap: () => _confirmRollback(provider),
          ),
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.sdCard),
          title: l10n.offlineSync,
          trailing: pendingSeconds > 0 ? _PendingSyncChip(seconds: pendingSeconds) : null,
          showChevron: true,
          onTap: () => _openOfflineSync(provider),
        ),
        // Omi devices only: opt out of syncing offline recordings automatically on connect.
        if (paired?.type == DeviceType.omi)
          OmiSettingsRow.toggle(
            leading: const FaIcon(FontAwesomeIcons.arrowsRotate),
            title: l10n.autoSync,
            subtitle: l10n.autoSyncDescription,
            value: _autoSyncOfflineRecordings,
            onChanged: (value) {
              setState(() => _autoSyncOfflineRecordings = value);
              SharedPreferencesUtil().autoSyncOfflineRecordings = value;
            },
          ),
        if (provider.isConnected && diagnosticsId != null)
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.stethoscope),
            title: l10n.diagnostics,
            onTap: () => routeToPage(context, DeviceDiagnostics(deviceId: diagnosticsId)),
          ),
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.circleQuestion),
          title: l10n.chargingIssues,
          onTap: () => _openChargingHelp(provider),
        ),
      ],
    );
  }

  Widget _forgetGroup(DeviceProvider provider) {
    final l10n = context.l10n;
    return OmiSettingsGroup(
      children: [
        OmiSettingsRow(
          key: const Key('forget_device_button'),
          leading: const FaIcon(FontAwesomeIcons.linkSlash),
          title: l10n.forgetDevice,
          isDestructive: true,
          showChevron: false,
          onTap: () => _forgetDevice(provider),
        ),
        // Limitless pendants also need a BLE unpair so another phone can take them.
        if (provider.isConnected && provider.connectedDevice?.type == DeviceType.limitless)
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.ban),
            title: l10n.unpairAndForget,
            isDestructive: true,
            showChevron: false,
            onTap: () => _unpairLimitless(provider),
          ),
      ],
    );
  }

  /// Replaces the projected double-tap, LED and mic-gain rows with native controls. Values are
  /// clamped to their ranges, so a device reporting an out-of-range level never invalidates the page.
  List<NativeSection> _nativeDeviceControls(List<NativeSection> sections) {
    final l10n = context.l10n;
    Iterable<NativeRow> control(NativeRow row) sync* {
      switch (row.id) {
        case 'device_double_tap':
          final current = SharedPreferencesUtil().doubleTapAction;
          yield NativeRow(row.id, row.title,
              kind: 'choice',
              symbol: row.symbol,
              // An unknown stored action reads as the default, as the classic row's label does.
              value: '${current >= 0 && current <= 2 ? current : 0}',
              options: {
                '0': l10n.endAndProcess,
                '1': l10n.deviceOnboardingMuteUnmute,
                '2': l10n.starOngoing,
              }, action: (value) {
            final action = int.parse(value! as String);
            if (mounted) setState(() => SharedPreferencesUtil().doubleTapAction = action);
          });
        case 'device_led':
          final ratio = _dimRatio.round().clamp(0, 100);
          yield NativeRow(row.id, row.title,
              kind: 'level',
              symbol: row.symbol,
              subtitle: '$ratio%',
              value: ratio.toDouble(),
              minimumValue: 0,
              maximumValue: 100,
              step: 1,
              action: (value) => _setNativeDimRatio(value! as num));
        case 'device_mic_gain':
          final gain = _micGain.round().clamp(0, 8);
          // The level row draws its subtitle as a short value beside the title, so the longer
          // description gets a row of its own.
          yield NativeRow(row.id, row.title,
              kind: 'level',
              symbol: row.symbol,
              subtitle: micGainLevelLabel(context, gain),
              value: gain.toDouble(),
              minimumValue: 0,
              maximumValue: 8,
              step: 1,
              action: (value) => _setNativeMicGain(value! as num));
          final description = micGainDescription(context, gain);
          if (description.isNotEmpty) yield NativeRow('device_mic_gain_description', description, kind: 'label');
          for (final (id, label, level) in [
            ('device_mic_gain_quiet', l10n.quiet, 2),
            ('device_mic_gain_normal', l10n.normal, 4),
            ('device_mic_gain_high', l10n.high, 6),
          ]) {
            yield NativeRow(id, label,
                symbol: gain == level ? 'checkmark' : null, action: (_) => _applyNativeMicGainPreset(level));
          }
        default:
          yield row;
      }
    }

    return [
      for (final section in sections)
        NativeSection(section.id, [for (final row in section.rows) ...control(row)],
            title: section.title, footer: section.footer),
    ];
  }

  /// Copies the device picture for the native status row once per bundled asset.
  void _watchThumbnail(String asset) {
    if (_thumbnailAsset == asset) return;
    _thumbnailAsset = asset;
    unawaited(nativeAssetImageUri(asset).then((uri) {
      if (mounted && _thumbnailAsset == asset) setState(() => _thumbnailUri = uri);
    }));
  }

  @override
  Widget build(BuildContext context) {
    final provider = _deviceProvider = context.watch<DeviceProvider>();
    final capture = _maybeProvider<CaptureProvider>(context);
    final paired = provider.pairedDevice;
    final connected = provider.connectedDevice;
    final rayBanCamera = paired?.type == DeviceType.raybanMeta ? _rayBanMetaCameraLabel(provider) : null;
    const gap = SizedBox(height: OmiSpacing.xxl);

    final classic = Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.deviceSettings)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 48),
        children: [
          DevicePageHeader(pairedDevice: paired, connectedDevice: connected),
          const SizedBox(height: OmiSpacing.xl),
          if (connected != null && provider.batteryLevel > 0) ...[
            DeviceBatteryGroup(batteryLevel: provider.batteryLevel, isCharging: provider.isCharging),
            gap,
          ],
          if (provider.isConnected)
            _customizationGroup(paired ?? connected, provider)
          else
            const DeviceDisconnectedCard(),
          gap,
          _deviceGroup(provider),
          gap,
          DeviceInfoGroups(pairedDevice: paired, isDeviceConnected: connected != null, rayBanCameraLabel: rayBanCamera),
          gap,
          _forgetGroup(provider),
          if (connected != null && capture != null && capture.havingRecordingDevice) ...[
            gap,
            DeviceStreamingMetrics(bleReceiveKbps: capture.bleReceiveRateKbps, wsSendKbps: capture.wsSendRateKbps),
          ],
        ],
      ),
    );
    if (!nativePresentationEnabled) return classic;
    final l10n = context.l10n;
    final projected = nativeSettingsSections([
      if (provider.isConnected) _customizationGroup(paired ?? connected, provider),
      _deviceGroup(provider),
      DeviceInfoGroups(pairedDevice: paired, isDeviceConnected: connected != null, rayBanCameraLabel: rayBanCamera)
          .build(context),
      _forgetGroup(provider),
    ],
        trailingText: (trailing) => trailing is _PendingSyncChip
            ? OmiDuration.compact(trailing.seconds, l10n)
            : trailing is OmiSpinner
                ? l10n.loading
                : null);
    if (projected == null) return classic;
    // The same picture, from the same arguments, as the classic header.
    _watchThumbnail(DeviceUtils.getDeviceImagePathWithState(
      deviceType: connected?.type,
      modelNumber: connected?.modelNumber,
      deviceName: connected?.name ?? paired?.name,
      isConnected: connected != null,
    ));
    return IosNativeSurface(title: l10n.deviceSettings, fallback: classic, toolbar: [
      NativeRow('device_back', l10n.back, symbol: 'chevron.left', action: (_) => Navigator.of(context).pop()),
    ], sections: [
      NativeSection('device_status', [
        NativeRow('device_name', deviceDisplayName(paired?.name, l10n.omiAppName),
            kind: 'label',
            imageUri: _thumbnailUri,
            subtitle: provider.isConnected ? l10n.connected : l10n.disconnected),
        if (connected != null && provider.batteryLevel > 0)
          NativeRow('device_battery', l10n.battery,
              kind: 'label', subtitle: '${provider.batteryLevel}%${provider.isCharging ? ' · ${l10n.charging}' : ''}'),
        // Shown in place of the device controls while the device is not connected.
        if (!provider.isConnected)
          NativeRow('device_disconnected', l10n.deviceNotConnected, kind: 'label', subtitle: l10n.connectDeviceMessage),
      ]),
      ..._nativeDeviceControls(projected),
      if (connected != null && capture != null && capture.havingRecordingDevice)
        NativeSection('device_streaming', [
          NativeRow('device_stream_rates', l10n.diagnostics,
              kind: 'label',
              subtitle:
                  'BLE ${l10n.dataRateKbps(capture.bleReceiveRateKbps.toStringAsFixed(1))} · WebSocket ${l10n.dataRateKbps(capture.wsSendRateKbps.toStringAsFixed(1))}'),
        ]),
    ]);
  }
}

/// How much recording is waiting on the device to be synced ("4m 10s"), in the warning colour.
class _PendingSyncChip extends StatelessWidget {
  const _PendingSyncChip({required this.seconds});

  final int seconds;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
      decoration: BoxDecoration(color: OmiColors.warning.withValues(alpha: 0.15), borderRadius: OmiRadius.pillAll),
      child: Text(
        OmiDuration.compact(seconds, context.l10n),
        style: OmiType.footnote.copyWith(color: OmiColors.warning, fontWeight: FontWeight.w500),
      ),
    );
  }
}
