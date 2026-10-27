import 'dart:async';

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/pages/settings/device/device_catching_up_card.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/omiglass_ota_update.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
import 'package:omi/pages/settings/device/device_control_sheets.dart';
import 'package:omi/pages/settings/device/device_info_groups.dart';
import 'package:omi/pages/settings/device/device_live_sections.dart';
import 'package:omi/pages/settings/device/heard_today.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/pages/settings/device/device_page_header.dart';
import 'package:omi/pages/settings/device_diagnostics.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/rayban_meta_connection.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/error_message.dart';
import 'package:omi/utils/firmware_update_build_policy.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// The one device page: status, controls, sync, firmware, device information and Forget Device.
///
/// Canonical implementation. It is reached from the Settings drawer, the capture "connect" flow,
/// the home-screen quick action, and (through the `ConnectedDevice` alias in
/// `pages/home/device.dart`) the header battery pill.
class DeviceSettings extends StatefulWidget {
  const DeviceSettings({super.key, this.pendingWork});

  /// Defaults to the same shared server view used by Home and the bell.
  final PendingWorkStore? pendingWork;

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

  PendingWorkStore get _pendingWork => widget.pendingWork ?? PendingWorkStore.instance;

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
      unawaited(_pendingWork.refresh());
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

  Future<void> _loadDeviceFeatures() async {
    final deviceProvider = context.read<DeviceProvider>();
    // BtDevice.empty() (id '') is the nothing-remembered sentinel, not a device to connect to.
    if (deviceProvider.pairedDevice?.id.isEmpty ?? true) return;
    final connection = await ServiceManager.instance().device.ensureConnection(deviceProvider.pairedDevice!.id);
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
              device: provider.pairedDevice,
              latestFirmwareDetails: provider.latestOmiGlassFirmwareDetails,
            )
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

  // Sections.

  Widget _customizationGroup(BtDevice? device, DeviceProvider provider) {
    final l10n = context.l10n;
    final isOmi = device?.type == DeviceType.omi;
    final supportsFind = isOmi && !FirmwareUpdateBuildPolicy.current.isOpenGlassDevice(device);
    final doubleTapRow = OmiSettingsRow(
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
            leading: const FaIcon(FontAwesomeIcons.lightbulb),
            title: l10n.ledBrightness,
            value: '${_dimRatio.round()}%',
            onTap: _showBrightnessSheet,
            showChevron: true,
          ),
        if (_isMicGainLoaded && _hasMicGainFeature == true)
          OmiSettingsRow(
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
    final pendingSeconds = context.select<SyncProvider?, int>((s) => s?.missingWalsInSeconds ?? 0);
    // getDeviceInfo() leaves pairedDevice as BtDevice.empty() (id '') when nothing is remembered;
    // native diagnostics are keyed by device id, so an empty id has no history to send.
    final diagnosticsId = (paired?.id.isNotEmpty ?? false) ? paired!.id : connected?.id;

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
        // Language is chosen in one place; the device page links to it.
        OmiSettingsRow(
          key: const Key('device_transcription_language'),
          leading: const FaIcon(FontAwesomeIcons.language),
          title: l10n.transcriptionLanguage,
          onTap: () => routeToPage(context, const TranscriptionSettingsPage()),
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
        // Native diagnostics persist per device, so a disconnected pendant can still send its
        // disconnect history and BLE log to support, which is when they matter most.
        if (diagnosticsId != null)
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

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<DeviceProvider>();
    final capture = context.read<CaptureProvider?>();
    // Audio metrics/transcript notifications must not rebuild the settings page.
    final (deviceSource, devicePaused, canPause) = context.select<CaptureProvider?, (String?, bool, bool)>(
      (c) => (c?.liveCaptureSource, c?.isPaused ?? false, c != null && EpisodePresentation.canPause(c)),
    );
    final paired = provider.pairedDevice;
    final connected = provider.connectedDevice;
    const gap = SizedBox(height: OmiSpacing.xxl);

    final deviceStreaming = capture != null && deviceSource != null && deviceSource != 'phone';

    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(leading: const OmiBackButton(), title: Text(context.l10n.deviceSettings)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 48),
        children: [
          DevicePageHeader(
            pairedDevice: paired,
            connectedDevice: connected,
            listening: connected != null && deviceStreaming && !devicePaused,
            paused: connected != null && deviceStreaming && devicePaused,
          ),
          const SizedBox(height: OmiSpacing.xl),
          _liveSections(
            connected: connected != null,
            batteryLevel: connected == null ? 0 : provider.batteryLevel,
            isCharging: connected != null && provider.isCharging,
          ),
          DeviceRecentlyGroup(load: provider.disconnectHistory),
          if (deviceStreaming && canPause) ...[
            DeviceControlsGroup(paused: devicePaused, onToggle: () => _togglePause(capture)),
            gap,
          ],
          if (provider.isConnected)
            _customizationGroup(paired ?? connected, provider)
          else
            const DeviceDisconnectedCard(),
          gap,
          _deviceGroup(provider),
          gap,
          DeviceInfoGroups(
            pairedDevice: paired,
            isDeviceConnected: connected != null,
            rayBanCameraStatus: paired?.type == DeviceType.raybanMeta ? _rayBanMetaCameraStatus(provider) : null,
          ),
          gap,
          _forgetGroup(provider),
          if (connected != null)
            Builder(builder: (context) {
              final metrics = context.select<CaptureProvider?, (bool, double, double)>(
                (c) => c == null || !c.havingRecordingDevice
                    ? (false, 0, 0)
                    : (true, c.bleReceiveRateKbps, c.wsSendRateKbps),
              );
              return metrics.$1
                  ? Column(children: [
                      gap,
                      DeviceStreamingMetrics(bleReceiveKbps: metrics.$2, wsSendKbps: metrics.$3),
                    ])
                  : const SizedBox.shrink();
            }),
        ],
      ),
    );
  }
}

