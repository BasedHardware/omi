import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/intercom.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Which half of [MobileFeedbackReason] a feedback sheet offers: one population
/// for summary usefulness, one for recording/transcription quality.
enum FeedbackReasonPopulation { summary, recording }

List<MobileFeedbackReason> feedbackReasonsFor(FeedbackReasonPopulation population) => switch (population) {
      FeedbackReasonPopulation.summary => const [
          MobileFeedbackReason.summaryInaccurate,
          MobileFeedbackReason.summaryIncomplete,
          MobileFeedbackReason.summaryIrrelevant,
          MobileFeedbackReason.summaryWrongContext,
          MobileFeedbackReason.summaryOther,
        ],
      FeedbackReasonPopulation.recording => const [
          MobileFeedbackReason.recordingMissingAudio,
          MobileFeedbackReason.recordingPoorTranscription,
          MobileFeedbackReason.recordingWrongSpeaker,
          MobileFeedbackReason.recordingDelayedOrStuck,
          MobileFeedbackReason.recordingFragmentedOrDuplicated,
          MobileFeedbackReason.recordingOther,
        ],
    };

String feedbackReasonLabel(AppLocalizations l10n, MobileFeedbackReason reason) => switch (reason) {
      MobileFeedbackReason.summaryInaccurate => l10n.feedbackReasonSummaryInaccurate,
      MobileFeedbackReason.summaryIncomplete => l10n.feedbackReasonSummaryIncomplete,
      MobileFeedbackReason.summaryIrrelevant => l10n.feedbackReasonSummaryIrrelevant,
      MobileFeedbackReason.summaryWrongContext => l10n.feedbackReasonSummaryWrongContext,
      MobileFeedbackReason.summaryOther => l10n.feedbackReasonSummaryOther,
      MobileFeedbackReason.recordingMissingAudio => l10n.feedbackReasonRecordingMissingAudio,
      MobileFeedbackReason.recordingPoorTranscription => l10n.feedbackReasonRecordingPoorTranscription,
      MobileFeedbackReason.recordingWrongSpeaker => l10n.feedbackReasonRecordingWrongSpeaker,
      MobileFeedbackReason.recordingDelayedOrStuck => l10n.feedbackReasonRecordingDelayedOrStuck,
      MobileFeedbackReason.recordingFragmentedOrDuplicated => l10n.feedbackReasonRecordingFragmentedOrDuplicated,
      MobileFeedbackReason.recordingOther => l10n.feedbackReasonRecordingOther,
    };

/// The quick feedback sheet behind a prompt's "Give feedback" button.
///
/// Picking a reason chip submits `-1` with that [MobileFeedbackReason] through
/// [onSubmit] and closes; the "All good" chip submits `+1` with no reason.
/// Free text is deliberately not offered — the `mobile_feedback.v1` schema has
/// no text field — instead a secondary row opens the Intercom messenger when it
/// is available. Dismissing the sheet without a choice submits nothing.
Future<void> showFeedbackReasonSheet(
  BuildContext context, {
  required String title,
  required FeedbackReasonPopulation population,
  required void Function(int value, MobileFeedbackReason? reason) onSubmit,
}) {
  return showOmiSheet<void>(
    context: context,
    title: title,
    builder: (context) => _FeedbackReasonSheet(population: population, onSubmit: onSubmit),
  );
}

class _FeedbackReasonSheet extends StatelessWidget {
  final FeedbackReasonPopulation population;
  final void Function(int value, MobileFeedbackReason? reason) onSubmit;

  const _FeedbackReasonSheet({required this.population, required this.onSubmit});

  void _choose(BuildContext context, int value, MobileFeedbackReason? reason) {
    OmiHaptics.selection();
    Navigator.pop(context);
    onSubmit(value, reason);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final intercomEnabled = IntercomManager.instance.isIntercomEnabled;
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: OmiSpacing.xs,
              runSpacing: OmiSpacing.xs,
              children: [
                for (final reason in feedbackReasonsFor(population))
                  ChoiceChip(
                    key: ValueKey('feedback_reason_${reason.name}'),
                    label: Text(feedbackReasonLabel(l10n, reason)),
                    selected: false,
                    showCheckmark: false,
                    materialTapTargetSize: MaterialTapTargetSize.padded,
                    backgroundColor: OmiColors.surface2,
                    selectedColor: OmiColors.accent,
                    side: BorderSide.none,
                    shape: const StadiumBorder(),
                    labelStyle: OmiType.subhead.copyWith(color: OmiColors.textPrimary),
                    onSelected: (_) => _choose(context, -1, reason),
                  ),
              ],
            ),
            const SizedBox(height: OmiSpacing.xs),
            ChoiceChip(
              key: const ValueKey('feedback_all_good'),
              label: Text(l10n.feedbackAllGood),
              selected: false,
              showCheckmark: false,
              materialTapTargetSize: MaterialTapTargetSize.padded,
              backgroundColor: OmiColors.successSurface,
              selectedColor: OmiColors.success,
              side: BorderSide.none,
              shape: const StadiumBorder(),
              labelStyle: OmiType.subhead.copyWith(color: OmiColors.success, fontWeight: FontWeight.w600),
              onSelected: (_) => _choose(context, 1, null),
            ),
            if (intercomEnabled) ...[
              const SizedBox(height: OmiSpacing.md),
              InkWell(
                key: const ValueKey('feedback_chat_with_us'),
                borderRadius: OmiRadius.mdAll,
                onTap: () => IntercomManager.instance.intercom.displayMessenger(),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
                  child: Row(
                    children: [
                      Icon(Icons.chat_bubble_outline_rounded, size: 18, color: OmiColors.textSecondary),
                      const SizedBox(width: OmiSpacing.xs),
                      Expanded(
                        child: Text(
                          l10n.feedbackChatWithUs,
                          style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: OmiSpacing.md),
          ],
        ),
      ),
    );
  }
}
