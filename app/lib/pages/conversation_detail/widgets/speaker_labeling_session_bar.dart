import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The bar over the transcript while the reader labels speakers in one pass: how many lines the
/// pass relabeled, Undo, Select (choose lines to name together) and Done, which updates the summary
/// once. While lines are being chosen it reads "N selected" with Cancel and Name Speaker.
class SpeakerLabelingSessionBar extends StatelessWidget {
  const SpeakerLabelingSessionBar({
    super.key,
    required this.linesRelabeled,
    required this.selectedCount,
    required this.onDone,
    required this.onSelect,
    required this.onCancelSelection,
    required this.onAssign,
    this.onUndo,
  });

  final int linesRelabeled;

  /// Null outside selection mode.
  final int? selectedCount;
  final VoidCallback onDone;
  final VoidCallback onSelect;
  final VoidCallback onCancelSelection;
  final VoidCallback onAssign;

  /// Null when there is nothing to undo.
  final VoidCallback? onUndo;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final selected = selectedCount;
    final title = selected == null ? l10n.speakerLabelLinesLabeled(linesRelabeled) : l10n.selectedCount(selected);
    return Semantics(
      container: true,
      liveRegion: true,
      child: Container(
        key: const Key('speaker_labeling_session_bar'),
        margin: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.xs, OmiSpacing.xxs),
        decoration: BoxDecoration(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.border),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                title,
                key: const Key('speaker_labeling_session_title'),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
              ),
            ),
            if (selected == null) ...[
              OmiIconButton(
                key: const Key('speaker_labeling_undo'),
                icon: const Icon(Icons.undo, size: 20),
                label: l10n.undo,
                color: OmiColors.textSecondary,
                onPressed: onUndo,
              ),
              OmiIconButton(
                key: const Key('speaker_labeling_select'),
                icon: const Icon(Icons.checklist, size: 20),
                label: l10n.selectOption,
                color: OmiColors.textSecondary,
                onPressed: onSelect,
              ),
              const SizedBox(width: OmiSpacing.xxs),
              OmiButton(
                key: const Key('speaker_labeling_done'),
                label: l10n.done,
                size: OmiButtonSize.compact,
                onPressed: onDone,
              ),
            ] else ...[
              OmiButton.tertiary(
                key: const Key('speaker_labeling_cancel_selection'),
                label: l10n.cancel,
                size: OmiButtonSize.compact,
                onPressed: onCancelSelection,
              ),
              const SizedBox(width: OmiSpacing.xxs),
              OmiButton(
                key: const Key('speaker_labeling_assign'),
                label: l10n.nameSpeakerTitle,
                size: OmiButtonSize.compact,
                onPressed: selected == 0 ? null : onAssign,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
