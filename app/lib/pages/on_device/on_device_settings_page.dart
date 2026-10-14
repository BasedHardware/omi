import 'dart:async';

import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/on_device/on_device_components.dart';
import 'package:omi/pages/on_device/on_device_queue_banner.dart';
import 'package:omi/pages/on_device/on_device_schedule_page.dart';
import 'package:omi/pages/on_device/on_device_setup_page.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// The month's live-hours meter, as the settings page shows it.
@immutable
class OnDeviceLiveHours {
  const OnDeviceLiveHours({required this.usedSeconds, required this.limitSeconds, required this.resetsOn});

  final int usedSeconds;
  final int limitSeconds;
  final DateTime resetsOn;

  /// Live hours are metered per UTC calendar month, so they come back on the 1st. Returned as a
  /// calendar date (local midnight) so it displays as the 1st in every time zone.
  static DateTime nextReset(DateTime now) {
    final utc = now.toUtc();
    return DateTime(utc.year, utc.month + 1, 1);
  }
}

/// Settings › Transcription › On-Device Transcription, reading the app's providers.
class OnDeviceSettingsPage extends StatelessWidget {
  const OnDeviceSettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final usage = context.watch<UsageProvider>();
    final subscription = usage.subscription;
    final recordings =
        context.watch<LocalRecordingsProvider>().recordings.where((r) => r.state == LocalRecordingState.pending);
    return OnDeviceSettingsView(
      liveHours: subscription == null || subscription.transcriptionSecondsLimit <= 0
          ? null
          : OnDeviceLiveHours(
              usedSeconds: subscription.transcriptionSecondsUsed,
              limitSeconds: subscription.transcriptionSecondsLimit,
              resetsOn: OnDeviceLiveHours.nextReset(DateTime.now()),
            ),
      showSaveLiveHours: subscription?.subscription.plan.isPaid ?? false,
      pendingSeconds: recordings.fold(0, (sum, r) => sum + r.seconds),
      pendingBytes: recordings.fold(0, (sum, r) => sum + r.sizeBytes),
      onGetMoreLiveHours: () => openOnDeviceUpgrade(context),
    );
  }
}

class OnDeviceSettingsView extends StatelessWidget {
  const OnDeviceSettingsView({
    super.key,
    required this.liveHours,
    required this.showSaveLiveHours,
    required this.pendingSeconds,
    required this.pendingBytes,
    required this.onGetMoreLiveHours,
    this.controller,
  });

  final OnDeviceLiveHours? liveHours;

  /// Paid plans can transcribe on the phone before live hours run out, to save them.
  final bool showSaveLiveHours;
  final int pendingSeconds;
  final int pendingBytes;
  final VoidCallback onGetMoreLiveHours;
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
          final hours = liveHours;
          return ListView(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxl),
            children: [
              if (hours != null) ...[
                OmiSettingsGroup(
                  header: l10n.onDeviceLiveHours,
                  children: [
                    _LiveHoursMeter(hours: hours),
                    OmiSettingsRow(
                      key: const Key('on_device_settings_more_hours'),
                      leading: const Icon(Icons.bolt),
                      title: l10n.onDeviceGetMoreLiveHours,
                      onTap: onGetMoreLiveHours,
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
                    onChanged: (value) => controller.updateSettings(settings.copyWith(enabled: value)),
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
              if (showSaveLiveHours) ...[
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
                  OmiSettingsRow(
                    key: const Key('on_device_settings_model'),
                    leading: const Icon(Icons.graphic_eq),
                    title: l10n.onDeviceSpeechModel,
                    value: onDeviceModelStatusLabel(l10n, status, wifiOnly: settings.wifiOnlyDownload),
                    onTap: status.isSupported && !status.isInstalled
                        ? () => unawaited(routeToPage(context, OnDeviceSetupPage(controller: this.controller)))
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
                  if (status.isInstalled)
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

class _LiveHoursMeter extends StatelessWidget {
  const _LiveHoursMeter({required this.hours});

  final OnDeviceLiveHours hours;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final format = NumberFormat.decimalPattern(l10n.localeName)..maximumFractionDigits = 1;
    String asHours(int seconds) => format.format(seconds / 3600);
    final ratio = hours.limitSeconds > 0 ? hours.usedSeconds / hours.limitSeconds : 0.0;
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  l10n.onDeviceLiveHoursUsed(asHours(hours.usedSeconds), asHours(hours.limitSeconds)),
                  style: OmiType.body,
                ),
              ),
              const SizedBox(width: OmiSpacing.xs),
              Text(
                l10n.onDeviceResets(OmiDateFormat.of(context).date(hours.resetsOn)),
                style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.sm),
          OnDeviceProgressBar(value: ratio),
        ],
      ),
    );
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
