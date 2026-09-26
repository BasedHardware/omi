import 'dart:async';

import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/action_items.dart' show tryGetActionItems;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Opens the shared task editor (the same sheet as the Tasks tab) for [item], a task of the
/// conversation [provider] shows, and folds the edit back into the conversation afterwards.
///
/// Conversation tasks are stored twice: in the conversation's structured summary (what this tab
/// lists) and as standalone tasks (what the editor edits, matched here by description).
Future<void> openConversationTask(BuildContext context, ConversationDetailProvider provider, ActionItem item) async {
  final conversationId = provider.conversation.id;
  final l10n = context.l10n;
  final listed = await tryGetActionItems(conversationId: conversationId, limit: 200);
  if (!context.mounted) return;
  final match = listed?.actionItems.firstWhereOrNull((task) => task.description.trim() == item.description.trim());
  if (match == null) {
    OmiFeedback.error(context, l10n.somethingWentWrong);
    return;
  }
  // The same guarded editor the Tasks tab opens: swipe-down with unsaved edits asks first.
  await showActionItemFormSheet(context, actionItem: match);
  final refreshed = await tryGetActionItems(conversationId: conversationId, limit: 200);
  if (refreshed == null || provider.conversationOrNull?.id != conversationId) return;
  final updated = refreshed.actionItems.firstWhereOrNull((task) => task.id == match.id);
  provider.applyTaskEdit(item,
      description: updated?.description, completed: updated?.completed, deleted: updated == null);
}

/// One task row of a conversation: a checkbox that completes it at once, and a tap that opens the
/// shared task editor.
class ActionItemDetailWidget extends StatefulWidget {
  final ActionItem actionItem;
  final String conversationId;

  const ActionItemDetailWidget({super.key, required this.actionItem, required this.conversationId});

  @override
  State<ActionItemDetailWidget> createState() => _ActionItemDetailWidgetState();
}

class _ActionItemDetailWidgetState extends State<ActionItemDetailWidget> {
  static final Map<String, bool> _pendingStates = {}; // Track pending states by description
  Timer? _pendingClearTimer;

