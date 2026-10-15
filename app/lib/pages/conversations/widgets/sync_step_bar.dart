import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/sync/offline_sync_amounts.dart';

/// One bar segment per sync step: Omi → phone, upload, transcribe.
///
/// Steps before [step] are full and steps after it are empty, so the bar only
/// ever fills left to right. Before, each step restarted one bar at 0%, and a
/// sync read as three separate jobs. A null [fraction] draws the active step
/// indeterminate: it has started but has no measurable amount yet.
class SyncStepBar extends StatelessWidget {
  const SyncStepBar({super.key, required this.step, required this.fraction});

  final SyncStep step;
  final double? fraction;

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final track = OmiColors.active == OmiPalette.light ? OmiColors.surface3 : Colors.grey.shade800;
    final labels = [l.syncStepLabelDownload, l.syncStepLabelUpload, l.syncStepLabelTranscribe];

    Widget segment(SyncStep s) {
      final double? value = s.index < step.index
          ? 1.0
          : s.index > step.index
              ? 0.0
              : fraction?.clamp(0.0, 1.0);
      return Expanded(
        child: ClipRRect(
          borderRadius: BorderRadius.circular(OmiRadius.sm),
          child: LinearProgressIndicator(
            value: value,
            minHeight: 6,
            backgroundColor: track,
            color: OmiColors.accent,
          ),
        ),
      );
    }

    Widget label(SyncStep s, TextAlign align) {
      return Expanded(
        child: Text(
          labels[s.index],
          textAlign: align,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: OmiType.footnote.copyWith(
            color: s == step ? OmiColors.textPrimary : OmiColors.textTertiary,
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            segment(SyncStep.download),
            const SizedBox(width: 4),
            segment(SyncStep.upload),
            const SizedBox(width: 4),
            segment(SyncStep.transcribe),
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            label(SyncStep.download, TextAlign.start),
            label(SyncStep.upload, TextAlign.center),
            label(SyncStep.transcribe, TextAlign.end),
          ],
        ),
      ],
    );
  }
}
