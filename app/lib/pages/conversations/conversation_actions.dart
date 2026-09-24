import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/capture_group_separation.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/share.dart';
import 'package:omi/pages/conversation_detail/widgets/capture_recordings.dart';
import 'package:omi/pages/conversations/widgets/move_to_folder_sheet.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/conversations/capture_groups.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// The conversation actions every surface shares (docs/ux-contract.md §4, D5): one delete path for a
// swiped row, the row's context menu, the selection bar and the detail page, and the row menu itself.

/// Asks before deleting one conversation. The "Don't ask again" row is allowed because every
/// conversation delete is backed by an Undo toast; once ticked, this returns `true` without asking.
/// Offline it explains why the delete cannot happen and returns `false`.
Future<bool> confirmConversationDelete(BuildContext context) async {
  final l10n = context.l10n;
  if (!context.read<ConnectivityProvider>().isConnected) {
    await showOmiAlert(
      context,
      title: l10n.unableToDeleteConversation,
      message: l10n.pleaseCheckInternetConnectionAndTryAgain,
    );
    return false;
  }
  final prefs = SharedPreferencesUtil();
  if (!prefs.showConversationDeleteConfirmation) return true;
  final result = await showOmiConfirmWithOptOut(
    context,
    title: l10n.deleteConversationTitle,
    message: l10n.deleteConversationMessage,
    confirmLabel: l10n.delete,
    destructive: true,
  );
  if (result.confirmed && result.dontAskAgain) prefs.showConversationDeleteConfirmation = false;
  return result.confirmed;
}

/// Removes [conversations] from the list now, offers Undo for 5 s, and sends the server DELETE when
/// the toast closes without Undo (or when the provider's pending window runs out first).
///
/// [context] only needs a `ScaffoldMessenger` and the providers above it; after a page pops, pass a
/// context that outlives it (for example `Navigator.of(context).context`).
Future<void> deleteConversationsWithUndo(BuildContext context, List<ServerConversation> conversations) async {
  if (conversations.isEmpty) return;
  final provider = context.read<ConversationProvider>();
  final l10n = context.l10n;
  for (final conversation in conversations) {
    provider.deleteConversationLocally(conversation);
  }
  final undone = await OmiFeedback.undo(
    context,
    conversations.length == 1 ? l10n.conversationDeleted : l10n.conversationsDeletedCount(conversations.length),
    onUndo: () {
      for (final conversation in conversations) {
        provider.undoDeletedConversation(conversation);
      }
    },
  );
  if (undone) return;
  for (final conversation in conversations) {
    provider.commitPendingDelete(conversation.id);
  }
}

/// Deletes the selected conversations after one confirmation. A bulk delete is always confirmed
/// (never "Don't ask again"); it is still backed by Undo.
Future<void> confirmAndDeleteSelectedConversations(BuildContext context) async {
  final provider = context.read<ConversationProvider>();
  final selected = provider.selectedConversations;
  if (selected.isEmpty) return;
  final l10n = context.l10n;
  if (!context.read<ConnectivityProvider>().isConnected) {
    await showOmiAlert(
      context,
      title: l10n.unableToDeleteConversation,
      message: l10n.pleaseCheckInternetConnectionAndTryAgain,
    );
    return;
  }
  final confirmed = await showOmiConfirm(
    context,
    title: l10n.deleteConversationsTitle(selected.length),
    message: l10n.deleteConversationsMessage,
    confirmLabel: l10n.delete,
    destructive: true,
  );
  if (!confirmed || !context.mounted) return;
  provider.exitSelectionMode();
  await deleteConversationsWithUndo(context, selected);
}

/// Moves the selected conversations into a folder the reader picks, then leaves selection mode.
Future<void> moveSelectedConversationsToFolder(BuildContext context) async {
  final provider = context.read<ConversationProvider>();
  final folderProvider = context.read<FolderProvider>();
  final selected = provider.selectedConversations;
  if (selected.isEmpty) return;
  if (folderProvider.folders.isEmpty) await folderProvider.loadFolders();
  if (!context.mounted) return;
  final folderId = await showMoveConversationsToFolderSheet(context, count: selected.length);
  if (folderId == null || !context.mounted) return;
  final l10n = context.l10n;
  provider.exitSelectionMode();
  final moved = await folderProvider.bulkMoveConversations([for (final c in selected) c.id], folderId);
  if (!context.mounted) return;
  if (moved <= 0) {
    OmiFeedback.error(context, l10n.failedToMoveConversations);
    return;
  }
  for (final conversation in selected) {
    conversation.folderId = folderId;
    PlatformManager.instance.analytics.conversationMovedToFolder(
      conversationId: conversation.id,
      toFolderId: folderId,
      source: 'list_selection_bar',
    );
  }
  provider.groupConversationsByDate();
  OmiFeedback.confirm(context, l10n.conversationsMovedCount(moved));
}

