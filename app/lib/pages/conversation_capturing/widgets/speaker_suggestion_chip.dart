import 'package:flutter/material.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// "Maya Chen?" on an unlabeled speaker in the live transcript: Omi heard a close-but-not-sure match
/// to a pinned person and asks instead of labeling. Collapsed it is a dashed chip beside the speaker
/// name; tapped it opens the same answers as the suggestion card, scoped to the whole speaker.
class SpeakerSuggestionChip extends StatefulWidget {
  const SpeakerSuggestionChip({super.key, required this.person, required this.onYes, required this.onSomeoneElse});

  final Person person;
  final VoidCallback onYes;
  final VoidCallback onSomeoneElse;

  @override
  State<SpeakerSuggestionChip> createState() => _SpeakerSuggestionChipState();
}

class _SpeakerSuggestionChipState extends State<SpeakerSuggestionChip> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final person = widget.person;
    final motion = OmiMotion.of(context);
    final chip = Semantics(
      button: true,
      expanded: _expanded,
      label: l10n.speakerTagPromptIsThisPerson(person.name),
      excludeSemantics: true,
      child: GestureDetector(
        key: const Key('speaker_suggestion_chip'),
        behavior: HitTestBehavior.opaque,
        onTap: () {
          OmiHaptics.selection();
          setState(() => _expanded = !_expanded);
        },
        // A 26pt chip inside a 44pt target (contract §3).
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 9),
          child: Container(
            height: 26,
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs),
            decoration: BoxDecoration(
              borderRadius: OmiRadius.pillAll,
              border: Border.all(color: _expanded ? OmiColors.textPrimary : OmiColors.textTertiary),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (person.pinned) ...[
                  Icon(Icons.push_pin, size: 11, color: OmiColors.textSecondary),
                  const SizedBox(width: 3),
                ],
                Text(
                  l10n.speakerSuggestionChip(person.name),
                  style: OmiType.footnote.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w500),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        chip,
        AnimatedSize(
          duration: motion.standard,
          curve: OmiMotion.standardCurve,
          child: !_expanded
              ? const SizedBox.shrink()
              : Container(
                  key: const Key('speaker_suggestion_panel'),
                  width: double.infinity,
                  margin: const EdgeInsets.only(bottom: OmiSpacing.xs),
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.sm, OmiSpacing.xs, OmiSpacing.xxs, OmiSpacing.xs),
                  decoration: BoxDecoration(
                    color: OmiColors.surface1,
                    borderRadius: OmiRadius.mdAll,
                    border: Border.all(color: OmiColors.border),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              l10n.speakerTagPromptIsThisPerson(person.name),
                              style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                            ),
                          ),
                          OmiIconButton(
                            icon: const Icon(Icons.close, size: 16),
                            label: l10n.collapseAction,
                            color: OmiColors.textSecondary,
                            onPressed: () => setState(() => _expanded = false),
                          ),
                        ],
                      ),
                      Text(
                        l10n.speakerSuggestionAppliesToSpeaker,
                        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                      ),
                      const SizedBox(height: OmiSpacing.xxs),
                      Wrap(
                        spacing: OmiSpacing.xs,
                        children: [
                          OmiButton(
                            key: const Key('speaker_suggestion_yes'),
                            label: l10n.yes,
                            icon: Icons.check,
                            size: OmiButtonSize.compact,
                            onPressed: widget.onYes,
                          ),
                          OmiButton.secondary(
                            key: const Key('speaker_suggestion_someone_else'),
                            label: l10n.speakerTagPromptSomeoneElse,
                            size: OmiButtonSize.compact,
                            onPressed: widget.onSomeoneElse,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
        ),
      ],
    );
  }
}
