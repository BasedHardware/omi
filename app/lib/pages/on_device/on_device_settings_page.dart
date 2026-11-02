import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/pages/on_device/on_device_queue_banner.dart';
import 'package:omi/pages/on_device/on_device_schedule_page.dart';
import 'package:omi/pages/on_device/on_device_setup_page.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/experiments/plan_storefront_gate.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Shared usage resets on the 1st of the next UTC month when the backend date is unknown.
/// Returned as a calendar date (local midnight) so it displays as the 1st in every time zone.
DateTime onDeviceUsageResetsOn(DateTime now) {
  final utc = now.toUtc();
  return DateTime(utc.year, utc.month + 1, 1);
}

/// Settings › Transcription › On-Device Transcription, reading the app's providers.
class OnDeviceSettingsPage extends StatefulWidget {
  const OnDeviceSettingsPage({super.key, this.controller, this.loadUsage});

  final OnDeviceTranscriptionController? controller;
  final Future<StorefrontUsage?> Function(String locale)? loadUsage;

  @override
  State<OnDeviceSettingsPage> createState() => _OnDeviceSettingsPageState();
}

class _OnDeviceSettingsPageState extends State<OnDeviceSettingsPage> {
  StorefrontUsage? _usage;
  bool _plansSheet = false;
  Future<void>? _loading;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _loading ??= _load();
  }

  Future<void> _load() async {
    final provider = context.read<UsageProvider>();
    final sheet = provider.showSubscriptionUI && await PlanStorefrontGate.sheetEnabled();
    if (!mounted) return;
    final usage = await (widget.loadUsage ?? loadOnDeviceUsage)(context.l10n.localeName);
    if (!mounted) return;
    setState(() {
      _plansSheet = sheet;
      _usage = usage;
    });
  }

  @override
  Widget build(BuildContext context) {
    final subscription = context.watch<UsageProvider>().subscription;
    final recordings =
        context.watch<LocalRecordingsProvider>().recordings.where((r) => r.state == LocalRecordingState.pending);
    return OnDeviceSettingsView(
      usage: _usage,
      plansSheetAvailable: _plansSheet,
      showSaveUsage: subscription?.subscription.plan.isPaid ?? false,
      pendingSeconds: recordings.fold<int>(0, (sum, r) => sum + r.seconds) +
          (widget.controller ?? OnDeviceTranscriptionController.instance).pendingSeconds,
      pendingBytes: recordings.fold(0, (sum, r) => sum + r.sizeBytes),
      onGetMoreUsage: () => unawaited(openOnDeviceUsagePlans(context)),
      controller: widget.controller,
    );
  }
}

class OnDeviceSettingsView extends StatelessWidget {
  const OnDeviceSettingsView({
    super.key,
    required this.usage,
    required this.plansSheetAvailable,
    required this.showSaveUsage,
    required this.pendingSeconds,
    required this.pendingBytes,
    required this.onGetMoreUsage,
    this.controller,
  });

  /// Backend usage payload. The meter and the get-more label are its strings; absent means no meter.
  final StorefrontUsage? usage;

  /// The contextual plans sheet can open. The get-more row stays hidden otherwise.
  final bool plansSheetAvailable;