/// Stars or unstars [conversation] and updates the list.
Future<void> toggleConversationStarred(BuildContext context, ServerConversation conversation, {String? source}) async {
  final provider = context.read<ConversationProvider>();
  final l10n = context.l10n;
  final starred = !conversation.starred;
  final ok = await setConversationStarred(conversation.id, starred);
  if (!context.mounted) return;
  if (!ok) {
    OmiFeedback.error(context, l10n.failedToUpdateStarred);
    return;
  }
  conversation.starred = starred;
  provider.updateConversationInSortedList(conversation);
  PlatformManager.instance.analytics.conversationStarToggled(
    conversation: conversation,
    starred: starred,
    source: source ?? 'list_context_menu',
  );
}

/// Shares [conversation]'s link, the same way the conversation page does: a private conversation
/// first asks ("Anyone with the link can view"), becomes shared, and goes back to private when the
/// share sheet is dismissed without sharing.
Future<void> shareConversation(BuildContext context, ServerConversation conversation) async {
  final l10n = context.l10n;
  final wasPrivate = conversation.visibility != ConversationVisibility.shared;
  if (wasPrivate) {
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.shareConversationQuestion,
      message: l10n.anyoneWithLinkCanView,
      confirmLabel: l10n.share,
    );
    if (!confirmed || !context.mounted) return;
    final ok = await setConversationVisibility(conversation.id);
    if (!context.mounted) return;
    if (!ok) {
      OmiFeedback.error(context, l10n.conversationUrlNotShared);
      return;
    }
    conversation.visibility = ConversationVisibility.shared;
  }
  PlatformManager.instance.analytics.conversationShared(conversation: conversation, shareMethod: 'url_share');
  final box = context.findRenderObject() as RenderBox?;
  final outcome = await shareConversationLink(
    conversation,
    sharePositionOrigin: box == null || !box.hasSize ? null : box.localToGlobal(Offset.zero) & box.size,
  );
  if (wasPrivate && outcome.status == ShareResultStatus.dismissed) {
    final reverted =
        await setConversationVisibility(conversation.id, visibility: ConversationVisibility.private_.value);
    if (reverted) conversation.visibility = ConversationVisibility.private_;
  }
}

/// Moves one conversation into a folder the reader picks.
Future<void> moveConversationToFolder(BuildContext context, ServerConversation conversation) async {
  final provider = context.read<ConversationProvider>();
  final folderProvider = context.read<FolderProvider>();
  if (folderProvider.folders.isEmpty) await folderProvider.loadFolders();
  if (!context.mounted) return;
  final previousFolderId = conversation.folderId;
  final folderId = await showMoveToFolderSheet(
    context,
    conversationId: conversation.id,
    currentFolderId: previousFolderId,
  );
  if (folderId == null) return;
  conversation.folderId = folderId;
  provider.groupConversationsByDate();
  PlatformManager.instance.analytics.conversationMovedToFolder(
    conversationId: conversation.id,
    fromFolderId: previousFolderId,
    toFolderId: folderId,
    source: 'list_context_menu',
  );
}

/// The actions a conversation row's long-press offers.
enum ConversationRowAction { open, star, move, share, recordings, separate, select, delete }

