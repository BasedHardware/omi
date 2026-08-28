/// "Add to Tasks" for a conversation's extracted action items.
///
/// Automatic capture is suggestion-only (INV-TASK-2, #11974): an extracted
/// action item is never written to the task list, it becomes a pending Candidate
/// that reaches the list only through an explicit user gesture. That gesture
/// exists on macOS — the conversation summary, the Suggested section, and the
/// chat card — but not on mobile, so a suggestion captured on a phone has no way
/// to become a task and expires after SUGGESTION_TTL.
///
/// This is the mobile counterpart of the macOS conversation-summary button. It
/// mirrors that surface's behaviour, including its known limitation: it creates
/// the task without resolving the twin pending Candidate, which still expires on
/// its own.
///
/// Manual create is outside the capture-policy boundary — it carries a real user
/// gesture and writes directly by design — so this path is a task writer and the
/// Candidate lifecycle is untouched.
///
/// POST /v1/action-items is content-idempotent on (uid, normalized description),
/// so a repeat tap returns the original item rather than duplicating it. The
/// `added` state below is presentation only.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

@visibleForTesting
enum AddToTasksState { idle, adding, added }

class AddToTasksButton extends StatefulWidget {
  const AddToTasksButton({
    super.key,
    required this.description,
    required this.conversationId,
  });

  /// The action item's text, exactly as rendered in the conversation.
  final String description;

  /// Links the created task back to the conversation it came from.
  final String conversationId;

  @override
  State<AddToTasksButton> createState() => AddToTasksButtonState();
}

@visibleForTesting
class AddToTasksButtonState extends State<AddToTasksButton> {
  AddToTasksState state = AddToTasksState.idle;

  /// Drive the presentation state directly. Tests use this instead of reaching
  /// into the protected `setState`.
  @visibleForTesting
  void setStateForTesting(AddToTasksState next) => setState(() => state = next);

  Future<void> add() async {
    if (state != AddToTasksState.idle) return;
    setState(() => state = AddToTasksState.adding);

    try {
      final created = await action_items_api.createActionItem(
        description: widget.description,
        conversationId: widget.conversationId,
      );
      if (!mounted) return;

      if (created == null) {
        setState(() => state = AddToTasksState.idle);
        showFailure();
        return;
      }

      setState(() => state = AddToTasksState.added);

      // Keep the Action Items page in step without a manual pull-to-refresh. A
      // refresh failure must not undo a task that was created successfully.
      try {
        await context.read<ActionItemsProvider>().refreshActionItems();
      } catch (e) {
        Logger.debug('AddToTasksButton: refresh after create failed: $e');
      }
    } catch (e, st) {
      Logger.error('AddToTasksButton: create failed: $e\n$st');
      if (!mounted) return;
      setState(() => state = AddToTasksState.idle);
      showFailure();
    }
  }

  @visibleForTesting
  void showFailure() {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(context.l10n.addToTasksFailed)),
    );
  }

  @override
  Widget build(BuildContext context) {
    switch (state) {
      case AddToTasksState.adding:
        return const Padding(
          padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          child: SizedBox(
            height: 16,
            width: 16,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        );

      case AddToTasksState.added:
        return Padding(
          padding: const EdgeInsets.only(left: 8, top: 4),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.check, size: 16, color: Colors.grey.shade500),
              const SizedBox(width: 4),
              Text(
                context.l10n.addedToTasks,
                style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
              ),
            ],
          ),
        );

      case AddToTasksState.idle:
        return IconButton(
          onPressed: add,
          icon: const Icon(Icons.playlist_add, size: 20),
          color: Colors.grey.shade300,
          tooltip: context.l10n.addToTasks,
          visualDensity: VisualDensity.compact,
          padding: const EdgeInsets.only(left: 8),
          constraints: const BoxConstraints(),
        );
    }
  }
}