extension _DeviceLiveSections on _DeviceSettingsState {
  Widget _liveSections({required bool connected, required int batteryLevel, required bool isCharging}) {
    const gap = SizedBox(height: OmiSpacing.xxl);
    return Builder(builder: (context) {
      // One WAL pass per sync notification, shared by Stats and Right now.
      // Capture/episode updates subscribe below this builder and never rescan it;
      // deviceCatchUpLocal memoizes on the WAL list identity, so a progress-only
      // notify reuses the last snapshot instead of rescanning, and the server
      // flag and status line select on their own.
      final l10n = context.l10n;
      final local =
          context.select<SyncProvider?, DeviceCatchUpLocal>((s) => deviceCatchUpLocal(s?.allWals ?? const []));
      final serverProcessing = context.select<SyncProvider?, bool>((s) => s?.syncState.isProcessing ?? false);
      // The status line reads sync state only; whether server jobs exist comes
      // from the memoized snapshot, so a progress tick never rescans the inventory.
      final syncStatus = context.select<SyncProvider?, String>((s) => s == null
          ? ''
          : SyncPendingWork.stageLabelFor(
              s.syncState,
              l10n,
              rateLimited: s.isRateLimited,
              rateLimitReason: s.isRateLimited ? s.rateLimitReason : null,
              serverJobs: local.hasUploaded || s.syncState.isProcessing,
            ));
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (connected) ...[
            Builder(
                builder: (context) => DeviceStatsRow(
                      batteryLevel: batteryLevel,
                      isCharging: isCharging,
                      heardTodaySeconds: _heardTodaySeconds(context),
                      onDeviceSeconds: local.onDeviceSeconds,
                      phoneQueueSeconds: local.onPhoneSeconds,
                    )),
            gap,
          ],
          ListenableBuilder(
            listenable: _pendingWork,
            builder: (context, _) {
              final rightNow =
                  _rightNow(context, local: local, serverProcessing: serverProcessing, syncStatus: syncStatus);
              return rightNow.hasContent ? Column(children: [rightNow, gap]) : const SizedBox.shrink();
            },
          ),
        ],
      );
    });
  }

  /// Speech heard today: transcript time inside today's local day across the
  /// loaded conversations, plus the active live episode's own interval since
  /// its start or anchor, merged so nothing is counted twice. A pendant that
  /// streams without a break files its conversations under the session's start
  /// day, so bucketing by that day hid today's speech.
  int _heardTodaySeconds(BuildContext context) {
    final liveEpisodeStart = _liveEpisodeStart(context);
    return context.select<ConversationProvider?, int>((conversations) {
      return heardTodaySpeechSeconds(
        conversations: conversations == null
            ? const []
            : [
                ...conversations.groupedConversations.values.expand((group) => group),
                ...conversations.processingConversations,
              ],
        now: DateTime.now(),
        liveEpisodeStart: liveEpisodeStart,
      );
    });
  }

  /// The active live episode's own start: the server episode's start, kept
  /// stable by the shared anchor across reconnects and restarts. Null when no
  /// episode is live. Never the capture session's origin
  /// (`liveCaptureStartedAt`): a pendant that streams without a break never
  /// resets it, so it would name the whole session as heard.
  DateTime? _liveEpisodeStart(BuildContext context) {
    final episodes = _maybeProvider<EpisodeProvider>(context, listen: false);
    if (episodes == null || !episodes.enabled) return null;
    final capture = _maybeProvider<CaptureProvider>(context, listen: false);
    return context.select<EpisodeProvider, DateTime?>((e) => _anchoredLiveEpisodeStart(e, capture, DateTime.now()));
  }

  static DateTime? _anchoredLiveEpisodeStart(EpisodeProvider e, CaptureProvider? capture, DateTime now) {
    final episode = e.live;
    if (episode == null) return null;
    if (capture == null) return episode.startedAt.isAfter(now) ? null : episode.startedAt;
    final elapsed = EpisodePresentation.elapsed(episode, capture, now, anchor: e.liveAnchor);
    return elapsed.inSeconds <= 0 ? null : now.subtract(elapsed);
  }

  DeviceRightNowGroup _rightNow(BuildContext context,
      {required DeviceCatchUpLocal local, required bool serverProcessing, required String syncStatus}) {
    final conversations = context.watch<ConversationProvider?>();
    final capture = context.read<CaptureProvider?>();
    // Only the visible source, its running length and its audio health depend on
    // capture, not its transcript text, socket state, or BLE/network rate samples.
    final (source, _, pendantFailed, pendantVerified, reconnecting) =
        context.select<CaptureProvider?, (String?, DateTime?, bool, bool, bool)>(
      (c) => (
        c?.liveCaptureSource,
        c?.liveCaptureStartedAt,
        c?.pendantCaptureActionRequired ?? false,
        c?.pendantCaptureVerified ?? true,
        c?.pendantReconnectInFlight ?? false,
      ),
    );
    final deviceStreaming = source != null && source != 'phone';
    final episodes = _maybeProvider<EpisodeProvider>(context);
    final live = episodes != null && episodes.enabled && deviceStreaming ? episodes.live : null;
    final l10n = context.l10n;
    // The pendant's own audio health names the row: a confirmed-subscription quiet
    // is Listening with a running length, a wait shows no length, and an exhausted
    // recovery is a failure with the one action that can fix it.
    final noAudio = deviceStreaming && pendantFailed;
    final connecting = deviceStreaming && !pendantFailed && !pendantVerified;
    return DeviceRightNowGroup(
      liveTitle: noAudio
          ? l10n.captureNoAudioFromPendant
          : live == null
              ? null
              : (live.title.isEmpty ? l10n.episodeListeningNow : live.title),
      liveSubtitle: noAudio
          ? l10n.captureNoAudioDetail
          : connecting
              ? l10n.captureConnecting
              : null,
      liveProblem: noAudio,
      // No tap while a reconnect runs: the controller ignores one anyway, and the
      // row saying nothing is quieter than a second teardown racing the first.
      onFixProblem: noAudio && capture != null && !reconnecting
          ? () {
              OmiHaptics.medium();
              final message = l10n.somethingWentWrong;
              capture.reconnectRecordingPendant().catchError((Object error) {
                AppSnackbar.showSnackbar(message);
              });
            }
          : null,
      liveLengthNow: live == null || capture == null || connecting
          ? null
          : (_) => EpisodePresentation.runningLength(
              EpisodePresentation.elapsed(live, capture, episodes!.now(), anchor: episodes.liveAnchor), l10n),
      onOpenLive: capture == null
          ? null
          : () => routeToPage(context, LiveEpisodePage(topConversationId: capture.topConversationId)),
      catchingUp: DeviceCatchUpSummary.from(
        local: local,
        serverProcessing: serverProcessing,
        // Local or phone-run work reads On the Way's own stage; server work the
        // phone did not start has no local stage to report.
        status: local.hasPending || serverProcessing ? syncStatus : l10n.processing,
        pending: _pendingWork.pending,
        conversations: conversations?.conversations ?? const [],
        processing: conversations?.processingConversations ?? const [],
      ),
      onOpenCatchingUp: () => routeToPage(context, OnTheWayPage(pendingWork: _pendingWork)),
    );
  }

  Future<void> _togglePause(CaptureProvider capture) async {
    try {
      OmiHaptics.medium();
      if (capture.isPaused) {
        await capture.resumeCapture();
      } else {
        await capture.pauseCapture();
      }
    } catch (_) {
      if (mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
    }
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
