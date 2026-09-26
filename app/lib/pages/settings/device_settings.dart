import 'dart:async';

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
import 'package:omi/pages/settings/device/device_control_sheets.dart';
import 'package:omi/pages/settings/device/device_info_groups.dart';
import 'package:omi/pages/settings/device/device_page_header.dart';
import 'package:omi/pages/settings/device_diagnostics.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/rayban_meta_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/enums.dart';
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
/// Which levels a device supports and their current values (LED brightness 0–100, mic gain 0–8).
typedef DeviceLevels = ({bool hasDimming, bool hasMicGain, int? dimRatio, int? micGain});

/// Reads [DeviceLevels] from the device with [deviceId]; null when it cannot be reached.
typedef DeviceLevelsLoader = Future<DeviceLevels?> Function(String deviceId);

class DeviceSettings extends StatefulWidget {
  const DeviceSettings({super.key, this.levelsLoader});

  /// Defaults to asking the device over its connection.
  final DeviceLevelsLoader? levelsLoader;

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

  CaptureProvider? _captureProvider;

  double _dimRatio = 100.0;
  bool _isDimRatioLoaded = false;
  bool? _hasDimmingFeature;

  double _micGain = 5.0;
  bool _isMicGainLoaded = false;
  bool? _hasMicGainFeature;

  Timer? _debounce;
  Timer? _micGainDebounce;
  bool _isFindingDevice = false;

  bool _autoSyncOfflineRecordings = SharedPreferencesUtil().autoSyncOfflineRecordings;
  bool _omiButtonActionsEnabled = SharedPreferencesUtil().omiButtonActionsEnabled;

