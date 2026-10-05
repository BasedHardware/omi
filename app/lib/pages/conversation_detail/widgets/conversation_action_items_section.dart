import 'package:flutter/material.dart';

import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/widgets/person_avatar.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What one action-item row says under its description. Every field is absent rather than
/// "Unknown": a row with no owner and no due date has no metadata line at all.
///
/// The same layout as the Mac (`ConversationActionItemRow`) and the web share page: the item,
/// then owner and due date on one line, then the context on its own line.
class ActionItemMeta {
  const ActionItemMeta({this.owner, this.due, this.context});

  /// "You" for the reader's own items, otherwise the name the extraction gave.
  final String? owner;
  final String? due;
  final String? context;

  bool get hasOwnerOrDue => owner != null || due != null;

  static final _emailShaped = RegExp(r'[^\s@]+@[^\s@]+\.[^\s@]+');

  factory ActionItemMeta.of(ActionItem item, {required AppLocalizations l10n, required OmiDateFormat dates}) {
    final name = item.ownerName?.trim() ?? '';
    final owner = item.captureOwner == 'user' ? l10n.you : (name.isEmpty || _emailShaped.hasMatch(name) ? null : name);
    final dueAt = item.dueAt;
    final context = item.context?.trim() ?? '';
    return ActionItemMeta(
      owner: owner,
      due: dueAt == null ? null : l10n.taskDueDate(dates.dayHeader(dueAt.toLocal())),
      context: context.isEmpty ? null : context,
    );
  }
}

/// The note's action items, after its sections: the mobile twin of the Mac's Action Items card.
/// Read-only here; promoting an item or ticking it off happens in Tasks. Absent when the note has
/// none.
class ConversationActionItemsSection extends StatelessWidget {
  const ConversationActionItemsSection({super.key, required this.items});

  final List<ActionItem> items;

  @override
  Widget build(BuildContext context) {
    final active = items.where((item) => !item.deleted).toList();
    if (active.isEmpty) return const SliverToBoxAdapter(child: SizedBox.shrink());
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    return SliverToBoxAdapter(
      child: Padding(
        key: const ValueKey('conversation_action_items_section'),
        padding: const EdgeInsets.only(top: OmiSpacing.md, bottom: OmiSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              header: true,
              child: Row(
                children: [
                  ExcludeSemantics(
                    child: Icon(Icons.checklist_rounded, size: 18, color: OmiColors.textSecondary),
                  ),
                  const SizedBox(width: OmiSpacing.xs),
                  Flexible(
                    child: Text(
                      l10n.actionItemsTitle,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: OmiSpacing.sm),
            DecoratedBox(
              decoration: BoxDecoration(
                border: Border.all(color: OmiColors.border),
                borderRadius: OmiRadius.lgAll,
              ),
              child: Column(
                children: [
                  for (var i = 0; i < active.length; i++) ...[
                    if (i > 0) Divider(height: 1, thickness: 1, color: OmiColors.border),
                    _ActionItemRow(item: active[i], meta: ActionItemMeta.of(active[i], l10n: l10n, dates: dates)),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionItemRow extends StatelessWidget {
  const _ActionItemRow({required this.item, required this.meta});

  final ActionItem item;
  final ActionItemMeta meta;

  @override
  Widget build(BuildContext context) {
    final secondary = OmiType.footnote.copyWith(color: OmiColors.textSecondary);
    final owner = meta.owner;
    final due = meta.due;
    return MergeSemantics(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Semantics(
                checked: item.completed,
                child: Icon(
                  item.completed ? Icons.check_circle : Icons.radio_button_unchecked,
                  size: 20,
                  color: item.completed ? OmiColors.success : OmiColors.textTertiary,
                ),
              ),
            ),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.description,
                    style: OmiType.callout.copyWith(
                      color: item.completed ? OmiColors.textSecondary : OmiColors.textPrimary,
                      decoration: item.completed ? TextDecoration.lineThrough : null,
                    ),
                  ),
                  if (meta.hasOwnerOrDue) ...[
                    const SizedBox(height: OmiSpacing.xxs),
                    Wrap(
                      crossAxisAlignment: WrapCrossAlignment.center,
                      spacing: OmiSpacing.xs,
                      runSpacing: OmiSpacing.xxs,
                      children: [
                        if (owner != null)
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              _OwnerInitials(name: owner),
                              const SizedBox(width: OmiSpacing.xxs + 2),
                              Flexible(child: Text(owner, style: secondary)),
                            ],
                          ),
                        if (owner != null && due != null)
                          ExcludeSemantics(
                              child: Text('·', style: secondary)), // omi-ux-allow: hardcoded-text -- separator glyph
                        if (due != null) Text(due, style: secondary),
                      ],
                    ),
                  ],
                  if (meta.context != null) ...[
                    const SizedBox(height: OmiSpacing.xxs),
                    Text(meta.context!, style: secondary),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A small initials disc, coloured like the person's avatar elsewhere.
class _OwnerInitials extends StatelessWidget {
  const _OwnerInitials({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Container(
        width: 18,
        height: 18,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: PersonAvatar.colorFor(name), shape: BoxShape.circle),
        // Speaker colours are dark in both appearances, so the initials are always light.
        child: Text(
          PersonAvatar.initials(name),
          style: OmiType.caption.copyWith(
              fontSize: 8, // omi-ux-allow: font-size-literal -- fixed 18 pt disc
              fontWeight: FontWeight.w600,
              color: OmiPalette.dark.textPrimary),
          maxLines: 1,
          textScaler: TextScaler.noScaling,
        ),
      ),
    );
  }
}