/// Long-press menu of a conversation row: Open, Star / Unstar, Move to Folder, Share, Select
/// (enters multi-select) and Delete. A row that stands for an event several devices recorded also
/// offers Recordings and Separate… (design ruling 2026-09-24). Resolves the chosen action, or null
/// when dismissed.
Future<ConversationRowAction?> showConversationActionsSheet(
  BuildContext context,
  ServerConversation conversation, {
  bool canSelect = true,
}) {
  final l10n = context.l10n;
  final title = conversation.structured.title.trim();
  return showOmiSheet<ConversationRowAction>(
    context: context,
    title: title.isEmpty ? l10n.untitledConversation : title,
    padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.md),
    builder: (sheetContext) {
      // FontAwesome glyphs, the same ones the conversation page's "…" menu uses for the same actions.
      Widget row(ConversationRowAction action, FaIconData icon, String label, {bool destructive = false}) {
        return OmiSettingsRow(
          key: ValueKey('conversation_action_${action.name}'),
          leading: FaIcon(icon, size: 18),
          title: label,
          showChevron: false,
          isDestructive: destructive,
          onTap: () => Navigator.of(sheetContext).pop(action),
        );
      }

      return SingleChildScrollView(
        child: OmiSettingsGroup(
          children: [
            row(ConversationRowAction.open, FontAwesomeIcons.upRightAndDownLeftFromCenter, l10n.open),
            row(
              ConversationRowAction.star,
              conversation.starred ? FontAwesomeIcons.solidStar : FontAwesomeIcons.star,
              conversation.starred ? l10n.unstarConversation : l10n.starConversation,
            ),
            row(ConversationRowAction.move, FontAwesomeIcons.folder, l10n.moveToFolder),
            row(ConversationRowAction.share, FontAwesomeIcons.arrowUpFromBracket, l10n.share),
            if (CaptureGroupPresentation.recordings(conversation).length > 1) ...[
              row(ConversationRowAction.recordings, FontAwesomeIcons.layerGroup, l10n.recordings),
              row(ConversationRowAction.separate, FontAwesomeIcons.codeBranch, l10n.captureRecordingSeparate),
            ],
            if (canSelect) row(ConversationRowAction.select, FontAwesomeIcons.circleCheck, l10n.selectOption),
            row(ConversationRowAction.delete, FontAwesomeIcons.trashCan, l10n.delete, destructive: true),
          ],
        ),
      );
    },
  );
}

/// Builds the separation controller the row menu uses; tests inject a fake server call.
@visibleForTesting
CaptureGroupSeparationController Function() rowSeparationController = CaptureGroupSeparationController.new;

/// The recordings of a grouped row's event, in the same sheet the conversation page uses: a row opens
/// that recording's conversation; Separate… confirms, separates and reloads the list.
Future<void> showConversationRowRecordings(BuildContext context, ServerConversation conversation) async {
  final recordings = CaptureGroupPresentation.recordings(conversation);
  if (recordings.length < 2) return;
  final list = context.read<ConversationProvider>();
  final controller = rowSeparationController();
  try {
    await showCaptureRecordingsSheet(
      context,
      recordings: recordings,
      controller: controller,
      onOpen: (recording) => _openRowRecording(context, list, recording),
      onSeparate: (recording) => controller.separate(recording.id, reload: () => _reloadConversationList(list)),
    );
  } finally {
    controller.dispose();
  }
}

/// Separate… from a grouped row. With one other recording it asks the page's "Separate this
/// recording?" and separates it; with several, the recordings sheet lets the reader pick which.
Future<void> separateFromConversationRow(BuildContext context, ServerConversation conversation) async {
  final others = CaptureGroupPresentation.recordings(conversation).where((r) => !r.isCurrent).toList();
  if (others.isEmpty) return;
  if (others.length > 1) return showConversationRowRecordings(context, conversation);
  final recording = others.single;
  if (!await confirmCaptureRecordingSeparation(context, recording) || !context.mounted) return;
  final list = context.read<ConversationProvider>();
  final failed = context.l10n.captureRecordingSeparateFailed;
  final controller = rowSeparationController();
  final bool separated;
  try {
    separated = await controller.separate(recording.id, reload: () => _reloadConversationList(list));
  } finally {
    controller.dispose();
  }
  if (!separated && context.mounted) OmiFeedback.error(context, failed);
}

Future<void> _openRowRecording(BuildContext context, ConversationProvider list, CaptureRecording recording) async {
  final target = await CaptureGroupPresentation.resolveMember(
    recording.id,
    loaded: list.conversations.followedBy(list.searchedConversations),
    fetch: getConversationById,
  );
  if (!context.mounted) return;
  if (target == null) {
    OmiFeedback.error(context, context.l10n.captureRecordingOpenFailed);
    return;
  }
  await routeToPage(context, ConversationDetailPage(conversation: target));
}

Future<void> _reloadConversationList(ConversationProvider list) =>
    list.hasActiveSearch ? list.searchConversations(list.previousQuery) : list.forceRefreshConversations();
