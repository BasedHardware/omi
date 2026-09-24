import 'package:flutter/material.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Completion controls share persistence feedback; retry repeats the intended
/// state rather than toggling a potentially stale copy of the task again.
Future<void> setActionItemCompleted(
  BuildContext context,
  ActionItemsProvider provider,
  ActionItemWithMetadata item,
  bool completed, {
  VoidCallback? onCompleted,
}) async {
  if (provider.isUpdatingActionItemState(item.id)) return;
  final l10n = context.l10n;
  OmiFeedback.hide(context);
  final saved = await provider.updateActionItemState(item, completed);
  if (!context.mounted) return;
  if (saved) {
    if (completed) onCompleted?.call();
    return;
  }
  OmiFeedback.error(
    context,
    l10n.failedToUpdateActionItem,
    actionLabel: l10n.retry,
    onAction: () {
      if (!context.mounted) return;
      setActionItemCompleted(context, provider, item, completed, onCompleted: onCompleted);
    },
  );
}
