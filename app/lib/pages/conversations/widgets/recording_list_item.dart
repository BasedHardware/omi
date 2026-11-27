import 'package:flutter/material.dart';

import 'package:clock/clock.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/home/home_model.dart';
import 'package:omi/pages/conversations/home/home_row_shell.dart';
import 'package:omi/pages/conversations/home/home_swipe_delete.dart';
import 'package:omi/pages/on_device/on_device_queue_banner.dart';
import 'package:omi/pages/conversations/recording_detail/recording_detail_sheet.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A recording held on this phone for the reader, in the Home row shape every other row uses: its
/// time and length, its state, and play (or Retry when sending failed and sending again can help). Tapping opens the recording
/// sheet (transcribe, share, delete). Swiping deletes it after a confirm; the file may be the only
/// copy, so there is no Undo, and a recording the server is still working on cannot be swiped.
class RecordingListItem extends StatefulWidget {
  final LocalRecording recording;

  const RecordingListItem({super.key, required this.recording});

  @override
  State<RecordingListItem> createState() => _RecordingListItemState();
}

class _RecordingListItemState extends State<RecordingListItem> {
  bool _retrying = false;

  LocalRecording get recording => widget.recording;

  (Color?, String) _status(BuildContext context) {
    final l = context.l10n;
    switch (recording.state) {
      case LocalRecordingState.uploading:
        return (null, l.syncStatusBackingUp);
      case LocalRecordingState.processing:
        // Past its deadline the row stops claiming all is well.
        if (savedProcessingOverdue(recording, clock.now())) return (OmiColors.warning, l.homeTakingLonger);
        return (null, l.syncStatusUploaded);
      case LocalRecordingState.failed:
        return (OmiColors.danger, l.failedStatus);
      case LocalRecordingState.pending:
        return (null, l.privateAndSecureOnDevice);
    }
  }

  Future<void> _retry(LocalRecordingsProvider provider) async {
    if (_retrying) return;
    setState(() => _retrying = true);
    final outcome = await provider.upload(recording);
    if (!mounted) return;
    setState(() => _retrying = false);
    switch (outcome) {
      case LocalUploadOutcome.fairUseLimited:
        OmiFeedback.error(context, context.l10n.fairUseBudgetExhausted);
      case LocalUploadOutcome.backendBusy:
        AppReviewService().recordBadExperience(AppReviewBadExperience.captureFailure);
        OmiFeedback.error(context, context.l10n.msgUploadFileFailed);
      case LocalUploadOutcome.failed:
        AppReviewService().recordBadExperience(AppReviewBadExperience.captureFailure);
        OmiFeedback.error(context, context.l10n.anErrorOccurredTryAgain);
      case LocalUploadOutcome.busy || LocalUploadOutcome.started:
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<LocalRecordingsProvider>(
      builder: (context, provider, _) {
        final l10n = context.l10n;
        final (statusColor, statusLabel) = _status(context);
        final isPlaying = provider.isPlaying(recording);
        final title = '${OmiDateFormat.of(context).time(recording.startedAt)} · '
            '${OmiDuration.compact(recording.seconds, l10n)}';
        final failed = recording.state == LocalRecordingState.failed;
        // A terminal refusal keeps its failure mark but offers play, not a Retry bound to fail.
        final canRetry = failed && recording.retryCanHelp;
        final busy =
            recording.state == LocalRecordingState.uploading || recording.state == LocalRecordingState.processing;
        final status = Text(
          statusLabel,
          style: HomeRowShell.subtitleStyle.copyWith(color: statusColor),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        );
        return HomeSwipeDelete(
          key: ValueKey('rec_swipe_${recording.id}'),
          enabled: !recording.isBusy,
          // The file on this phone may be the only copy of the audio: deleting it cannot be
          // undone, so the swipe always confirms (tokens audit #1, docs/ux-contract.md §4).
          confirm: (_) => showOmiConfirm(
            context,
            title: l10n.deleteRecording,
            message: l10n.thisCannotBeUndone,
            confirmLabel: l10n.delete,
            destructive: true,
          ),
          onDeleted: () => provider.delete(recording),
          child: HomeRowShell(
            key: ValueKey('rec_${recording.id}'),
            tile: HomeRowTile(
              child: busy
                  // The same spinner and failure mark a conversation's tile shows.
                  ? const OmiSpinner(size: OmiSpinnerSize.small)
                  : failed
                      ? Icon(Icons.error_outline_rounded, size: 20, color: OmiColors.danger)
                      : Icon(Icons.graphic_eq, color: OmiColors.textTertiary, size: 20),
            ),
            title: title,
            subtitle: statusLabel,
            subtitleWidget: _OnDeviceStatus(recording: recording, fallback: status),
            onTap: () => showRecordingDetailSheet(context, recording),
            actionTrailing: true,
            trailing: canRetry
                ? HomeRowAction(
                    key: ValueKey('rec_retry_${recording.id}'),
                    label: l10n.retry,
                    busy: _retrying,
                    onPressed: () => _retry(provider),
                  )
                : OmiIconButton.filled(
                    key: ValueKey('rec_play_${recording.id}'),
                    icon: Icon(isPlaying ? Icons.pause : Icons.play_arrow, size: 20),
                    label: isPlaying ? l10n.pause : l10n.play,
                    diameter: kOmiMinTapTarget,
                    fillColor: OmiColors.surface2,
                    onPressed: () => provider.togglePlayback(recording),
                  ),
          ),
        );
      },
    );
  }
}

/// A pending recording's on-device status (setup, transcribing, waiting to transcribe) while the
/// on-device flag is on; otherwise [fallback], the row's usual status line. A charger wait is not
/// shown here: Offline Sync names it.
class _OnDeviceStatus extends StatelessWidget {
  const _OnDeviceStatus({required this.recording, required this.fallback});

  final LocalRecording recording;
  final Widget fallback;

  @override
  Widget build(BuildContext context) {
    if (recording.state != LocalRecordingState.pending) return fallback;
    final controller = OnDeviceTranscriptionController.instance;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        if (!controller.isActive) return fallback;
        final atCap = context.select<UsageProvider, bool>((p) => p.isOutOfCredits);
        return onDeviceRecordingChip(context, controller, atCap: atCap) ?? fallback;
      },
    );
  }
}
