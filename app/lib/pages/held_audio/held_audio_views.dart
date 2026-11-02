import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/models/subscription.dart';
import 'processing_backlog_view.dart';
import 'package:omi/pages/on_device/on_device_setup_page.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The UTC calendar day of the server-supplied reset instant, shown as that day
/// in every time zone. The client does not choose the month boundary.
DateTime heldAudioCalendarDate(int resetAtSeconds) {
  final utc = DateTime.fromMillisecondsSinceEpoch(resetAtSeconds * 1000, isUtc: true);
  return DateTime(utc.year, utc.month, utc.day);
}

/// Same eligibility as the on-device overflow offer: this phone can run the engine.
bool heldAudioPhoneEligible(OnDeviceTranscriptionController controller) {
  if (!controller.isActive || !controller.model.engineResolved || controller.model.detectionFailed) return false;
  return controller.model.status.isSupported;
}

Future<void> chooseHeldAudioOnPhone(BuildContext context, OnDeviceTranscriptionController controller) async {
  await controller.updateSettings(controller.settings.copyWith(enabled: true));
  if (!context.mounted) return;
  final model = controller.model;
  if (!model.engineResolved) await model.refresh();
  if (!context.mounted || !model.status.isSupported || model.status.isInstalled) return;
  await openOnDeviceSetup(context, controller: controller);
}

void openHeldAudioPlans(BuildContext context) {
  unawaited(openContextualPlans(context, source: 'held_audio', trigger: 'usage_budget'));
}

class HeldAudioCardView extends StatelessWidget {
  const HeldAudioCardView({
    super.key,
    required this.atCap,
    required this.seconds,
    required this.resetOn,
    required this.phoneEligible,
    required this.phoneChosen,
    required this.onUpgrade,
    required this.onTranscribeOnPhone,
  });

  final bool atCap;
  final int seconds;
  final DateTime resetOn;
  final bool phoneEligible;
  final bool phoneChosen;
  final VoidCallback onUpgrade;
  final VoidCallback onTranscribeOnPhone;

  @override
  Widget build(BuildContext context) {
    if (seconds <= 0) return const SizedBox.shrink();
    final l10n = context.l10n;
    final duration = OmiDuration.compact(seconds, l10n);
    final body = l10n.processingStored;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
      child: Container(
        key: const Key('held_audio_card'),
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.border, width: 0.5),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 1),
                  child: ExcludeSemantics(child: Icon(Icons.schedule, size: 18, color: OmiColors.warning)),
                ),
                const SizedBox(width: OmiSpacing.xs),
                Expanded(
                  child: Text(
                    atCap ? l10n.processingPaused : l10n.heldAudioWaiting(duration),
                    style: OmiType.headline,
                  ),
                ),
              ],
            ),
            const SizedBox(height: OmiSpacing.xxs),
            if (atCap) Text(l10n.heldAudioWaiting(duration), style: OmiType.subhead),
            Text(body, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.35)),
            const SizedBox(height: OmiSpacing.sm),
            OmiButton(
              key: const Key('held_audio_upgrade'),
              label: l10n.upgrade,
              size: OmiButtonSize.compact,
              expand: true,
              onPressed: onUpgrade,
            ),
            if (phoneEligible && !phoneChosen) ...[
              const SizedBox(height: OmiSpacing.xs),
              OmiButton.secondary(
                key: const Key('held_audio_on_phone'),
                label: l10n.onDeviceTranscribeOnPhone,
                size: OmiButtonSize.compact,
                expand: true,
                onPressed: onTranscribeOnPhone,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class HeldAudioRecordingRow extends StatelessWidget {
  const HeldAudioRecordingRow({super.key, required this.recording, this.recovering = false});

  final bool recovering;

  final HeldAudioRecording recording;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final started = DateTime.fromMillisecondsSinceEpoch(recording.startedAt * 1000);
    final duration = OmiDuration.compact(recording.seconds, l10n);
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
      child: Container(
        key: Key('held_audio_row_${recording.id}'),
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.border, width: 0.5),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.heldAudioRecordingTitle(dates.timestamp(started)), style: OmiType.body),
            const SizedBox(height: 2),
            Text(
              recovering ? l10n.processingProgress : '$duration · ${l10n.processingDeferred}',
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
            ),
          ],
        ),
      ),
    );
  }
}

