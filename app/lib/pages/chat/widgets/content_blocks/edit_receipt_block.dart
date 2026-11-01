import 'dart:async';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/backend/http/api/chat_receipts.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/home/home_deep_links.dart' show resolveIndexedMemoryById;
import 'package:omi/pages/memories/widgets/memory_dialog.dart';
import 'package:omi/pages/settings/person_detail_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

import 'chat_block_chrome.dart';
import 'conversation_link_blocks.dart';

/// Opens the item an edit receipt points at. Returns false when it is gone.
typedef EditReceiptTargetOpener = Future<bool> Function(BuildContext context, EditReceiptContentBlock block);

/// Undoes a receipt on the server.
typedef EditReceiptUndo = Future<ApiResult<EditReceiptUndoResult>> Function(String receiptId);

/// Renders an `editReceipt` block: what a chat agent changed, a tap to open the
/// changed item, and Undo while the server still allows it.
///
/// Mirrors the memory and task chips: the same card, an existing icon per
/// kind, the summary line. A kind this client does not know shows the summary
/// with no destination; Undo still works because it is keyed by receipt.
class EditReceiptBlock extends StatefulWidget {
  const EditReceiptBlock({
    super.key,
    required this.block,
    this.fetchConversation,
    this.openTarget,
    this.undo,
  });

  final EditReceiptContentBlock block;
  final Future<ServerConversation?> Function(String id)? fetchConversation;
  final EditReceiptTargetOpener? openTarget;
  final EditReceiptUndo? undo;

  /// Receipts undone in this session. A transcript row can be rebuilt from the
  /// message it came with before the server copy is reloaded; this keeps it
  /// from offering Undo again in between.
  static final Map<String, String> _undoneThisSession = {};

  /// Receipts whose undo the server refused (`unavailable`, 404, 409). Same
  /// lifetime as [_undoneThisSession]: a rebuild from the original message
  /// must not put Undo back.
  static final Set<String> _undoRefusedThisSession = {};

  @visibleForTesting
  static void resetSessionState() {
    _undoneThisSession.clear();
    _undoRefusedThisSession.clear();
  }

  @override
  State<EditReceiptBlock> createState() => _EditReceiptBlockState();
}

class _EditReceiptBlockState extends State<EditReceiptBlock> {
  bool _isUndoing = false;
  bool _isOpening = false;

  EditReceiptContentBlock get _block => widget.block;

  String? get _undoneAt => _block.undoneAt ?? EditReceiptBlock._undoneThisSession[_block.receiptId];

  bool get _isUndone => _undoneAt != null;

  bool get _undoRefused => EditReceiptBlock._undoRefusedThisSession.contains(_block.receiptId);

  bool get _canUndo => _block.undoable && !_isUndone && !_undoRefused;

  /// Whether the target still exists to open: a deleted item is gone until its
  /// delete is undone, and an undone create removed what it made.
  bool get _canOpen {
    if (_block.targetKind == EditReceiptTargetKind.unknown || _block.targetId == null) return false;
    if (_block.action == EditReceiptAction.deleted) return _isUndone;
    if (_block.action == EditReceiptAction.created) return !_isUndone;
    return true;
  }

  Future<void> _undo() async {
    if (_isUndoing || !_canUndo) return;
    setState(() => _isUndoing = true);
    final undo = widget.undo ?? const ChatReceiptsApi().undo;
    final receiptId = _block.receiptId;
    final result = await undo(receiptId);
    // Record the outcome before the mounted check. The row may already have
    // been disposed (a scroll, a provider rebuild) and the next one is built
    // from the original message.
    var showError = false;
    switch (result) {
      case ApiSuccess<EditReceiptUndoResult>(:final data) when data.undoneAt != null:
        EditReceiptBlock._undoRefusedThisSession.remove(receiptId);
        EditReceiptBlock._undoneThisSession[receiptId] = data.undoneAt!;
      case ApiSuccess<EditReceiptUndoResult>():
        // `unavailable`: the undo window closed or the inverse is ambiguous. Retrying cannot help.
        EditReceiptBlock._undoRefusedThisSession.add(receiptId);
        showError = true;
      case ApiFailure<EditReceiptUndoResult>(:final problem):
        // 404 (not this owner's receipt) and 409 (no longer undoable) are terminal.
        final terminal = problem.kind == ApiProblemKind.notFound || problem.statusCode == 409;
        if (terminal) EditReceiptBlock._undoRefusedThisSession.add(receiptId);
        showError = true;
    }
    if (!mounted) return;
    setState(() => _isUndoing = false);
    if (showError) OmiFeedback.error(context, context.l10n.chatBlockUndoFailed);
  }

