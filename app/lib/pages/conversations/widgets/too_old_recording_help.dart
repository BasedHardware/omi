// A recording outside automatic sync can't be transcribed, so the row offers the two things the
// user can still do: keep the audio (system share sheet) or delete it. It never retries or uploads.
import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class TooOldRecordingHelp extends StatelessWidget {
  const TooOldRecordingHelp({super.key, required this.onDownload, required this.onDelete});

  final Future<void> Function() onDownload;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(context.l10n.syncTooOldExplanation, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              OmiButton.secondary(
                key: const Key('too_old_download'),
                label: context.l10n.downloadAudio,
                size: OmiButtonSize.compact,
                onPressed: onDownload,
              ),
              OmiButton.tertiary(
                key: const Key('too_old_delete'),
                label: context.l10n.delete,
                size: OmiButtonSize.compact,
                onPressed: onDelete,
              ),
            ],
          ),
        ],
      );
}
