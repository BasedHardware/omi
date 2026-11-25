import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/widgets/plans/contextual_plans.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Same eligibility as the on-device overflow offer: this phone can run the engine.
bool heldAudioPhoneEligible(OnDeviceTranscriptionController controller) {
  if (!controller.isActive || !controller.model.engineResolved || controller.model.detectionFailed) return false;
  return controller.model.status.isSupported;
}

void openHeldAudioPlans(BuildContext context) {
  unawaited(openContextualPlans(context, source: 'held_audio', trigger: 'usage_budget'));
}

/// The current Basic limit is useful for the Upgrade action on a confirmed hold.
/// A recording stays held until its own admission changes, even when the plan has minutes again.
int? heldRecordingUpgradeLimitMinutes(ServerConversation conversation, UsageProvider? usage) {
  if (!conversation.isTranscriptionAllowanceHeld || usage == null || !usage.showSubscriptionUI) return null;
  final subscription = usage.subscription;
  if (subscription == null || subscription.subscription.plan != PlanType.basic) return null;
  final limitMinutes = (subscription.transcriptionSecondsLimit / 60).round();
  final allowance = subscription.transcriptionAllowance;
  if (limitMinutes <= 0 || allowance == null || allowance.isManaged || allowance.reason != 'plan_allowance_exhausted') {
    return null;
  }
  return limitMinutes;
}

/// Recordings still waiting for a plan or an allowance, as locked rows. A running release shows none.
List<HeldAudioRecording> lockedHeldRecordings(HeldAudioSummary? held, ProcessingBacklog? backlog) {
  if (held == null || held.seconds <= 0 || backlog?.isProcessing == true) return const [];
  return held.recordings;
}

class HeldRecordingLockedRow extends StatelessWidget {
  const HeldRecordingLockedRow({super.key, required this.recording, this.more = 0, this.onPressed});

  final HeldAudioRecording recording;

  /// Waiting recordings the server did not list; shown under the last row.
  final int more;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final started = DateTime.fromMillisecondsSinceEpoch(recording.startedAt * 1000);
    void unlock() {
      PlatformManager.instance.analytics
          .upgradeTapped(plan: 'unknown', billingInterval: 'unknown', source: 'held_audio');
      (onPressed ?? () => openHeldAudioPlans(context))();
    }

    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Material(
            color: OmiColors.surface1,
            borderRadius: OmiRadius.lgAll,
            child: InkWell(
              key: Key('held_recording_locked_${recording.id}'),
              borderRadius: OmiRadius.lgAll,
              onTap: unlock,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
                child: Row(
                  children: [
                    Icon(Icons.lock_outline, size: 20, color: OmiColors.warning),
                    const SizedBox(width: OmiSpacing.sm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(l10n.heldAudioRecordingTitle(OmiDateFormat.of(context).timestamp(started)),
                              style: OmiType.body),
                          const SizedBox(height: 2),
                          Text('${OmiDuration.compact(recording.seconds, l10n)} · ${l10n.saved}',
                              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                        ],
                      ),
                    ),
                    const SizedBox(width: OmiSpacing.sm),
                    OmiButton(
                      key: Key('held_recording_unlock_${recording.id}'),
                      label: l10n.unlock,
                      size: OmiButtonSize.compact,
                      onPressed: unlock,
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (more > 0)
            Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xs, left: OmiSpacing.xxs),
              child: Text(l10n.heldAudioAndMore(more),
                  key: const Key('held_audio_more'), style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
            ),
        ],
      ),
    );
  }
}

/// The one held-audio control left on Plan & Usage: a paid owner on a phone that can run the engine.
class SaveLiveHoursRow extends StatelessWidget {
  const SaveLiveHoursRow({super.key, this.controller, this.paid, this.onChanged});

  final OnDeviceTranscriptionController? controller;
  final bool? paid;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    final resolved = controller ?? OnDeviceTranscriptionController.instance;
    return ListenableBuilder(
      listenable: resolved,
      builder: (context, _) {
        final paidPlan =
            paid ?? context.select<UsageProvider, bool>((p) => p.subscription?.subscription.plan.isPaid ?? false);
        if (!paidPlan || !heldAudioPhoneEligible(resolved)) return const SizedBox.shrink();
        final l10n = context.l10n;
        return Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.sm),
          child: OmiSettingsGroup(
            children: [
              OmiSettingsRow.toggle(
                key: const Key('held_audio_usage_toggle'),
                title: l10n.onDeviceSaveLiveHours,
                subtitle: l10n.onDeviceSaveLiveHoursSubtitle,
                value: resolved.settings.saveLiveHours,
                onChanged: onChanged ??
                    (value) => unawaited(resolved.updateSettings(resolved.settings.copyWith(saveLiveHours: value))),
              ),
            ],
          ),
        );
      },
    );
  }
}
