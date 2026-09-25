import 'package:flutter/widgets.dart';

import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Whether [memory] can be edited (and so deleted by swipe) in the app. Superseded, invalidated,
/// locked and non-fact knowledge-ledger rows are read-only: they open, but they do not edit.
bool memoryIsEditable(Memory memory) {
  if (!memory.isKnowledgeLedger) return true;
  return !memory.deleted &&
      memory.invalidAt == null &&
      (memory.supersededBy ?? '').trim().isEmpty &&
      memory.ledgerKind == KnowledgeLedgerKind.fact &&
      !memory.isLocked;
}

/// Deletes [memory] at once and offers Undo (docs/ux-contract.md §4, D5): no confirmation dialog.
///
/// The provider holds the server delete back; the delete commits when the toast closes without
/// Undo (timed out, swiped away or replaced by the next toast). Every memory delete — list swipe,
/// long-press menu, edit sheet — goes through here so they all show the same toast.
///
/// Safe to call from a sheet that closes right after: the toast is shown synchronously and the
/// rest only talks to [provider].
Future<void> deleteMemoryWithUndo(BuildContext context, MemoriesProvider provider, Memory memory) async {
  provider.deleteMemory(memory);
  PlatformManager.instance.analytics.memoriesPageDeletedMemory(memory);
  final undone = await OmiFeedback.undo(
    context,
    context.l10n.memoryDeleted,
    onUndo: () => provider.restoreLastDeletedMemory(id: memory.id),
  );
  if (!undone) await provider.confirmPendingDeletion(id: memory.id);
}