class HeldAudioHomeSection extends StatelessWidget {
  const HeldAudioHomeSection({
    super.key,
    this.controller,
    this.summary,
    this.backlog,
    this.onProcess,
    this.gate,
    this.onUpgrade,
    this.onPhone,
  });

  final OnDeviceTranscriptionController? controller;
  final HeldAudioSummary? summary;
  final ProcessingBacklog? backlog;
  final Future<bool> Function()? onProcess;
  final bool? gate;
  final VoidCallback? onUpgrade;
  final VoidCallback? onPhone;

  @override
  Widget build(BuildContext context) {
    final resolved = controller ?? OnDeviceTranscriptionController.instance;
    return ListenableBuilder(
      listenable: resolved,
      builder: (context, _) {
        final processing = backlog ??
            ((summary == null && gate != false)
                ? context.select<UsageProvider?, ProcessingBacklog?>((p) => p?.subscription?.processingBacklog)
                : null);
        final active = gate ?? (processing != null || resolved.isActive);
        final held = summary ??
            (active && backlog == null
                ? context.select<UsageProvider, HeldAudioSummary?>((p) => p.subscription?.heldAudio)
                : null);
        if (!active) return const SizedBox.shrink();
        if (processing != null) {
          if (!processing.isVisible) return const SizedBox.shrink();
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ProcessingBacklogView(
                backlog: processing,
                surface: 'a',
                onUpgrade: onUpgrade ?? () => openHeldAudioPlans(context),
                onProcess: onProcess,
                phoneAction: heldAudioPhoneEligible(resolved) && !resolved.settings.enabled
                    ? OmiButton.tertiary(
                        label: context.l10n.onDeviceTranscribeOnPhone,
                        onPressed: onPhone ?? () => unawaited(chooseHeldAudioOnPhone(context, resolved)),
                      )
                    : null,
              ),
              for (final recording in held?.recordings ?? <HeldAudioRecording>[])
                HeldAudioRecordingRow(recording: recording, recovering: processing.isProcessing),
              if ((held?.count ?? 0) > (held?.recordings.length ?? 0))
                Padding(
                  padding: const EdgeInsets.all(OmiSpacing.md),
                  child: Text(
                    context.l10n.heldAudioAndMore(held!.count - held.recordings.length),
                    style: OmiType.footnote,
                  ),
                ),
            ],
          );
        }
        if (held == null || held.seconds <= 0) return const SizedBox.shrink();
        final phone = heldAudioPhoneEligible(resolved);
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            HeldAudioCardView(
              atCap: held.retainLive,
              seconds: held.seconds,
              resetOn: heldAudioCalendarDate(held.resetAt),
              phoneEligible: phone,
              phoneChosen: resolved.settings.enabled,
              onUpgrade: onUpgrade ?? () => openHeldAudioPlans(context),
              onTranscribeOnPhone: onPhone ?? () => unawaited(chooseHeldAudioOnPhone(context, resolved)),
            ),
            for (final recording in held.recordings) HeldAudioRecordingRow(recording: recording, recovering: false),
            if (held.count > held.recordings.length)
              Padding(
                padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
                child: Text(
                  context.l10n.heldAudioAndMore(held.count - held.recordings.length),
                  key: const Key('held_audio_more'),
                  style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                ),
              ),
          ],
        );
      },
    );
  }
}

class HeldAudioLiveBannerView extends StatelessWidget {
  const HeldAudioLiveBannerView({
    super.key,
    required this.phoneEligible,
    required this.phoneChosen,
    required this.onUpgrade,
    required this.onTranscribeOnPhone,
  });

