import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/recording_detail/recording_detail_sheet.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A row in the conversations list for a batch/offline-mode recording captured
/// locally. Unlike a conversation it has no title/icon yet — it shows the
/// recording's time + duration, its state, and an inline play/pause button that
/// decodes and plays the local audio on device. Tapping opens a floating
/// playback sheet (transcribe, share, delete).
class RecordingListItem extends StatelessWidget {
  final LocalRecording recording;

  const RecordingListItem({super.key, required this.recording});

  (Color, String) _status(BuildContext context) {
    final l = context.l10n;
    switch (recording.state) {
      case LocalRecordingState.uploading:
        return (Colors.grey.shade300, l.syncStatusBackingUp);
      case LocalRecordingState.processing:
        return (Colors.grey.shade400, l.syncStatusUploaded);
      case LocalRecordingState.failed:
        return (OmiColors.danger, l.failedStatus);
      case LocalRecordingState.pending:
        return (Colors.grey.shade500, l.privateAndSecureOnDevice);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<LocalRecordingsProvider>(
      builder: (context, provider, _) {
        final (statusColor, statusLabel) = _status(context);
        final isPlaying = provider.isPlaying(recording);
        final timeStr = OmiDateFormat.of(context).time(recording.startedAt);

        return Padding(
          padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
          child: Container(
            width: double.maxFinite,
            decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
            child: ClipRRect(
              borderRadius: OmiRadius.xlAll,
              child: Dismissible(
                key: ValueKey('rec_${recording.id}'),
                direction: recording.isBusy ? DismissDirection.none : DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  color: OmiColors.danger,
                  padding: const EdgeInsets.only(right: 20),
                  child: const Icon(Icons.delete, color: Colors.white),
                ),
                // The file on this phone may be the only copy of the audio: deleting it cannot be
                // undone, so the swipe always confirms (tokens audit #1, docs/ux-contract.md §4).
                confirmDismiss: (_) => showOmiConfirm(
                  context,
                  title: context.l10n.deleteRecording,
                  message: context.l10n.thisCannotBeUndone,
                  confirmLabel: context.l10n.delete,
                  destructive: true,
                ),
                onDismissed: (_) => provider.delete(recording),
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => showRecordingDetailSheet(context, recording),
                  child: Padding(
                    padding: const EdgeInsetsDirectional.symmetric(horizontal: 16, vertical: 18),
                    child: Row(
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                          child: Icon(Icons.graphic_eq, color: Colors.grey.shade400, size: 20),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '$timeStr · ${OmiDuration.compact(recording.seconds, context.l10n)}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: OmiType.callout.copyWith(fontWeight: FontWeight.w600),
                              ),
                              const SizedBox(height: 3),
                              Text(
                                statusLabel,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(color: statusColor, fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 10),
                        OmiIconButton.filled(
                          key: ValueKey('rec_play_${recording.id}'),
                          icon: Icon(isPlaying ? Icons.pause : Icons.play_arrow, size: 24),
                          label: isPlaying ? context.l10n.pause : context.l10n.play,
                          diameter: kOmiMinTapTarget,
                          fillColor: OmiColors.surface2,
                          onPressed: () => provider.togglePlayback(recording),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
