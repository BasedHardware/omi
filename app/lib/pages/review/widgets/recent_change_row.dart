import 'package:flutter/material.dart';

import 'package:omi/pages/review/widgets/recent_change_groups.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Text Omi replaced: struck through on a red tint.
TextStyle recentChangeRemovedStyle(TextStyle base) => base.copyWith(
      color: OmiColors.danger,
      decoration: TextDecoration.lineThrough,
      decorationColor: OmiColors.danger,
      backgroundColor: OmiColors.dangerSurface,
    );

/// Text Omi wrote in its place: on a green tint.
TextStyle recentChangeAddedStyle(TextStyle base) =>
    base.copyWith(color: OmiColors.success, fontWeight: FontWeight.w600, backgroundColor: OmiColors.successSurface);

const _inlineLimit = 48;

/// The change itself: what the text was and what it is now. Short values sit on one line with an
/// arrow; longer ones stack. Task merges strike each retired line above the surviving task.
class RecentChangeDiff extends StatelessWidget {
  const RecentChangeDiff({super.key, required this.before, required this.after, this.section, this.dimmed = false});

  final String? before;

  /// Empty means removed; null means the server did not say.
  final String? after;
  final RecentChangeSection? section;
  final bool dimmed;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final before = this.before;
    final after = this.after;
    final removed = after != null && after.isEmpty;
    final beforeLines = before == null
        ? const <String>[]
        : section == RecentChangeSection.tasks
            ? before.split('\n').map((l) => l.trim()).where((l) => l.isNotEmpty).toList(growable: false)
            : [before];
    final inline = !removed &&
        beforeLines.length <= 1 &&
        (before ?? '').length <= _inlineLimit &&
        (after ?? '').length <= _inlineLimit &&
        !(before ?? '').contains('\n') &&
        !(after ?? '').contains('\n');
    final base = section == RecentChangeSection.terms ? OmiType.body : OmiType.subhead;
    final Widget body;
    if (inline) {
      body = Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: OmiSpacing.xs,
        runSpacing: OmiSpacing.xxs,
        children: [
          if (before != null) _Chip(text: before, key: const Key('recent_change_before'), removed: true, base: base),
          if (before != null && after != null)
            Icon(Icons.arrow_forward, size: 16, color: OmiColors.textSecondary, semanticLabel: l10n.reviewChangeAfter),
          if (after != null) _Chip(text: after, key: const Key('recent_change_after'), removed: false, base: base),
        ],
      );
    } else {
      body = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (i, line) in beforeLines.indexed)
            Padding(
              padding: EdgeInsets.only(top: i == 0 ? 0 : OmiSpacing.xxs),
              child: _Block(text: line, key: i == 0 ? const Key('recent_change_before') : null, removed: true),
            ),
          if (beforeLines.isNotEmpty && after != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xxs),
              child: Icon(Icons.arrow_downward,
                  size: 16, color: OmiColors.textSecondary, semanticLabel: l10n.reviewChangeAfter),
            ),
          if (removed)
            Text(l10n.reviewChangeRemoved,
                key: const Key('recent_change_after'), style: OmiType.footnote.copyWith(color: OmiColors.textSecondary))
          else if (after != null)
            _Block(text: after, key: const Key('recent_change_after'), removed: false),
        ],
      );
    }
    return Opacity(opacity: dimmed ? 0.5 : 1, child: body);
  }
}

class _Chip extends StatelessWidget {
  const _Chip({super.key, required this.text, required this.removed, required this.base});

  final String text;
  final bool removed;
  final TextStyle base;

  @override
  Widget build(BuildContext context) {
    final style = removed
        ? base.copyWith(
            color: OmiColors.danger, decoration: TextDecoration.lineThrough, decorationColor: OmiColors.danger)
        : base.copyWith(color: OmiColors.success, fontWeight: FontWeight.w600);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: removed ? OmiColors.dangerSurface : OmiColors.successSurface,
        borderRadius: OmiRadius.smAll,
      ),
      child: Text(text, style: style),
    );
  }
}

class _Block extends StatelessWidget {
  const _Block({super.key, required this.text, required this.removed});

  final String text;
  final bool removed;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.xs),
      decoration: BoxDecoration(
        color: removed ? OmiColors.dangerSurface : OmiColors.successSurface,
        borderRadius: OmiRadius.smAll,
      ),
      child: Text(
        text,
        style: removed
            ? OmiType.subhead.copyWith(
                color: OmiColors.textSecondary,
                decoration: TextDecoration.lineThrough,
                decorationColor: OmiColors.danger,
              )
            : OmiType.subhead,
      ),
    );
  }
}