  final bool phoneEligible;
  final bool phoneChosen;
  final VoidCallback onUpgrade;
  final VoidCallback onTranscribeOnPhone;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, 0),
      child: Container(
        key: const Key('held_audio_live_banner'),
        padding: const EdgeInsets.all(OmiSpacing.md),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.warning.withValues(alpha: 0.45), width: 0.5),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(l10n.processingPaused, style: OmiType.headline),
            const SizedBox(height: OmiSpacing.xxs),
            Text(l10n.processingStored, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.35)),
            const SizedBox(height: OmiSpacing.sm),
            OmiButton(
              key: const Key('held_audio_live_upgrade'),
              label: l10n.upgrade,
              size: OmiButtonSize.compact,
              expand: true,
              onPressed: onUpgrade,
            ),
            if (phoneEligible && !phoneChosen) ...[
              const SizedBox(height: OmiSpacing.xs),
              OmiButton.secondary(
                key: const Key('held_audio_live_on_phone'),
                label: l10n.onDeviceTranscribeOnPhone,
                size: OmiButtonSize.compact,
                expand: true,
                onPressed: onTranscribeOnPhone,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class HeldAudioLivePlaceholder extends StatelessWidget {
  const HeldAudioLivePlaceholder({super.key, required this.recordedSeconds, required this.resetOn});

  final int recordedSeconds;
  final DateTime resetOn;

  @override
  Widget build(BuildContext context) {
    if (recordedSeconds <= 0) return const SizedBox.shrink();
    final l10n = context.l10n;
    final minutes = (recordedSeconds / 60).ceil();
    return Padding(
      key: const Key('held_audio_live_placeholder'),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.md, OmiSpacing.xl, 0),
      child: Column(
        children: [
          Text(
            l10n.heldAudioRecordedSinceLimit(minutes),
            textAlign: TextAlign.center,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
          ),
          const SizedBox(height: 2),
          Text(
            l10n.processingDeferred,
            textAlign: TextAlign.center,
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
          ),
        ],
      ),
    );
  }
}

class HeldAudioLiveBanner extends StatelessWidget {
  const HeldAudioLiveBanner({
    super.key,
    this.controller,
    this.summary,
    this.backlog,
    this.onProcess,
    this.gate,
    this.recordedSeconds,
    this.onUpgrade,
    this.onPhone,
  });

  final OnDeviceTranscriptionController? controller;
  final HeldAudioSummary? summary;
  final ProcessingBacklog? backlog;
  final Future<bool> Function()? onProcess;
  final bool? gate;
  final int? recordedSeconds;
  final VoidCallback? onUpgrade;
  final VoidCallback? onPhone;

  @override
  Widget build(BuildContext context) {
    final resolved = controller ?? OnDeviceTranscriptionController.instance;
    return ListenableBuilder(
      listenable: resolved,
      builder: (context, _) {
        final processing = backlog ??
            ((summary == null && gate != false)
                ? context.select<UsageProvider?, ProcessingBacklog?>((p) => p?.subscription?.processingBacklog)
                : null);
        final active = gate ?? (processing != null || resolved.isActive);
        if (!active) return const SizedBox.shrink();
        if (processing != null) {
          return ProcessingBacklogView(
            backlog: processing,
            surface: 'b',
            onUpgrade: onUpgrade ?? () => openHeldAudioPlans(context),
            onProcess: onProcess,
            phoneAction: heldAudioPhoneEligible(resolved) && !resolved.settings.enabled
                ? OmiButton.tertiary(
                    label: context.l10n.onDeviceTranscribeOnPhone,
                    onPressed: onPhone ?? () => unawaited(chooseHeldAudioOnPhone(context, resolved)),
                  )
                : null,
          );
        }
        // Receipts cover the period before the next subscription refresh.
        final live = recordedSeconds == null ? context.watch<CaptureProvider>().liveHeldAudio : null;
        final held = summary ?? context.select<UsageProvider, HeldAudioSummary?>((p) => p.subscription?.heldAudio);
        final paused = live?.paused ?? held?.retainLive ?? false;
        final resetAt = live != null && live.resetAt > 0 ? live.resetAt : held?.resetAt ?? 0;
        if (!paused) return const SizedBox.shrink();
        final chosen = resolved.settings.enabled;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            HeldAudioLiveBannerView(
              phoneEligible: heldAudioPhoneEligible(resolved),
              phoneChosen: chosen,
              onUpgrade: onUpgrade ?? () => openHeldAudioPlans(context),
              onTranscribeOnPhone: onPhone ?? () => unawaited(chooseHeldAudioOnPhone(context, resolved)),
            ),
            if (!chosen && resetAt > 0)
              HeldAudioLivePlaceholder(
                recordedSeconds: recordedSeconds ?? live!.heldSeconds,
                resetOn: heldAudioCalendarDate(resetAt),
              ),
          ],
        );
      },
    );
  }
}

