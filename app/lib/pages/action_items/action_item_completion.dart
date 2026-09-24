import 'package:flutter/material.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/providers/action_items_provider.dart';
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
  final messenger = ScaffoldMessenger.of(context);
  final l10n = context.l10n;
  messenger.hideCurrentSnackBar();
  final saved = await provider.updateActionItemState(item, completed);
  if (!context.mounted) return;
  if (saved) {
    if (completed) onCompleted?.call();
    return;
  }
  messenger.showSnackBar(SnackBar(
    content: Text(l10n.failedToUpdateActionItem),
    action: SnackBarAction(
      label: l10n.retry,
      onPressed: () {
        if (!context.mounted) return;
        setActionItemCompleted(context, provider, item, completed, onCompleted: onCompleted);
      },
    ),
  ));
}