/// One row on Recent changes: the change, where it happened, and what can be done about it.
class RecentChangeRow extends StatelessWidget {
  const RecentChangeRow({
    super.key,
    required this.group,
    required this.busy,
    required this.onOpen,
    required this.onToggleAll,
    this.onOpenTask,
  });

  final RecentChangeGroup group;
  final bool busy;
  final VoidCallback onOpen;

  /// Undoes every active change in the group, or redoes them all once all are undone.
  final VoidCallback onToggleAll;
  final VoidCallback? onOpenTask;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final latest = group.latest;
    final undone = group.allUndone;
    final multiple = group.changes.length > 1;
    final places = group.placeCount;
    final before = group.before;
    final after = group.after;
    final hasDiff = before != null || after != null;

    final String meta;
    if (group.section == RecentChangeSection.terms && (multiple || places > 1)) {
      meta = [l10n.reviewChangeConversationCount(group.conversationCount), l10n.reviewChangePlaceCount(places)]
          .join(' · ');
    } else {
      meta = [
        if (recentChangeSourceTitle(latest) case final title?) title,
        dates.date(recentChangeSourceTime(latest)),
      ].join(' · ');
    }
    final note = recentChangeNote(latest);

    final actions = <Widget>[
      if (group.section == RecentChangeSection.terms && places > 1)
        OmiButton.tertiary(
          key: ValueKey('recent_change_show_all_${group.latest.changeId}'),
          label: l10n.reviewChangeShowAll(places),
          size: OmiButtonSize.compact,
          onPressed: onOpen,
        )
      else if (group.section == RecentChangeSection.tasks && onOpenTask != null)
        OmiButton.tertiary(
          key: ValueKey('recent_change_view_task_${group.latest.changeId}'),
          label: l10n.reviewChangeViewTask,
          size: OmiButtonSize.compact,
          onPressed: onOpenTask,
        )
      else if (group.section != RecentChangeSection.terms)
        OmiButton.tertiary(
          key: ValueKey('recent_change_evidence_${group.latest.changeId}'),
          label: l10n.reviewChangeSeeEvidence,
          size: OmiButtonSize.compact,
          onPressed: onOpen,
        ),
      OmiButton.tertiary(
        key: ValueKey('recent_change_toggle_${group.latest.changeId}'),
        label: undone ? l10n.redo : (multiple && group.active.length > 1 ? l10n.reviewChangeUndoAll : l10n.undo),
        size: OmiButtonSize.compact,
        isLoading: busy,
        onPressed: busy ? null : onToggleAll,
      ),
    ];

    return Material(
      color: OmiColors.surface1,
      borderRadius: OmiRadius.lgAll,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        key: ValueKey('recent_change_${group.latest.changeId}'),
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 14, OmiSpacing.xs, OmiSpacing.xxs),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.only(right: OmiSpacing.xs),
                child: hasDiff
                    ? RecentChangeDiff(before: before, after: after, section: group.section, dimmed: undone)
                    : Text(latest.title,
                        style: OmiType.subhead.copyWith(
                          fontWeight: FontWeight.w600,
                          decoration: undone ? TextDecoration.lineThrough : null,
                        )),
              ),
              if (!hasDiff && latest.snippet != null)
                Padding(
                  padding: const EdgeInsets.only(top: OmiSpacing.xs, right: OmiSpacing.xs),
                  child: Text(latest.snippet!, style: OmiType.footnote),
                ),
              if (meta.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: OmiSpacing.xs, right: OmiSpacing.xs),
                  child: Text(meta,
                      key: const Key('recent_change_meta'),
                      style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                ),
              if (undone)
                Padding(
                  padding: const EdgeInsets.only(top: OmiSpacing.xxs, right: OmiSpacing.xs),
                  child: Text(l10n.reviewChangeUndone, style: OmiType.footnote),
                )
              else if (note != null)
                Padding(
                  padding: const EdgeInsets.only(top: OmiSpacing.xxs, right: OmiSpacing.xs),
                  child: Text(note,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                ),
              Wrap(alignment: WrapAlignment.end, children: actions),
            ],
          ),
        ),
      ),
    );
  }
}
