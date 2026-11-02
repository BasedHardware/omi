import 'package:flutter/material.dart';

import 'package:omi/backend/schema/review.dart';
import 'package:omi/pages/review/widgets/recent_change_groups.dart';
import 'package:omi/pages/review/widgets/recent_change_row.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Every place one grouped change landed, each in its own words, with Undo per conversation.
///
/// [group] is re-read on every [listenable] tick so Undo inside the sheet and on the page agree.
class RecentChangeSheetBody extends StatelessWidget {
  const RecentChangeSheetBody({
    super.key,
    required this.listenable,
    required this.group,
    required this.isBusy,
    required this.onToggle,
    this.onOpenConversation,
  });

  final Listenable listenable;
  final RecentChangeGroup? Function() group;
  final bool Function(String changeId) isBusy;
  final void Function(ReviewChange change) onToggle;
  final void Function(String conversationId)? onOpenConversation;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: listenable,
      builder: (context, _) {
        final current = group();
        if (current == null) return const SizedBox.shrink();
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (current.before != null || current.after != null)
              Padding(
                padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
                child: RecentChangeDiff(before: current.before, after: current.after, section: current.section),
              ),
            for (final change in current.changes)
              _Entry(
                change: change,
                busy: isBusy(change.changeId),
                onToggle: () => onToggle(change),
                onOpenConversation: onOpenConversation,
              ),
          ],
        );
      },
    );
  }
}

class _Entry extends StatelessWidget {
  const _Entry({required this.change, required this.busy, required this.onToggle, this.onOpenConversation});

  final ReviewChange change;
  final bool busy;
  final VoidCallback onToggle;
  final void Function(String conversationId)? onOpenConversation;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final occurrences = change.diff?.occurrences ?? const <ReviewChangeOccurrence>[];
    final conversation = recentChangeConversation(change);
    final note = recentChangeNote(change);
    final title = recentChangeSourceTitle(change) ?? l10n.untitledConversation;

    final Widget evidence;
    if (occurrences.isNotEmpty) {
      evidence = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (i, occurrence) in occurrences.indexed)
            Padding(
              padding: EdgeInsets.only(top: i == 0 ? 0 : OmiSpacing.xs),
              child: _OccurrenceText(occurrence: occurrence, dimmed: change.undone),
            ),
        ],
      );
    } else if (change.context != null) {
      // Rows written before the diff existed still carry the bounded speech around the edit.
      evidence = ReviewSpellingContext(context: change.context!);
    } else if (change.snippet != null) {
      evidence = Text(change.snippet!, style: OmiType.callout);
    } else {
      evidence = RecentChangeDiff(
        before: recentChangeBefore(change),
        after: recentChangeAfter(change),
        section: recentChangeSection(change),
        dimmed: change.undone,
      );
    }

    return Container(
      key: ValueKey('recent_change_entry_${change.changeId}'),
      margin: const EdgeInsets.only(bottom: OmiSpacing.sm),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.xs, OmiSpacing.xxs),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.only(right: OmiSpacing.xs),
            child: Text(
              '$title · ${dates.dateTime(recentChangeSourceTime(change))}',
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
            ),
          ),
          const SizedBox(height: OmiSpacing.xs),
          Padding(padding: const EdgeInsets.only(right: OmiSpacing.xs), child: evidence),
          if (change.undone)
            Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xs, right: OmiSpacing.xs),
              child: Text(l10n.reviewChangeUndone, style: OmiType.footnote),
            )
          else if (note != null)
            Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xs, right: OmiSpacing.xs),
              child: Text(note, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
            ),
          Wrap(
            alignment: WrapAlignment.end,
            children: [
              if (conversation != null && onOpenConversation != null)
                OmiButton.tertiary(
                  key: ValueKey('recent_change_open_conversation_${change.changeId}'),
                  label: l10n.reviewChangeViewConversation,
                  size: OmiButtonSize.compact,
                  onPressed: () => onOpenConversation!(conversation.id),
                ),
              OmiButton.tertiary(
                key: ValueKey('review_change_toggle_${change.changeId}'),
                label: change.undone ? l10n.redo : l10n.undo,
                size: OmiButtonSize.compact,
                isLoading: busy,
                onPressed: busy ? null : onToggle,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// The sentence around one edit: old span struck through, new span highlighted.
class _OccurrenceText extends StatelessWidget {
  const _OccurrenceText({required this.occurrence, required this.dimmed});

  final ReviewChangeOccurrence occurrence;
  final bool dimmed;

  @override
  Widget build(BuildContext context) {
    final base = OmiType.callout;
    final before = occurrence.before;
    final after = occurrence.after;
    final contextBefore = occurrence.contextBefore;
    final contextAfter = occurrence.contextAfter;
    return Opacity(
      opacity: dimmed ? 0.5 : 1,
      child: Text.rich(
        TextSpan(children: [
          if (contextBefore.isNotEmpty) TextSpan(text: contextBefore),
          if (before.isNotEmpty) TextSpan(text: before, style: recentChangeRemovedStyle(base)),
          if (before.isNotEmpty && after.isNotEmpty) const TextSpan(text: ' '),
          if (after.isNotEmpty) TextSpan(text: after, style: recentChangeAddedStyle(base)),
          if (contextAfter.isNotEmpty) TextSpan(text: contextAfter),
        ]),
        key: const Key('recent_change_occurrence'),
        style: base,
      ),
    );
  }
}
