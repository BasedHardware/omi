import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/folder.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The folder picker inside the Move to Folder sheet. Pops the chosen folder id.
///
/// With [conversationId] it also moves that conversation (fire and forget, as before); without
/// one it only picks, and the caller moves (the selection bar's bulk move).
class MoveToFolderSheet extends StatelessWidget {
  final String? conversationId;
  final String? currentFolderId;

  const MoveToFolderSheet({super.key, this.conversationId, this.currentFolderId});

  @override
  Widget build(BuildContext context) {
    return Consumer<FolderProvider>(
      builder: (context, provider, child) {
        if (provider.isLoading) {
          return const SizedBox(height: 200, child: OmiLoadingState());
        }
        if (provider.folders.isEmpty) {
          return Padding(
            padding: const EdgeInsets.only(bottom: OmiSpacing.lg),
            child: OmiEmptyState(icon: Icons.folder_outlined, title: context.l10n.noFoldersAvailable),
          );
        }
        return ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.5),
          child: ListView.builder(
            shrinkWrap: true,
            padding: const EdgeInsets.only(top: OmiSpacing.xxs, bottom: OmiSpacing.md),
            itemCount: provider.folders.length,
            itemBuilder: (context, index) {
              final folder = provider.folders[index];
              final isCurrentFolder = folder.id == currentFolderId;
              return _FolderListItem(
                folder: folder,
                isCurrentFolder: isCurrentFolder,
                onTap: isCurrentFolder ? null : () => _moveToFolder(context, provider, folder.id),
              );
            },
          ),
        );
      },
    );
  }

  void _moveToFolder(BuildContext context, FolderProvider provider, String folderId) {
    HapticFeedback.selectionClick();
    // Close sheet immediately with the folder ID
    Navigator.of(context).pop(folderId);
    // Fire and forget - API call in background
    final id = conversationId;
    if (id != null) provider.moveConversation(id, folderId);
  }
}

class _FolderListItem extends StatelessWidget {
  final Folder folder;
  final bool isCurrentFolder;
  final VoidCallback? onTap;

  const _FolderListItem({required this.folder, required this.isCurrentFolder, this.onTap});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xxs),
      child: Semantics(
        selected: isCurrentFolder,
        button: onTap != null,
        child: Material(
          color: isCurrentFolder ? OmiColors.surface2 : Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: OmiRadius.mdAll,
            side: BorderSide(color: isCurrentFolder ? OmiColors.accent : OmiColors.border),
          ),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.sm),
              child: Row(
                children: [
                  Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: folder.colorValue.withValues(alpha: 0.15),
                      borderRadius: OmiRadius.smAll,
                    ),
                    child: Center(child: FaIcon(folderIconToFa(folder.icon), size: 18, color: folder.colorValue)),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          folder.name,
                          style: OmiType.subhead.copyWith(
                            fontWeight: isCurrentFolder ? FontWeight.w600 : FontWeight.w500,
                          ),
                        ),
                        if (folder.description != null && folder.description!.isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 3),
                            child: Text(
                              folder.description!,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                            ),
                          ),
                      ],
                    ),
                  ),
                  if (isCurrentFolder)
                    const ExcludeSemantics(child: Icon(Icons.check_circle, color: OmiColors.accent, size: 22)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Shows the Move to Folder sheet for one conversation and moves it.
/// Returns the new folder ID if moved, null if dismissed.
Future<String?> showMoveToFolderSheet(
  BuildContext context, {
  required String conversationId,
  String? currentFolderId,
}) {
  return showOmiSheet<String?>(
    context: context,
    title: context.l10n.moveToFolder,
    useRootNavigator: true,
    builder: (context) => MoveToFolderSheet(conversationId: conversationId, currentFolderId: currentFolderId),
  );
}

/// Shows the Move to Folder sheet for [count] selected conversations and returns the picked folder
/// ID (the caller moves them), or null if dismissed.
Future<String?> showMoveConversationsToFolderSheet(BuildContext context, {required int count}) {
  return showOmiSheet<String?>(
    context: context,
    title: context.l10n.moveConversationsTo(count),
    useRootNavigator: true,
    builder: (context) => const MoveToFolderSheet(),
  );
}
