import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/recording_detail/recording_detail_sheet.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/pages/home/widgets/day_timeline_entry.dart';

/// A Transcribe Later capture on the home day timeline.
///
/// It sits in the same shape as a conversation — time, what it is, how long it
/// ran — because on the day it happened that is what it is. It has no title
/// yet, so the second line carries what the user actually needs to know: that
/// the audio is still on the phone, on its way, or that sending it failed.
class DayTimelineRecording extends StatelessWidget {
  const DayTimelineRecording({super.key, required this.recording});

  final LocalRecording recording;

  static const double _timeColumnWidth = 58;

  (Color, String) _status(BuildContext context) {
    final l10n = context.l10n;
    switch (recording.state) {
      case LocalRecordingState.uploading:
        return (Colors.white.withValues(alpha: 0.55), l10n.syncStatusBackingUp);
      case LocalRecordingState.processing:
        return (Colors.white.withValues(alpha: 0.55), l10n.syncStatusUploaded);
      case LocalRecordingState.failed:
        return (const Color(0xFFFF5C47), l10n.failedStatus);
      case LocalRecordingState.pending:
        return (Colors.white.withValues(alpha: 0.45), l10n.privateAndSecureOnDevice);
    }
  }

  @override
  Widget build(BuildContext context) {
    final (statusColor, statusLabel) = _status(context);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        HapticFeedback.selectionClick();
        showRecordingDetailSheet(context, recording);
      },
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 14, 24, 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: _timeColumnWidth,
              child: Padding(
                padding: const EdgeInsets.only(top: 1, right: 8),
                child: Text(
                  timelineTimeLabel(context, recording.startedAt),
                  maxLines: 1,
                  overflow: TextOverflow.clip,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.45), fontSize: 13),
                ),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          context.l10n.recording,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.95),
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                            height: 1.3,
                            letterSpacing: -0.1,
                          ),
                        ),
                      ),
                      if (recording.seconds > 0) ...[
                        const SizedBox(width: 10),
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(
                            timelineDurationLabel(context, recording.seconds),
                            style: TextStyle(color: Colors.white.withValues(alpha: 0.4), fontSize: 13),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    statusLabel,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: statusColor, fontSize: 14, height: 1.3),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
