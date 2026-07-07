import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/recording_detail/recording_detail_sheet.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// A row in the conversations list for a batch/offline-mode recording captured
/// locally. Unlike a conversation it has no title/icon yet — it shows the
/// recording's time + duration, its state, and an inline play/pause button that
/// decodes and plays the local audio on device. Tapping opens a floating
/// playback sheet (transcribe, share, delete).
class RecordingListItem extends StatelessWidget {
  final LocalRecording recording;

  const RecordingListItem({super.key, required this.recording});

  String _formatDuration(int seconds) {
    final m = seconds ~/ 60;
    final s = seconds % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  (Color, String) _status(BuildContext context) {
    final l = context.l10n;
    switch (recording.state) {
      case LocalRecordingState.uploading:
        return (Colors.grey.shade300, l.syncStatusBackingUp);
      case LocalRecordingState.processing:
        return (Colors.grey.shade400, l.syncStatusUploaded);
      case LocalRecordingState.failed:
        return (Colors.redAccent, l.failedStatus);
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
        final timeStr = dateTimeFormat(
          'h:mm a',
          recording.startedAt,
          locale: Localizations.localeOf(context).languageCode,
        );

        return Padding(
          padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
          child: Container(
            width: double.maxFinite,
            decoration: BoxDecoration(color: const Color(0xFF1F1F25), borderRadius: BorderRadius.circular(24.0)),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(24.0),
              child: Dismissible(
                key: ValueKey('rec_${recording.id}'),
                direction: recording.isBusy ? DismissDirection.none : DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  color: Colors.red,
                  padding: const EdgeInsets.only(right: 20),
                  child: const Icon(Icons.delete, color: Colors.white),
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
                          decoration: BoxDecoration(
                            color: const Color(0xFF35343B),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(Icons.graphic_eq, color: Colors.grey.shade400, size: 20),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '$timeStr · ${_formatDuration(recording.seconds)}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
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
                        GestureDetector(
                          onTap: () => provider.togglePlayback(recording),
                          child: Container(
                            width: 44,
                            height: 44,
                            decoration: const BoxDecoration(color: Color(0xFF35343B), shape: BoxShape.circle),
                            child: Icon(isPlaying ? Icons.pause : Icons.play_arrow, color: Colors.white, size: 24),
                          ),
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
