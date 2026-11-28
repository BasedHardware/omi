// Activity's On this phone section (SCA-5226): recordings kept only on this phone, waiting to be
// transcribed or that could not be sent. Home shows a recording only while it is being sent or the
// server is processing it, so this section is where waiting audio lives, and the bell stays lit
// while any is here.

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/home/home_row_shell.dart';
import 'package:omi/pages/conversations/widgets/recording_list_item.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The recordings On this phone lists: every one not being sent or processed, in the provider's
/// order (newest first, sorted where the ledger is read).
List<LocalRecording> onThisPhoneRecordings(Iterable<LocalRecording> all) => [
      for (final r in all)
        if (!r.isBusy) r,
    ];

/// Whether Transcribe all sends [r]: one waiting (unless on-device transcription owns the waiting
/// ones), or one that failed where sending again can help.
bool sendableFromPhone(LocalRecording r, {required bool onDeviceActive}) => switch (r.state) {
      LocalRecordingState.pending => !onDeviceActive,
      LocalRecordingState.failed => r.retryCanHelp,
      LocalRecordingState.uploading || LocalRecordingState.processing => false,
    };

/// Recordings kept only on this phone, in the same rows Home uses (play, Try Again, swipe to
/// delete with a confirm), under a header that counts them and offers Transcribe all. Nothing when
/// there are none.
class OnThisPhoneSection extends StatefulWidget {
  const OnThisPhoneSection({super.key});

  /// Whether the section draws anything.
  static bool hasContent(LocalRecordingsProvider? recordings) =>
      recordings != null && recordings.recordings.any((r) => !r.isBusy);

  @override
  State<OnThisPhoneSection> createState() => _OnThisPhoneSectionState();
}

class _OnThisPhoneSectionState extends State<OnThisPhoneSection> {
  bool _sending = false;

  Future<void> _transcribeAll(LocalRecordingsProvider provider, List<LocalRecording> recordings) async {
    if (_sending) return;
    setState(() => _sending = true);
    final outcomes = <LocalUploadOutcome>[];
    for (final r in recordings) {
      final outcome = await provider.upload(r);
      outcomes.add(outcome);
      // Out of allowance or the server is full: the rest would only fail the same way.
      if (outcome == LocalUploadOutcome.fairUseLimited || outcome == LocalUploadOutcome.backendBusy) break;
    }
    if (!mounted) return;
    setState(() => _sending = false);
    final l = context.l10n;
    if (outcomes.contains(LocalUploadOutcome.fairUseLimited)) {
      OmiFeedback.error(context, l.fairUseBudgetExhausted);
    } else if (outcomes.contains(LocalUploadOutcome.backendBusy)) {
      AppReviewService().recordBadExperience(AppReviewBadExperience.captureFailure);
      OmiFeedback.error(context, l.msgUploadFileFailed);
    } else if (outcomes.contains(LocalUploadOutcome.failed)) {
      AppReviewService().recordBadExperience(AppReviewBadExperience.captureFailure);
      OmiFeedback.error(context, l.anErrorOccurredTryAgain);
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<LocalRecordingsProvider?>();
    if (provider == null) return const SizedBox.shrink();
    final recordings = onThisPhoneRecordings(provider.recordings);
    if (recordings.isEmpty) return const SizedBox.shrink();
    final l = context.l10n;
    final onDevice = OnDeviceTranscriptionController.instance.isActive;
    final sendable = [
      for (final r in recordings)
        if (sendableFromPhone(r, onDeviceActive: onDevice)) r,
    ];
    final largeText = MediaQuery.textScalerOf(context).scale(1) >= 1.6;
    final header = Semantics(
      header: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l.activityOnThisPhone.toUpperCase(),
            // The same header as Needs attention and Activity's day groups.
            style: OmiType.footnote
                .copyWith(fontWeight: FontWeight.w600, color: OmiColors.textSecondary, letterSpacing: 0.4),
          ),
          Text(
            l.activityOnThisPhoneSummary(recordings.length),
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
          ),
        ],
      ),
    );
    final transcribeAll = sendable.isEmpty
        ? null
        : OmiButton.tertiary(
            key: const Key('activity_transcribe_all'),
            label: l.activityTranscribeAll,
            isLoading: _sending,
            onPressed: _sending ? null : () => _transcribeAll(provider, sendable),
          );
    return Column(
      key: const Key('activity_on_this_phone'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.md, 0, 0),
          child: largeText
              // At the accessibility text sizes the button moves under the header, as Needs
              // attention's Retry all does, so the header keeps whole words.
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [header, if (transcribeAll != null) transcribeAll],
                )
              : Row(children: [Expanded(child: header), if (transcribeAll != null) transcribeAll]),
        ),
        for (final r in recordings)
          RecordingListItem(key: ValueKey('activity_rec_${r.id}'), recording: r, margin: HomeRowShell.listMargin),
      ],
    );
  }
}
