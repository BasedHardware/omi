import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'firmware_update_dialog.dart';

class FirmwareUpdate extends StatefulWidget {
  final BtDevice? device;
  final bool isRollback;

  const FirmwareUpdate({super.key, this.device, this.isRollback = false});

  @override
  State<FirmwareUpdate> createState() => _FirmwareUpdateState();
}

class _FirmwareUpdateState extends State<FirmwareUpdate> with FirmwareMixin {
  bool shouldUpdate = false;
  String updateMessage = '';
  bool isLoading = false;

  // Store reference to provider for safe disposal
  DeviceProvider? _deviceProvider;

  @override
  void initState() {
    var device = widget.device!;

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      Provider.of<DeviceProvider>(context, listen: false).setOnFirmwareUpdatePage(true);
      setState(() {
        isLoading = true;
      });

      if (widget.isRollback) {
        await getStableVersion(deviceModelNumber: device.modelNumber);
        if (mounted) {
          setState(() {
            shouldUpdate = latestFirmwareDetails.isNotEmpty && latestFirmwareDetails['version'] != null;
            updateMessage = shouldUpdate ? '' : context.l10n.noStableFirmwareFound;
            isLoading = false;
          });
        }
      } else {
        await getLatestVersion(
          deviceModelNumber: device.modelNumber,
          firmwareRevision: device.firmwareRevision,
          hardwareRevision: device.hardwareRevision,
          manufacturerName: device.manufacturerName,
        );
        var result = await shouldUpdateFirmware(currentFirmware: widget.device!.firmwareRevision);
        if (mounted) {
          setState(() {
            shouldUpdate = result.$2;
            updateMessage =
                widget.device!.firmwareRevision.isEmpty ? context.l10n.unableToDetermineFirmwareVersion : result.$1;
            isLoading = false;
          });
        }
      }
    });
    super.initState();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
  }

  @override
  void dispose() {
    killMcuUpdateManager();
    final provider = _deviceProvider;
    if (provider != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        provider.setOnFirmwareUpdatePage(false);
        provider.resetFirmwareUpdateState();
      });
    }
    super.dispose();
  }

  Widget _buildSectionHeader(String title, {String? subtitle}) => OmiSectionHeader(title, subtitle: subtitle);

  Widget _buildVersionItem(
      {required FaIconData icon, required String label, required String version, Color? chipColor}) {
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: Row(
        children: [
          SizedBox(width: 24, height: 24, child: FaIcon(icon, color: OmiColors.textTertiary, size: 18)),
          const SizedBox(width: OmiSpacing.md),
          Expanded(child: Text(label, style: OmiType.body)),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
            decoration: BoxDecoration(color: chipColor ?? OmiColors.surface2, borderRadius: OmiRadius.pillAll),
            child: Text(version, style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500)),
          ),
        ],
      ),
    );
  }

  Widget _card({required Widget child, EdgeInsetsGeometry padding = EdgeInsets.zero}) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
      child: child,
    );
  }

  /// "Do not close the app…" — shown before the update starts (in the pre-flight sheet) and while
  /// it runs.
  Widget _warningCard(String text) {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(
        color: OmiColors.warning.withValues(alpha: 0.12),
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.warning.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: [
          const ExcludeSemantics(
            child: FaIcon(FontAwesomeIcons.triangleExclamation, color: OmiColors.warning, size: 18),
          ),
          const SizedBox(width: 14),
          Expanded(child: Text(text, style: OmiType.subhead.copyWith(height: 1.4))),
        ],
      ),
    );
  }

  Widget _buildProgressSection() {
    final progress = isInstalling ? installProgress : downloadProgress;
    final statusText = isDownloading ? context.l10n.downloadingFirmware : context.l10n.installingFirmware;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _card(
          padding: const EdgeInsets.all(OmiSpacing.xxl),
          child: Semantics(
            liveRegion: true,
            label: '$statusText, $progress%',
            excludeSemantics: true,
            child: Column(
              children: [
                SizedBox(
                  width: 120,
                  height: 120,
                  child: Stack(
                    children: [
                      SizedBox(
                        width: 120,
                        height: 120,
                        child: CircularProgressIndicator(
                          // omi-ux-allow: raw-spinner -- determinate progress ring, not a spinner
                          value: progress / 100,
                          strokeWidth: 8,
                          backgroundColor: OmiColors.surface2,
                          valueColor: const AlwaysStoppedAnimation<Color>(OmiColors.textPrimary),
                        ),
                      ),
                      Center(child: Text('$progress%', style: OmiType.title1)),
                    ],
                  ),
                ),
                const SizedBox(height: OmiSpacing.xl),
                Text(statusText, style: OmiType.headline),
              ],
            ),
          ),
        ),
        const SizedBox(height: OmiSpacing.md),
        _warningCard(context.l10n.firmwareUpdateWarning),
      ],
    );
  }

  Widget _buildSuccessSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _card(
          padding: const EdgeInsets.all(OmiSpacing.xxl),
          child: Column(
            children: [
              Container(
                width: 80,
                height: 80,
                decoration: const BoxDecoration(color: OmiColors.successSurface, shape: BoxShape.circle),
                child: const Center(child: FaIcon(FontAwesomeIcons.check, color: OmiColors.success, size: 32)),
              ),
              const SizedBox(height: OmiSpacing.xl),
              Semantics(header: true, child: Text(context.l10n.firmwareUpdated, style: OmiType.title3)),
              const SizedBox(height: OmiSpacing.xs),
              Text(
                context.l10n.restartDeviceToComplete(widget.device?.name ?? 'Omi'),
                textAlign: TextAlign.center,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
              ),
            ],
          ),
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiButton(
          key: const Key('firmware_update_done'),
          label: context.l10n.done,
          expand: true,
          onPressed: () {
            final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
            deviceProvider.resetFirmwareUpdateState();
            // Back to the Home underneath, not a second Home on top of the stack.
            HomeNavigation.returnHome(context);
          },
        ),
      ],
    );
  }

  /// A failed update says why, whether the device is safe, and what to do next (onboarding-home #16).
  Widget _buildFailedSection(FirmwareUpdateFailure failure) {
    final message = switch (failure) {
      FirmwareUpdateFailure.download => context.l10n.firmwareDownloadFailedMessage,
      FirmwareUpdateFailure.install => context.l10n.firmwareUpdateFailedMessage,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _card(
          padding: const EdgeInsets.all(OmiSpacing.xxl),
          child: Semantics(
            liveRegion: true,
            child: Column(
              children: [
                Container(
                  width: 80,
                  height: 80,
                  decoration: const BoxDecoration(color: OmiColors.dangerSurface, shape: BoxShape.circle),
                  child: const Center(child: FaIcon(FontAwesomeIcons.xmark, color: OmiColors.danger, size: 32)),
                ),
                const SizedBox(height: OmiSpacing.xl),
                Semantics(header: true, child: Text(context.l10n.firmwareUpdateFailedTitle, style: OmiType.title3)),
                const SizedBox(height: OmiSpacing.xs),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiButton(
          key: const Key('firmware_update_try_again'),
          label: context.l10n.tryAgain,
          leading: const FaIcon(FontAwesomeIcons.arrowRotateLeft),
          expand: true,
          onPressed: () {
            clearFirmwareFailure();
            _startUpdate();
          },
        ),
        const SizedBox(height: OmiSpacing.xs),
        OmiButton.secondary(
          key: const Key('firmware_update_contact_support'),
          label: context.l10n.contactSupportAction,
          expand: true,
          onPressed: () => IntercomManager.instance.intercom.displayMessenger(),
        ),
      ],
    );
  }

  /// Starts the update after the pre-flight: battery enforced in code (not a checklist item), the
  /// risky-version warning, then the checklist sheet with the "don't close the app" warning.
  Future<void> _startUpdate() async {
    final deviceProvider = Provider.of<DeviceProvider>(context, listen: false);
    if (_batteryTooLow(deviceProvider)) return;
    var targetVersion = latestFirmwareDetails['version']?.toString() ?? '';
    if (targetVersion.startsWith('3.0.17')) {
      final confirmed = await showOmiConfirm(
        context,
        title: context.l10n.firmwareWarningTitle,
        message: context.l10n.firmwareFormatWarning,
        confirmLabel: context.l10n.continueAnyway,
        destructive: true,
      );
      if (!confirmed || !mounted) return;
    }

    showFirmwareUpdateSheet(
      context: context,
      steps: otaUpdateSteps,
      onUpdateStart: () async {
        deviceProvider.setFirmwareUpdateInProgress(true);
        if (await downloadFirmware()) {
          await startDfu(widget.device!);
        }
      },
    );
  }

  bool _batteryTooLow(DeviceProvider provider) =>
      provider.batteryLevel > 0 && provider.batteryLevel < kFirmwareUpdateMinBattery && !provider.isCharging;

  Widget _buildUpdateSection() {
    dynamic changelogData = latestFirmwareDetails['changelog'];
    bool hasChangelog = changelogData != null && changelogData is List && (List<String>.from(changelogData)).isNotEmpty;
    final deviceProvider = context.watch<DeviceProvider>();
    final batteryTooLow = _batteryTooLow(deviceProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Up to date status (only when not needing update)
        if (!shouldUpdate) ...[
          Padding(
            padding: const EdgeInsets.only(left: OmiSpacing.xxs, bottom: OmiSpacing.sm),
            child: Row(
              children: [
                Flexible(
                  child: Text(
                    widget.isRollback ? context.l10n.alreadyOnStableFirmware : context.l10n.yourDeviceIsUpToDate,
                    style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                  ),
                ),
                const SizedBox(width: OmiSpacing.xs),
                const FaIcon(FontAwesomeIcons.circleCheck, color: OmiColors.success, size: 14),
              ],
            ),
          ),
        ],
        // Version cards
        _card(
          child: Column(
            children: [
              _buildVersionItem(
                icon: FontAwesomeIcons.microchip,
                label: context.l10n.currentVersion,
                version: widget.device!.firmwareRevision,
                chipColor: shouldUpdate ? OmiColors.dangerSurface : null,
              ),
              if (shouldUpdate && latestFirmwareDetails['version'] != null) ...[
                const Divider(height: 1, color: OmiColors.border),
                _buildVersionItem(
                  icon: FontAwesomeIcons.cloudArrowDown,
                  label: context.l10n.latestVersion,
                  version: '${latestFirmwareDetails['version']}',
                  chipColor: OmiColors.successSurface,
                ),
              ],
            ],
          ),
        ),

        // Changelog
        if (hasChangelog) ...[
          const SizedBox(height: OmiSpacing.xl),
          _buildSectionHeader(context.l10n.whatsNew),
          _card(
            padding: const EdgeInsets.all(OmiSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ...(List<String>.from(changelogData)).map(
                  (change) => Padding(
                    padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Container(
                          margin: const EdgeInsets.only(top: 6),
                          width: 6,
                          height: 6,
                          decoration: const BoxDecoration(color: OmiColors.textTertiary, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: OmiSpacing.sm),
                        Expanded(
                          child: Text(change,
                              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4)),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],

        const SizedBox(height: OmiSpacing.xl),

        // Action buttons
        if (shouldUpdate && firmwareUpdatePolicy.allowsOmiFirmwareUpdate) ...[
          if (batteryTooLow) ...[
            _warningCard(context.l10n.firmwareBatteryTooLow(deviceProvider.batteryLevel)),
            const SizedBox(height: OmiSpacing.md),
          ],
          OmiButton(
            key: const Key('firmware_update_start'),
            label: widget.isRollback
                ? context.l10n.installStableFirmware
                : otaUpdateSteps.isEmpty
                    ? context.l10n.installUpdate
                    : context.l10n.updateNow,
            leading: const FaIcon(FontAwesomeIcons.download),
            expand: true,
            onPressed: batteryTooLow ? null : _startUpdate,
          ),
        ],

        // Help link
        if (!shouldUpdate) ...[
          const SizedBox(height: OmiSpacing.sm),
          OmiButton.secondary(
            label: context.l10n.updateGuide,
            leading: const FaIcon(FontAwesomeIcons.circleQuestion),
            expand: true,
            onPressed: () => IntercomManager.instance.displayFirmwareUpdateArticle(),
          ),
        ],
      ],
    );
  }

  Widget _buildLoadingSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader(
          widget.isRollback ? context.l10n.stableFirmware : context.l10n.checkingForUpdates,
          subtitle: context.l10n.pleaseWait,
        ),
        _card(
          padding: const EdgeInsets.all(48),
          child: OmiSpinner(
            label: widget.isRollback ? context.l10n.fetchingStableFirmware : context.l10n.checkingFirmwareVersion,
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final busy = isDownloading || isInstalling;
    final failure = updateFailure;
    return PopScope(
      canPop: !busy,
      child: Scaffold(
        backgroundColor: OmiColors.surface0,
        appBar: AppBar(
          automaticallyImplyLeading: false,
          // No way back while the device is being written; the PopScope blocks system back too.
          leading: busy ? null : const OmiBackButton(),
          title: Text(widget.isRollback ? context.l10n.stableFirmware : context.l10n.firmwareUpdate),
        ),
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg, vertical: OmiSpacing.md),
            child: isLoading
                ? _buildLoadingSection()
                : busy
                    ? _buildProgressSection()
                    : isInstalled
                        ? _buildSuccessSection()
                        : failure != null
                            ? _buildFailedSection(failure)
                            : _buildUpdateSection(),
          ),
        ),
      ),
    );
  }
}