class HeldAudioUsageSection extends StatelessWidget {
  const HeldAudioUsageSection({
    super.key,
    this.controller,
    this.summary,
    this.backlog,
    this.onProcess,
    this.gate,
    this.showSaveToggle = false,
    this.paid,
    this.onUpgrade,
    this.onSaveLiveHours,
  });

  final OnDeviceTranscriptionController? controller;
  final HeldAudioSummary? summary;
  final ProcessingBacklog? backlog;
  final Future<bool> Function()? onProcess;
  final bool? gate;
  final bool showSaveToggle;
  final bool? paid;
  final VoidCallback? onUpgrade;
  final ValueChanged<bool>? onSaveLiveHours;

  @override
  Widget build(BuildContext context) {
    final resolved = controller ?? OnDeviceTranscriptionController.instance;
    return ListenableBuilder(
      listenable: resolved,
      builder: (context, _) {
        final processing = backlog ??
            ((summary == null && gate != false)
                ? context.select<UsageProvider?, ProcessingBacklog?>((p) => p?.subscription?.processingBacklog)
                : null);
        final active = gate ?? (processing != null || resolved.isActive);
        final held = summary ??
            (active && backlog == null
                ? context.select<UsageProvider, HeldAudioSummary?>((p) => p.subscription?.heldAudio)
                : null);
        if (!active ||
            (processing == null && (held == null || held.seconds <= 0)) ||
            (processing != null && !processing.isVisible)) {
          return const SizedBox.shrink();
        }
        final l10n = context.l10n;
        final duration = OmiDuration.compact(held?.seconds ?? 0, l10n);
        final paidPlan = paid ??
            (showSaveToggle ||
                context.select<UsageProvider, bool>((p) => p.subscription?.subscription.plan.isPaid ?? false));
        final showPhoneToggle = paidPlan && heldAudioPhoneEligible(resolved);
        return Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (processing != null)
                ProcessingBacklogView(
                  backlog: processing,
                  surface: 'c',
                  onUpgrade: onUpgrade ?? () => openHeldAudioPlans(context),
                  onProcess: onProcess,
                ),
              if (processing != null && showPhoneToggle) const SizedBox(height: OmiSpacing.sm),
              if (processing == null || showPhoneToggle)
                OmiSettingsGroup(
                  children: [
                    if (processing == null)
                      OmiSettingsRow(
                        key: const Key('held_audio_usage_waiting'),
                        title: l10n.heldAudioWaiting(duration),
                        subtitle: l10n.processingDeferred,
                      ),
                    if (showPhoneToggle)
                      OmiSettingsRow.toggle(
                        key: const Key('held_audio_usage_toggle'),
                        title: l10n.onDeviceSaveLiveHours,
                        subtitle: l10n.onDeviceSaveLiveHoursSubtitle,
                        value: resolved.settings.saveLiveHours,
                        onChanged: onSaveLiveHours ??
                            (value) =>
                                unawaited(resolved.updateSettings(resolved.settings.copyWith(saveLiveHours: value))),
                      ),
                    if (processing == null)
                      OmiSettingsRow(
                        key: const Key('held_audio_usage_plans'),
                        title: l10n.paywallComparePlans,
                        onTap: onUpgrade ?? () => openHeldAudioPlans(context),
                        showChevron: true,
                      ),
                  ],
                ),
            ],
          ),
        );
      },
    );
  }
}