  Future<void> _open() async {
    if (_isOpening || !_canOpen) return;
    setState(() => _isOpening = true);
    final open = widget.openTarget ??
        (context, block) => openEditReceiptTarget(context, block, fetchConversation: widget.fetchConversation);
    final opened = await open(context, _block);
    if (!mounted) return;
    setState(() => _isOpening = false);
    if (!opened) OmiFeedback.info(context, context.l10n.chatBlockUnavailable);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final (icon, label) = editReceiptKindChrome(context, _block.targetKind);
    final prefix = 'chat-block-editReceipt-${_block.id}';
    final canOpen = _canOpen;
    final canUndo = _canUndo;
    // The caption row grows with the text scale. A fixed 32px box clips the
    // Undo control once the user turns on larger text.
    final scaledControl = MediaQuery.textScalerOf(context).scale(32);
    final controlHeight = scaledControl < 32 ? 32.0 : scaledControl;

    final Widget? trailing;
    if (_isUndone) {
      trailing = Text(
        l10n.chatBlockUndone,
        key: Key('$prefix-undone'),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
      );
    } else if (canUndo) {
      trailing = OmiButton(
        key: Key('$prefix-undo'),
        label: l10n.undo,
        variant: OmiButtonVariant.tertiary,
        // Same family as the summary above it (the button style otherwise drops it).
        labelStyle: OmiType.footnote.copyWith(
          fontWeight: FontWeight.w600,
          fontFamily: Theme.of(context).textTheme.bodyMedium?.fontFamily,
        ),
        size: OmiButtonSize.compact,
        height: controlHeight,
        isLoading: _isUndoing,
        onPressed: _isUndoing ? null : _undo,
      );
    } else {
      trailing = null;
    }

    return ChatBlockCard(
      key: Key(prefix),
      explicitChildNodes: canUndo,
      semanticsLabel: '$label: ${_block.summary}${_isUndone ? ', ${l10n.chatBlockUndone}' : ''}',
      onTap: canOpen && !_isOpening ? _open : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Undo / Undone sits at the end of the caption row so the receipt stays as compact as
          // the memory and task chips. The trailing control is capped so a large text
          // scale ellipsizes instead of overflowing the row.
          LayoutBuilder(
            builder: (context, constraints) {
              return Row(
                children: [
                  Expanded(child: ChatBlockEyebrow(icon: icon, label: label, ellipsis: true)),
                  if (_isOpening) OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.textSecondary),
                  if (trailing != null) ...[
                    const SizedBox(width: 8),
                    ConstrainedBox(
                      constraints: BoxConstraints(maxWidth: constraints.maxWidth * 0.5),
                      child: trailing,
                    ),
                  ],
                ],
              );
            },
          ),
          const SizedBox(height: 4),
          Text(
            _block.summary,
            key: Key('$prefix-summary'),
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: _isUndone ? OmiColors.textSecondary : null,
                ),
          ),
        ],
      ),
    );
  }
}

/// The icon and caption each receipt kind shares with its existing chip.
(IconData, String) editReceiptKindChrome(BuildContext context, EditReceiptTargetKind kind) {
  final l10n = context.l10n;
  return switch (kind) {
    EditReceiptTargetKind.conversation => (Icons.subject, l10n.chatBlockConversation),
    EditReceiptTargetKind.memory => (Icons.psychology_outlined, l10n.chatBlockMemory),
    EditReceiptTargetKind.task => (Icons.checklist, l10n.chatBlockTask),
    EditReceiptTargetKind.person => (Icons.people_outline, l10n.chatBlockPerson),
    EditReceiptTargetKind.unknown => (Icons.edit_outlined, l10n.edit),
  };
}

/// Opens the receipt's target through the same pages the other chat chips use.
Future<bool> openEditReceiptTarget(
  BuildContext context,
  EditReceiptContentBlock block, {
  Future<ServerConversation?> Function(String id)? fetchConversation,
}) async {
  final id = block.targetId;
  if (id == null) return false;
  switch (block.targetKind) {
    case EditReceiptTargetKind.conversation:
      return openChatBlockConversation(context, conversationId: id, fetchConversation: fetchConversation);
    case EditReceiptTargetKind.memory:
      final provider = context.read<MemoriesProvider>();
      if (!provider.hasLoaded) await provider.loadMemories();
      if (!context.mounted) return false;
      Memory? memory;
      for (final row in provider.memories) {
        if (row.id == id) memory = row;
      }
      if (memory == null) {
        // Older than the loaded page: walk the owner-wide index like a deep link does.
        final uid = FirebaseAuth.instance.currentUser?.uid;
        if (uid == null) return false;
        memory = await resolveIndexedMemoryById(
          id,
          uid: uid,
          ownerIsCurrent: () => FirebaseAuth.instance.currentUser?.uid == uid,
        );
      }
      if (!context.mounted || memory == null) return false;
      unawaited(showMemoryDialog(context, provider, memory: memory));
      return true;
    case EditReceiptTargetKind.task:
      final provider = context.read<ActionItemsProvider>();
      ActionItemWithMetadata? task;
      for (final item in provider.actionItems) {
        if (item.id == id || item.taskId == id) task = item;
      }
      if (task == null) {
        final result = await action_items_api.ActionItemsApi(baseUrl: Env.apiBaseUrl ?? '').getById(id);
        if (result is ApiSuccess<ActionItemWithMetadata>) task = result.data;
      }
      if (!context.mounted || task == null) return false;
      unawaited(showActionItemFormSheet(context, actionItem: task));
      return true;
    case EditReceiptTargetKind.person:
      unawaited(routeToPage(context, PersonDetailPage(personId: id)));
      return true;
    case EditReceiptTargetKind.unknown:
      return false;
  }
}
