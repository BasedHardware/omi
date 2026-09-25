import 'package:flutter/widgets.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Deletes [item] at once and offers Undo (docs/ux-contract.md §4, D5): no confirmation dialog.
///
/// The task disappears from the Tasks list and Home immediately; the server delete runs when the
/// toast closes without Undo (timed out, swiped away or replaced by the next toast). A failed
/// server delete puts the task back and says so. Resolves `true` when the task was deleted.
///
/// Every single-task delete — list swipe, long-press menu, the edit sheet, the task rows in a
/// conversation — should go through here so they all behave the same. Safe to call from a sheet
/// or row that is about to go away: the toast is shown synchronously and later feedback goes to
/// the navigator's context.
Future<bool> deleteTaskWithUndo(BuildContext context, ActionItemsProvider provider, ActionItemWithMetadata item) async {
  OmiHaptics.medium();
  final hostContext = Navigator.maybeOf(context)?.context ?? context;
  final l10n = context.l10n;
  provider.stageDeleteActionItem(item);
  final undone = await OmiFeedback.undo(
    context,
    l10n.actionItemDeleted,
    onUndo: () => provider.undoStagedDelete(item.id),
  );
  if (undone) return false;
  final deleted = await provider.commitStagedDelete(item.id);
  if (!deleted && hostContext.mounted) {
    OmiFeedback.error(hostContext, l10n.failedToDeleteActionItem);
  }
  return deleted;
}
