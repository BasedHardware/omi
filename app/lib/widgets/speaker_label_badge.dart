import 'package:flutter/material.dart';

import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// How a transcript label was made, as the server reports it in `speaker_label_source`.
abstract final class SpeakerLabelSource {
  /// The user decided this label.
  static const manual = 'manual';

  /// Omi matched the voice; nobody has confirmed it.
  static const auto = 'auto';

  /// The user's own decision on the same voice earlier in this recording.
  static const carried = 'carried';

  static bool isConfirmed(String? source) => source == manual || source == carried;
}

/// The first line of each automatically named person (not the owner) in [segments]: where the
/// transcript asks "Sounds like Maya" once, instead of on every line that voice speaks.
Set<String> firstAutoLabelSegmentIds(List<TranscriptSegment> segments) {
  final asked = <String>{};
  final ids = <String>{};
  for (final segment in segments) {
    final personId = segment.personId;
    if (segment.isUser || personId == null || segment.speakerLabelSource != SpeakerLabelSource.auto) continue;
    if (asked.add('${segment.speakerId}:$personId')) ids.add(segment.id);
  }
  return ids;
}

/// Beside a speaker's name: a check when the user decided the label, "Likely" when Omi guessed it,
/// nothing for an unnamed speaker.
class SpeakerLabelBadge extends StatelessWidget {
  const SpeakerLabelBadge({super.key, required this.source});

  final String? source;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    if (SpeakerLabelSource.isConfirmed(source)) {
      return Semantics(
        label: l10n.speakerLabelText('confirmed', ''),
        child: ExcludeSemantics(
          child: Icon(
            Icons.check_circle_outline,
            key: const Key('speaker_label_confirmed'),
            size: 14,
            color: OmiColors.success,
          ),
        ),
      );
    }
    if (source != SpeakerLabelSource.auto) return const SizedBox.shrink();
    return Container(
      key: const Key('speaker_label_likely'),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(
        borderRadius: OmiRadius.pillAll,
        border: Border.all(color: OmiColors.textTertiary),
      ),
      child: Text(
        l10n.speakerLabelText('likely', ''),
        style: OmiType.caption.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
      ),
    );
  }
}

/// Under the first line Omi named by voice: two light chips, Yes and "Not Maya", that answer
/// "Sounds like Maya" (the "Likely" badge beside the name asks it; screen readers hear it). Either
/// answer applies to every line from that voice.
class SpeakerLikelyConfirm extends StatelessWidget {
  const SpeakerLikelyConfirm({super.key, required this.name, required this.onYes, required this.onNot});

  final String name;
  final VoidCallback onYes;
  final VoidCallback onNot;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Semantics(
      key: const Key('speaker_likely_confirm'),
      container: true,
      label: l10n.speakerLabelText('soundsLike', name),
      child: Wrap(
        spacing: OmiSpacing.xs,
        children: [
          OmiFilterChip(key: const Key('speaker_likely_yes'), label: l10n.yes, selected: false, onSelected: onYes),
          OmiFilterChip(
            key: const Key('speaker_likely_not'),
            label: l10n.speakerLabelText('notPerson', name),
            selected: false,
            onSelected: onNot,
          ),
        ],
      ),
    );
  }
}