  /// Paid plans can transcribe on the phone before the shared budget runs out.
  final bool showSaveUsage;
  final int pendingSeconds;
  final int pendingBytes;
  final VoidCallback onGetMoreUsage;
  final OnDeviceTranscriptionController? controller;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final controller = this.controller ?? OnDeviceTranscriptionController.instance;
    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.onDeviceTranscription)),
      body: ListenableBuilder(
        listenable: Listenable.merge([controller, controller.model]),
        builder: (context, _) {
          final settings = controller.settings;
          final status = controller.model.status;
          final meter = usage;
          final meterLine = meter == null ? null : onDeviceMeterLine(meter);
          final showMeter = meter != null && meterLine != null && meterLine.isNotEmpty;
          final moreTitle = onDeviceMoreUsageTitle(
            plansSheetAvailable: plansSheetAvailable,
            moreLabel: meter?.moreLabel,
          );
          final showMore = moreTitle != null;
          final modelKnown = controller.model.engineResolved;
          final detectionFailed = controller.model.detectionFailed;
          final showModelRows = modelKnown && !detectionFailed && !controller.model.isOsManaged;
          final showSpeechProgress =
              modelKnown && controller.model.isOsManaged && status.phase == OnDeviceModelPhase.downloading;
          return ListView(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
            children: [
              if (showMeter || showMore) ...[
                OmiSettingsGroup(
                  children: [
                    if (showMeter) StorefrontUsageMeter(usage: meter.withMeterLine(meterLine), embedded: true),
                    if (showMore)
                      OmiSettingsRow(
                        key: const Key('on_device_settings_more_usage'),
                        leading: const Icon(Icons.bolt),
                        title: moreTitle,
                        onTap: onGetMoreUsage,
                      ),
                  ],
                ),
                const SizedBox(height: OmiSpacing.lg),
              ],
              if (detectionFailed) ...[
                OmiSettingsGroup(
                  children: [
                    OmiSettingsRow(
                      key: const Key('on_device_settings_engine_unavailable'),
                      leading: const Icon(Icons.graphic_eq),
                      title: l10n.onDeviceModelUnsupported,
                      value: l10n.tryAgain,
                      onTap: () => unawaited(controller.model.refresh()),
                    ),
                  ],
                ),
                const SizedBox(height: OmiSpacing.lg),
              ],
              if (showSpeechProgress) ...[
                OmiSettingsGroup(
                  children: [
                    OmiSettingsRow(
                      key: const Key('on_device_settings_speech_progress'),
                      leading: const Icon(Icons.graphic_eq),
                      title: l10n.onDeviceGettingSpeechReady((status.progress * 100).floor()),
                    ),
                  ],
                ),
                const SizedBox(height: OmiSpacing.lg),
              ],
              OmiSettingsGroup(
                header: l10n.onDeviceAfterLiveHours,
                children: [
                  OmiSettingsRow.toggle(
                    key: const Key('on_device_settings_enabled'),
                    leading: Icon(onDevicePhoneIcon),
                    title: l10n.onDeviceTranscribeOnPhone,
                    value: settings.enabled,
                    onChanged: (value) {
                      unawaited(() async {
                        await controller.updateSettings(settings.copyWith(enabled: value));
                        if (!context.mounted || !value) return;
                        final model = controller.model;
                        if (!model.engineResolved) await model.refresh();
                        if (!context.mounted || !model.isOsManaged) return;
                        if (!model.status.isInstalled && model.status.isSupported) {
                          await openOnDeviceSetup(context, controller: this.controller);
                        }
                      }());
                    },
                  ),
                  if (settings.enabled) ...[
                    OmiSettingsRow(
                      key: const Key('on_device_settings_when'),
                      leading: const Icon(Icons.schedule),
                      title: l10n.onDeviceWhen,
                      value: onDeviceScheduleLabel(l10n, settings.schedule),
                      onTap: () => unawaited(routeToPage(context, OnDeviceSchedulePage(controller: this.controller))),
                      showChevron: true,
                    ),
                    OmiSettingsRow(
                      leading: const Icon(Icons.notes),
                      title: l10n.onDeviceSummaries,
                      value: settings.keepEverythingOnDevice
                          ? l10n.off
                          : controller.canSummarizeOnPhone
                              ? l10n.onDeviceSummariesOnIphone
                              : l10n.onDeviceSummariesCloud,
                    ),
                    OmiSettingsRow.toggle(
                      key: const Key('on_device_settings_keep'),
                      leading: const Icon(Icons.lock_outline),
                      title: l10n.onDeviceKeepEverything,
                      subtitle: l10n.onDeviceKeepEverythingSubtitle,
                      value: settings.keepEverythingOnDevice,
                      onChanged: (value) => controller.updateSettings(settings.copyWith(keepEverythingOnDevice: value)),
                    ),
                  ],
                ],
              ),
              if (showSaveUsage) ...[
                const SizedBox(height: OmiSpacing.lg),
                OmiSettingsGroup(
                  children: [
                    OmiSettingsRow.toggle(
                      key: const Key('on_device_settings_save_hours'),
                      title: l10n.onDeviceSaveLiveHours,
                      subtitle: l10n.onDeviceSaveLiveHoursSubtitle,
                      value: settings.saveLiveHours,
                      onChanged: (value) => controller.updateSettings(settings.copyWith(saveLiveHours: value)),
                    ),
                  ],
                ),
              ],
              const SizedBox(height: OmiSpacing.lg),
              OmiSettingsGroup(
                header: l10n.onDeviceOnThisPhone,
                children: [
                  if (showModelRows)
                    OmiSettingsRow(
                      key: const Key('on_device_settings_model'),
                      leading: const Icon(Icons.graphic_eq),
                      title: l10n.onDeviceSpeechModel,
                      value: onDeviceModelStatusLabel(l10n, status, wifiOnly: settings.wifiOnlyDownload),
                      onTap: status.isSupported && !status.isInstalled
                          ? () => unawaited(openOnDeviceSetup(context, controller: this.controller))
                          : null,
                    ),
                  OmiSettingsRow(
                    leading: const Icon(Icons.schedule),
                    title: l10n.onDeviceWaitingToTranscribe,
                    value: OmiDuration.compact(pendingSeconds, l10n),
                  ),
                  OmiSettingsRow(
                    leading: const Icon(Icons.mic_none),
                    title: l10n.onDeviceAudioWaiting,
                    value: onDeviceSizeLabel(l10n, pendingBytes),
                  ),
                  if (status.isInstalled && showModelRows)
                    OmiSettingsRow(
                      key: const Key('on_device_settings_remove'),
                      leading: const Icon(Icons.delete_outline),
                      title: l10n.onDeviceRemoveModel,
                      isDestructive: true,
                      showChevron: false,
                      onTap: () => _confirmRemove(context, controller),
                    ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _confirmRemove(BuildContext context, OnDeviceTranscriptionController controller) async {
    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.onDeviceRemoveModelTitle,
      message: l10n.onDeviceRemoveModelMessage,
      confirmLabel: l10n.onDeviceRemove,
      destructive: true,
    );
    if (confirmed) await controller.model.remove();
  }
}

/// The row on the Transcription settings page that opens [OnDeviceSettingsPage]. Nothing while the
/// on-device flag is off.
class OnDeviceSettingsEntry extends StatefulWidget {
  const OnDeviceSettingsEntry({super.key, this.controller});

  final OnDeviceTranscriptionController? controller;

  @override
  State<OnDeviceSettingsEntry> createState() => _OnDeviceSettingsEntryState();
}

class _OnDeviceSettingsEntryState extends State<OnDeviceSettingsEntry> {
  OnDeviceTranscriptionController get _controller => widget.controller ?? OnDeviceTranscriptionController.instance;

  @override
  void initState() {
    super.initState();
    unawaited(_controller.ensureLoaded());
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return ListenableBuilder(
      listenable: _controller,
      builder: (context, _) {
        if (!_controller.isActive) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.sm),
          child: OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                key: const Key('on_device_settings_entry'),
                leading: Icon(onDevicePhoneIcon),
                title: l10n.onDeviceTranscription,
                subtitle: l10n.onDeviceEntrySubtitle,
                value: _controller.settings.enabled ? l10n.on : l10n.off,
                onTap: () => unawaited(routeToPage(context, const OnDeviceSettingsPage())),
                showChevron: true,
              ),
            ],
          ),
        );
      },
    );
  }
}
