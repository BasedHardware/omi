import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/folder.dart';
import 'package:omi/pages/conversations/widgets/create_folder_sheet.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Edit or delete [folder]: the options sheet that long-pressing a folder opens (search's folder
/// tiles; they were the Conversations folder chips until 2026-09-29).
Future<void> showFolderOptions(BuildContext context, Folder folder) {
  HapticFeedback.mediumImpact();
  PlatformManager.instance.analytics.folderContextMenuOpened(folderId: folder.id, folderName: folder.name);
  return showOmiSheet<void>(context: context, builder: (ctx) => _FolderContextMenu(folder: folder));
}

/// Context menu for folder actions (Edit/Delete).
class _FolderContextMenu extends StatelessWidget {
  final Folder folder;

  const _FolderContextMenu({required this.folder});

  Future<void> _handleEdit(BuildContext context) async {
    // The menu's own context dies with it; open the editor from the navigator's.
    final navigatorContext = Navigator.of(context).context;
    Navigator.pop(context);
    await showCreateFolderBottomSheet(navigatorContext, folderToEdit: folder);
  }

  Future<void> _handleDelete(BuildContext context) async {
    // Capture references before context becomes invalid
    final folderProvider = Provider.of<FolderProvider>(context, listen: false);
    final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);
    final navigatorContext = Navigator.of(context).context;
    final l10n = context.l10n;

    Navigator.pop(context);

    // Show delete folder sheet with move options
    showOmiSheet<void>(
      context: navigatorContext,
      title: l10n.deleteQuoted(folder.name),
      builder: (ctx) => _DeleteFolderSheet(
        folder: folder,
        onDelete: (String? moveToFolderId) {
          Navigator.pop(ctx);

          // Track folder deletion
          PlatformManager.instance.analytics.folderDeleted(
            folderId: folder.id,
            folderName: folder.name,
            conversationCount: folder.conversationCount,
            moveToFolderId: moveToFolderId,
          );

          // Fire and forget - don't wait
          folderProvider.deleteFolder(folder.id, moveToFolderId: moveToFolderId).then((success) {
            if (success) {
              // Refresh conversations to show updated folder contents
              conversationProvider.filterByFolder(moveToFolderId);
            } else {
              if (navigatorContext.mounted) OmiFeedback.error(navigatorContext, l10n.failedToDeleteFolder);
            }
          });
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Folder preview
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(color: folder.colorValue.withValues(alpha: 0.2), borderRadius: OmiRadius.lgAll),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                FaIcon(folderIconToFa(folder.icon), size: 18, color: folder.colorValue),
                const SizedBox(width: 8),
                Text(folder.name,
                    style: OmiType.callout.copyWith(color: folder.colorValue, fontWeight: FontWeight.w600)),
              ],
            ),
          ),
          const SizedBox(height: OmiSpacing.lg),
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                leading: const Icon(Icons.edit_outlined),
                title: context.l10n.editFolder,
                showChevron: false,
                onTap: () => _handleEdit(context),
              ),
              // Delete option (only for non-system folders)
              if (!folder.isSystem)
                OmiSettingsRow(
                  leading: const Icon(Icons.delete_outline),
                  title: context.l10n.deleteFolder,
                  isDestructive: true,
                  showChevron: false,
                  onTap: () => _handleDelete(context),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Sheet for deleting a folder with option to move conversations.
class _DeleteFolderSheet extends StatelessWidget {
  final Folder folder;
  final void Function(String? moveToFolderId) onDelete;

  const _DeleteFolderSheet({required this.folder, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    return Consumer<FolderProvider>(
      builder: (context, provider, _) {
        final otherFolders = provider.folders.where((f) => f.id != folder.id).toList();

        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              context.l10n.moveConversationsTo(folder.conversationCount),
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
            ),
            const SizedBox(height: OmiSpacing.xs),
            // Folder options
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.4),
              child: ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.only(bottom: OmiSpacing.md),
                children: [
                  // No folder option
                  _MoveOption(
                    icon: '🚫',
                    name: context.l10n.noFolder,
                    description: context.l10n.removeFromAllFolders,
                    color: OmiColors.textTertiary,
                    onTap: () => onDelete(null),
                  ),

                  // Other folders
                  ...otherFolders.map(
                    (f) => _MoveOption(
                      icon: f.icon,
                      name: f.name,
                      description: f.description,
                      color: f.colorValue,
                      onTap: () => onDelete(f.id),
                    ),
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

class _MoveOption extends StatelessWidget {
  final String icon;
  final String name;
  final String? description;
  final Color color;
  final VoidCallback onTap;

  const _MoveOption({
    required this.icon,
    required this.name,
    this.description,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      decoration: BoxDecoration(
        color: OmiColors.surface3,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: OmiColors.surface3, width: 1),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Center(child: FaIcon(folderIconToFa(icon), size: 18, color: color)),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w500,
                          color: OmiColors.textPrimary,
                        ),
                      ),
                      if (description != null && description!.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 3),
                          child: Tooltip(
                            message: description!,
                            child: Text(
                              description!,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(fontSize: 12, color: OmiColors.textTertiary),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