  Future<String>? _rayBanMetaCameraStatusFuture;
  String? _rayBanMetaCameraStatusDeviceId;

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
    super.dispose();
  }

  // Device features: LED dimming and mic gain.

  static Future<DeviceLevels?> _readDeviceLevels(String deviceId) async {
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return null;
    final features = await connection.getFeatures();
    final hasDimming = (features & OmiFeatures.ledDimming) != 0;
    final hasMicGain = (features & OmiFeatures.micGain) != 0;
    return (
      hasDimming: hasDimming,
      hasMicGain: hasMicGain,
      dimRatio: hasDimming ? await connection.getLedDimRatio() : null,
      micGain: hasMicGain ? await connection.getMicGain() : null,
    );
  }

  Future<void> _loadDeviceFeatures() async {
    final deviceId = context.read<DeviceProvider>().pairedDevice?.id;
    if (deviceId == null) return;
    DeviceLevels? levels;
    try {
      levels = await (widget.levelsLoader ?? _readDeviceLevels)(deviceId);
    } catch (e) {
      // A device that cannot be asked simply shows no level controls.
      Logger.debug('DeviceSettings: could not read device levels: $e');
    }
    if (!mounted || levels == null) return;
    final read = levels;
    setState(() {
      _hasDimmingFeature = read.hasDimming;
      _hasMicGainFeature = read.hasMicGain;
      // Loaded; without a value the default stays.
      if (read.dimRatio != null) _dimRatio = read.dimRatio!.toDouble();
      if (read.micGain != null) _micGain = read.micGain!.toDouble();
      _isDimRatioLoaded = true;
      _isMicGainLoaded = true;
    });
  }

  Future<void> _updateDimRatio(double value) async {
    final deviceProvider = context.read<DeviceProvider>();
    if (deviceProvider.pairedDevice == null) return;
    final connection = await ServiceManager.instance().device.ensureConnection(deviceProvider.pairedDevice!.id);
    await connection?.setLedDimRatio(value.toInt());
  }

  Future<void> _updateMicGain(double value) async {
    final deviceProvider = context.read<DeviceProvider>();
    if (deviceProvider.pairedDevice == null) return;
    final connection = await ServiceManager.instance().device.ensureConnection(deviceProvider.pairedDevice!.id);
    await connection?.setMicGain(value.toInt());
  }

  // Sliders preview while dragging (at most every 300 ms) and write the final value on release.

  void _onBrightnessChanged(double value) {
    setState(() => _dimRatio = value);
    if (!(_debounce?.isActive ?? false)) {
      _debounce = Timer(const Duration(milliseconds: 300), () => _updateDimRatio(value));
    }
  }

  void _onBrightnessChangeEnd(double value) {
    _debounce?.cancel();
    setState(() => _dimRatio = value);
    _updateDimRatio(value);
  }

  void _onMicGainChanged(double value) {
    setState(() => _micGain = value);
    if (!(_micGainDebounce?.isActive ?? false)) {
      _micGainDebounce = Timer(const Duration(milliseconds: 300), () => _updateMicGain(value));
    }
  }

  void _onMicGainChangeEnd(double value) {
    _micGainDebounce?.cancel();
    setState(() => _micGain = value);
    _updateMicGain(value);
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

  Future<String> _rayBanMetaCameraStatus(DeviceProvider provider) {
    final deviceId = provider.connectedDevice?.id;
    if (_rayBanMetaCameraStatusFuture == null || _rayBanMetaCameraStatusDeviceId != deviceId) {
      _rayBanMetaCameraStatusDeviceId = deviceId;
      _rayBanMetaCameraStatusFuture = () async {
        try {
          if (deviceId == null) return 'unavailable';
          final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
          if (connection is! RayBanMetaDeviceConnection) return 'unavailable';
          return await connection.getCameraPermissionStatus();
        } catch (_) {
          return 'unavailable';
        }
      }();
    }
    return _rayBanMetaCameraStatusFuture!;
  }

  Future<void> _captureRayBanMetaPhoto() async {
    try {
      final deviceId = context.read<DeviceProvider>().connectedDevice?.id;
      if (deviceId == null) return;
      final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
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
      final connection = await ServiceManager.instance().device.ensureConnection(device.id);
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

  // Sections (v2 `Device.dc`): controls, firmware and sync, finding and help, About, then Forget.

  Widget _controlsGroup(BtDevice? device) {
    final l10n = context.l10n;
    final isOmi = device?.type == DeviceType.omi;
    final doubleTapRow = OmiSettingsRow(
      leading: const FaIcon(FontAwesomeIcons.handPointer),
      title: l10n.doubleTap,
      trailing: _MenuValue(_doubleTapActionLabel(SharedPreferencesUtil().doubleTapAction)),
      onTap: _pickDoubleTapAction,
    );
    return OmiSettingsGroup(
      children: [
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
          DeviceLevelRow(
            key: const Key('led_brightness_slider'),
            title: l10n.ledBrightness,
            value: _dimRatio,
            max: 100,
            divisions: 100,
            valueLabel: (value) => value.round() == 0 ? l10n.off : '${value.round()}%',
            onChanged: _onBrightnessChanged,
            onChangeEnd: _onBrightnessChangeEnd,
          ),
        if (_isMicGainLoaded && _hasMicGainFeature == true)
          DeviceLevelRow(
            key: const Key('mic_gain_slider'),
            title: l10n.micGain,
            value: _micGain,
            max: 8,
            divisions: 8,
            valueLabel: (value) => micGainLevelLabel(context, value.round()),
            note: micGainDescription(context, _micGain.round()),
            onChanged: _onMicGainChanged,
            onChangeEnd: _onMicGainChangeEnd,
          ),
      ],
    );
  }

  Widget _firmwareAndSyncGroup(DeviceProvider provider) {
    final l10n = context.l10n;
    const firmwarePolicy = FirmwareUpdateBuildPolicy.current;
    final paired = provider.pairedDevice;
    final connected = provider.connectedDevice;
    final isRayBan = paired?.type == DeviceType.raybanMeta;
    final pendingSeconds = _maybeProvider<SyncProvider>(context)?.missingWalsInSeconds ?? 0;

    return OmiSettingsGroup(
      children: [
        // The Meta AI app manages Ray-Ban firmware, so the update rows are hidden for it.
        if (!isRayBan && firmwarePolicy.allowsFirmwareUpdateForDevice(paired))
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.download),
            title: l10n.firmware,
            // An update needs the device itself, so without it the row says so and is inert.
            value: connected == null
                ? l10n.disconnected
                : provider.havingNewFirmware
                    ? l10n.updateAvailable
                    : l10n.upToDate,
            showChevron: connected != null,
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
        OmiSettingsRow(
          leading: const FaIcon(FontAwesomeIcons.sdCard),
          title: l10n.offlineSync,
          trailing: pendingSeconds > 0 ? _PendingSyncChip(seconds: pendingSeconds) : null,
          showChevron: true,
          onTap: () => _openOfflineSync(provider),
        ),
        // The interactive device tutorial ("Speak Into Your Omi") is retired (2026-09-26): it
        // confused new accounts, and getting Omi to know you lives in To do now ("Teach Omi your
        // voice"). Its code stays in onboarding/interactive_device_onboarding, unreachable.
        // Ray-Ban Meta: on-demand photo capture.
        if (isRayBan)
          OmiSettingsRow(
            leading: const FaIcon(FontAwesomeIcons.camera),
            title: l10n.raybanMetaCapturePhoto,
            onTap: connected != null ? _captureRayBanMetaPhoto : null,
          ),
      ],
    );
  }

  Widget _helpGroup(DeviceProvider provider) {
    final l10n = context.l10n;
    final paired = provider.pairedDevice;
    final connected = provider.connectedDevice;
    final device = paired ?? connected;
    final supportsFind = provider.isConnected &&
        device?.type == DeviceType.omi &&
        !FirmwareUpdateBuildPolicy.current.isOpenGlassDevice(device);
    final diagnosticsId = paired?.id ?? connected?.id;
    return OmiSettingsGroup(
      children: [
        if (supportsFind)
          OmiSettingsRow(
            key: const Key('find_device_button'),
            leading: const FaIcon(FontAwesomeIcons.bullseye),
            title: l10n.findMyPendant,
            subtitle: l10n.findMyPendantHint,
            showChevron: false,
            trailing: _isFindingDevice ? const OmiSpinner(size: OmiSpinnerSize.small) : _PlayCapsule(l10n.play),
            onTap: () => _findDevice(provider),
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
        // Limitless pendants also need a BLE unpair so another phone can take them.
        if (provider.isConnected && provider.connectedDevice?.type == DeviceType.limitless)
          OmiSettingsRow(
            title: l10n.unpairAndForget,
            isDestructive: true,
            showChevron: false,
            onTap: () => _unpairLimitless(provider),
          ),
        OmiSettingsRow(
          key: const Key('forget_device_button'),
          title: l10n.forgetDevice,
          isDestructive: true,
          showChevron: false,
          onTap: () => _forgetDevice(provider),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<DeviceProvider>();
    final capture = _maybeProvider<CaptureProvider>(context);
    final paired = provider.pairedDevice;
    final connected = provider.connectedDevice;
    final receivingAudio = connected != null &&
        capture != null &&
        capture.havingRecordingDevice &&
        capture.recordingState == RecordingState.deviceRecord &&
        !capture.isPaused;
    const gap = SizedBox(height: 22);

    // v2 `Device.dc`: a sheet-coloured page titled with the device's name.
    return Scaffold(
      backgroundColor: OmiColors.sheet,
      appBar: OmiAppBar(
        leading: const OmiBackButton(),
        backgroundColor: OmiColors.sheet,
        inlineTitle: Text(paired?.name ?? connected?.name ?? context.l10n.unknownDevice),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.md, 50),
        children: [
          DeviceHeroCard(
            pairedDevice: paired,
            connectedDevice: connected,
            isConnecting: provider.isConnecting,
            isReceivingAudio: receivingAudio,
            batteryLevel: connected != null ? provider.batteryLevel : -1,
            isCharging: connected != null && provider.isCharging,
          ),
          gap,
          if (provider.isConnected) _controlsGroup(paired ?? connected) else const DeviceDisconnectedCard(),
          gap,
          _firmwareAndSyncGroup(provider),
          gap,
          _helpGroup(provider),
          gap,
          DeviceInfoGroups(
            pairedDevice: paired,
            isDeviceConnected: connected != null,
            rayBanCameraStatus: paired?.type == DeviceType.raybanMeta ? _rayBanMetaCameraStatus(provider) : null,
          ),
          gap,
          _forgetGroup(provider),
          if (connected != null && capture != null && capture.havingRecordingDevice) ...[
            gap,
            DeviceStreamingMetrics(bleReceiveKbps: capture.bleReceiveRateKbps, wsSendKbps: capture.wsSendRateKbps),
          ],
        ],
      ),
    );
  }
}

/// A menu row's current choice with the up-down glyph (v2 `Device.dc` "End conversation ⌃⌄").
class _MenuValue extends StatelessWidget {
  const _MenuValue(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 190),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: OmiType.body.copyWith(color: OmiColors.textSecondary),
            ),
          ),
          const SizedBox(width: OmiSpacing.xxs),
          Icon(Icons.unfold_more_rounded, size: 18, color: OmiColors.textTertiary),
        ],
      ),
    );
  }
}

/// The small filled capsule at the end of an action row ("Play").
class _PlayCapsule extends StatelessWidget {
  const _PlayCapsule(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 32,
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm),
      alignment: Alignment.center,
      decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.pillAll),
      child: Text(label, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
    );
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
