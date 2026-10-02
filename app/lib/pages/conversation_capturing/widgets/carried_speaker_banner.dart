import 'package:flutter/material.dart';

import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/speaker_label_badge.dart';

/// The first line of each person whose label Omi carried into this conversation from the user's
/// own answer earlier in the same recording, in order of appearance.
List<TranscriptSegment> carriedSpeakerSegments(List<TranscriptSegment> segments) {
  final seen = <String>{};
  return [
    for (final segment in segments)
      if (segment.speakerLabelSource == SpeakerLabelSource.carried &&
          segment.personId != null &&
          seen.add('${segment.speakerId}:${segment.personId}'))
        segment,
  ];
}

/// Above a live transcript: "Still Maya. Carried over from your last conversation." with Change,
/// so a label that followed the voice into a new conversation is visible and one tap from wrong.
class CarriedSpeakerBanner extends StatelessWidget {
  const CarriedSpeakerBanner({super.key, required this.name, required this.onChange, required this.onClose});

  final String name;
  final VoidCallback onChange;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Container(
      key: const Key('carried_speaker_banner'),
      margin: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xxs),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.sm, OmiSpacing.xxs, OmiSpacing.xxs, OmiSpacing.xxs),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.border),
      ),
      child: Row(
        children: [
          ExcludeSemantics(child: Icon(Icons.redo, size: 18, color: OmiColors.textSecondary)),
          const SizedBox(width: OmiSpacing.xs),
          Expanded(
            child: Text(
              l10n.speakerLabelText('carried', name),
              style: OmiType.footnote.copyWith(color: OmiColors.textPrimary, height: 1.35),
            ),
          ),
          OmiButton.tertiary(
            key: const Key('carried_speaker_change'),
            label: l10n.speakerLabelText('change', ''),
            size: OmiButtonSize.compact,
            onPressed: onChange,
          ),
          OmiIconButton(
            icon: const Icon(Icons.close, size: 16),
            label: l10n.close,
            color: OmiColors.textSecondary,
            onPressed: onClose,
          ),
        ],
      ),
    );
  }
}
