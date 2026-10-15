import 'package:flutter/material.dart';

import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What Home's recording pill opens when there is more to say than "Listening": why something
/// needs a look, the capture's own controls (the live capture card: Pause/Resume, Transcribe
/// Later's New recording and Stop, retrying transcription), the live transcript, and Stop.
class HomeCaptureSheet extends StatelessWidget {
  const HomeCaptureSheet({
    super.key,
    this.explanation,
    this.onOpenTranscript,
    this.onStop,
    this.onRecordWithPhone,
    this.showCard = true,
  });

  final String? explanation;
  final VoidCallback? onOpenTranscript;
  final VoidCallback? onStop;

  /// A pendant that dropped: start a phone recording instead.
  final VoidCallback? onRecordWithPhone;

  /// False when the capture is gone (a pendant that dropped): only the explanation is left to show.
  final bool showCard;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, 0, OmiSpacing.lg, OmiSpacing.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (explanation != null) ...[
            Text(
              explanation!,
              key: const ValueKey('home_capture_sheet_explanation'),
              style: OmiType.body.copyWith(color: OmiColors.textSecondary),
            ),
            const SizedBox(height: OmiSpacing.md),
          ],
          if (showCard) const ConversationCaptureWidget(),
          if (onOpenTranscript != null) ...[
            const SizedBox(height: OmiSpacing.md),
            OmiButton.secondary(
              key: const ValueKey('home_capture_sheet_transcript'),
              label: l10n.liveTranscript,
              onPressed: onOpenTranscript,
              expand: true,
            ),
          ],
          if (onRecordWithPhone != null)
            OmiButton.secondary(
              key: const ValueKey('home_capture_sheet_record_phone'),
              label: l10n.recordWithPhoneInstead,
              icon: Icons.mic_rounded,
              onPressed: onRecordWithPhone,
              expand: true,
            ),
          if (onStop != null) ...[
            const SizedBox(height: OmiSpacing.sm),
            OmiButton.secondary(
              key: const ValueKey('home_capture_sheet_stop'),
              label: l10n.stopRecording,
              icon: Icons.stop_rounded,
              onPressed: onStop,
              expand: true,
            ),
          ],
        ],
      ),
    );
  }
}