  @override
  void dispose() {
    _pendingClearTimer?.cancel();
    _pendingClearTimer = null;
    _pendingStates.remove(widget.actionItem.description);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        final actionItem = provider.conversation.structured.actionItems.firstWhere(
          (item) => item.description == widget.actionItem.description,
          orElse: () => widget.actionItem,
        );
        final isCompleted = _pendingStates[widget.actionItem.description] ?? actionItem.completed;

        return Material(
          color: OmiColors.surface1,
          borderRadius: OmiRadius.lgAll,
          child: InkWell(
            borderRadius: OmiRadius.lgAll,
            onTap: () {
              OmiHaptics.light();
              openConversationTask(context, provider, actionItem);
            },
            child: Padding(
              padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.xxs, OmiSpacing.md, OmiSpacing.xxs),
              child: Row(
                children: [
                  Semantics(
                    checked: isCompleted,
                    label: actionItem.description,
                    excludeSemantics: true,
                    onTap: () => _toggleCompletion(provider, actionItem),
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => _toggleCompletion(provider, actionItem),
                      child: SizedBox.square(
                        dimension: kOmiMinTapTarget,
                        child: Center(
                          child: Container(
                            width: 20,
                            height: 20,
                            decoration: BoxDecoration(
                              color: isCompleted ? OmiColors.accent : Colors.transparent,
                              border: Border.all(
                                color: isCompleted ? OmiColors.accent : OmiColors.textTertiary,
                                width: 2,
                              ),
                              borderRadius: const BorderRadius.all(Radius.circular(4)),
                            ),
                            child: isCompleted ? const Icon(Icons.check, size: 14, color: OmiColors.onAccent) : null,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.xxs),
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
                      child: Text(
                        actionItem.description,
                        style: OmiType.subhead.copyWith(
                          color: isCompleted ? OmiColors.textTertiary : OmiColors.textPrimary,
                          decoration: isCompleted ? TextDecoration.lineThrough : null,
                          decorationColor: OmiColors.textTertiary,
                          height: 1.4,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  void _toggleCompletion(ConversationDetailProvider provider, ActionItem actionItem) async {
    OmiHaptics.light();

    final newValue = !actionItem.completed;
    final itemDescription = widget.actionItem.description;
    setState(() => _pendingStates[itemDescription] = newValue);

    final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);
    try {
      await conversationProvider.updateGlobalActionItemState(provider.conversation, itemDescription, newValue);

      // Let the reader see the change before the row moves to its new section.
      _pendingClearTimer?.cancel();
      _pendingClearTimer = Timer(const Duration(milliseconds: 200), () {
        _pendingClearTimer = null;
        if (mounted) setState(() => _pendingStates.remove(itemDescription));
      });

      final currentIndex =
          provider.conversation.structured.actionItems.indexWhere((item) => item.description == itemDescription);
      if (currentIndex != -1) {
        if (newValue) {
          PlatformManager.instance.analytics.checkedActionItem(provider.conversation, currentIndex);
        } else {
          PlatformManager.instance.analytics.uncheckedActionItem(provider.conversation, currentIndex);
        }
      }
    } catch (e) {
      if (mounted) setState(() => _pendingStates.remove(itemDescription));
      Logger.debug('Error updating action item state: $e');
    }
  }
}

/// A section header with a labelled count pill ("Tasks  3", read as "3 pending").
class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, required this.count, required this.countLabel});

  final String title;
  final int count;
  final String countLabel;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xs, OmiSpacing.xl, OmiSpacing.xs, OmiSpacing.xs),
      child: Row(
        children: [
          Semantics(header: true, child: Text(title, style: OmiType.title3)),
          const SizedBox(width: OmiSpacing.xs),
          Semantics(
            label: countLabel,
            excludeSemantics: true,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: 2),
              decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
              child: Text(
                '$count',
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PlaceholderRow extends StatelessWidget {
  const _PlaceholderRow(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs),
      child: Container(
        constraints: const BoxConstraints(minHeight: 52),
        alignment: Alignment.center,
        decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
        child: Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
      ),
    );
  }
}

/// The conversation's Tasks tab: pending tasks, then completed ones.
class ActionItemsTab extends StatelessWidget {
  const ActionItemsTab({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        final allActionItems = provider.conversation.structured.actionItems.where((item) => !item.deleted).toList();
        final incompleteItems = allActionItems.where((item) => !item.completed).toList();
        final completedItems = allActionItems.where((item) => item.completed).toList();

        if (allActionItems.isEmpty) {
          return OmiEmptyState(
            icon: Icons.check_circle_outline,
            title: context.l10n.noTasksYet,
            message: context.l10n.conversationTasksEmptyMessage,
          );
        }

        Widget itemList(List<ActionItem> items) => SliverList(
              delegate: SliverChildBuilderDelegate((context, index) {
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: 6),
                  child: ActionItemDetailWidget(actionItem: items[index], conversationId: provider.conversation.id),
                );
              }, childCount: items.length),
            );

        return CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverToBoxAdapter(
              child: _SectionHeader(
                title: context.l10n.tasks,
                count: incompleteItems.length,
                countLabel: context.l10n.nPending(incompleteItems.length),
              ),
            ),
            if (incompleteItems.isNotEmpty)
              itemList(incompleteItems)
            else
              SliverToBoxAdapter(child: _PlaceholderRow(context.l10n.noPendingTasks)),
            SliverToBoxAdapter(
              child: _SectionHeader(
                title: context.l10n.completed,
                count: completedItems.length,
                countLabel: context.l10n.nCompleted(completedItems.length),
              ),
            ),
            if (completedItems.isNotEmpty)
              itemList(completedItems)
            else
              SliverToBoxAdapter(child: _PlaceholderRow(context.l10n.emptyDoneMessage)),
            const SliverPadding(padding: EdgeInsets.only(bottom: 150)),
          ],
        );
      },
    );
  }
}
