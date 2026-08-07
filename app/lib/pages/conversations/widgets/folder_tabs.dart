import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/backend/schema/folder.dart';
import 'package:omi/pages/conversations/widgets/create_folder_sheet.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// The conversations filter row: one dropdown carrying All / Starred / every
/// folder, plus the search toggle.
///
/// This used to be a horizontally scrolling chip rail. With more than a couple
/// of folders the active one could sit off screen, so the row failed at the one
/// job it had — telling you what you are looking at.
class FolderTabs extends StatefulWidget {
  final List<Folder> folders;
  final String? selectedFolderId;
  final Function(String?) onFolderSelected;
  final bool showStarredOnly;
  final VoidCallback onStarredToggle;

  const FolderTabs({
    super.key,
    required this.folders,
    required this.selectedFolderId,
    required this.onFolderSelected,
    required this.showStarredOnly,
    required this.onStarredToggle,
  });

  @override
  State<FolderTabs> createState() => _FolderTabsState();
}

class _FolderTabsState extends State<FolderTabs> {
  Folder? get _selectedFolder =>
      widget.selectedFolderId == null ? null : widget.folders.firstWhereOrNull((f) => f.id == widget.selectedFolderId);

  /// What the button reads. Starred wins over a folder because toggling it
  /// clears the folder filter.
  String get _label {
    if (widget.showStarredOnly) return context.l10n.starred;
    return _selectedFolder?.name ?? context.l10n.all;
  }

  void _selectAll() {
    widget.onFolderSelected(null);
    if (widget.showStarredOnly) widget.onStarredToggle();
  }

  void _selectStarred() {
    PlatformManager.instance.analytics.starredFilterToggled(
      enabled: !widget.showStarredOnly,
      selectedFolderId: widget.selectedFolderId,
    );
    if (!widget.showStarredOnly) widget.onStarredToggle();
  }

  void _selectFolder(Folder folder) {
    PlatformManager.instance.analytics.folderSelected(folderId: folder.id, folderName: folder.name);
    if (widget.showStarredOnly) widget.onStarredToggle();
    widget.onFolderSelected(folder.id);
  }

  /// Edit/delete lived on a long-press of the folder's chip. The chips are gone,
  /// so the menu carries the actions for whichever folder is selected.
  void _showFolderActions(Folder folder) {
    HapticFeedback.mediumImpact();
    PlatformManager.instance.analytics.folderContextMenuOpened(folderId: folder.id, folderName: folder.name);
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1F1F25),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => _FolderContextMenu(folder: folder),
    );
  }

  @override
  Widget build(BuildContext context) {
    final selectedFolder = _selectedFolder;

    return Container(
      height: 36,
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          PullDownButton(
            itemBuilder: (context) => [
              PullDownMenuItem.selectable(
                title: context.l10n.all,
                selected: !widget.showStarredOnly && widget.selectedFolderId == null,
                onTap: _selectAll,
              ),
              PullDownMenuItem.selectable(
                title: context.l10n.starred,
                selected: widget.showStarredOnly,
                iconWidget: const FaIcon(FontAwesomeIcons.solidStar, size: 14, color: Colors.amber),
                onTap: _selectStarred,
              ),
              if (widget.folders.isNotEmpty) const PullDownMenuDivider.large(),
              ...widget.folders.map(
                (folder) => PullDownMenuItem.selectable(
                  title: folder.name,
                  selected: !widget.showStarredOnly && widget.selectedFolderId == folder.id,
                  iconWidget: FaIcon(folderIconToFa(folder.icon), size: 14, color: folder.colorValue),
                  onTap: () => _selectFolder(folder),
                ),
              ),
              const PullDownMenuDivider.large(),
              if (selectedFolder != null)
                PullDownMenuItem(
                  title: context.l10n.editFolder,
                  iconWidget: const Icon(Icons.edit_outlined, size: 18),
                  onTap: () => _showFolderActions(selectedFolder),
                ),
              PullDownMenuItem(
                title: context.l10n.newFolder,
                iconWidget: const Icon(Icons.add, size: 18),
                onTap: () async {
                  HapticFeedback.mediumImpact();
                  PlatformManager.instance.analytics.createFolderButtonClicked();
                  await showCreateFolderBottomSheet(context);
                },
              ),
            ],
            buttonBuilder: (context, showMenu) => GestureDetector(
              onTap: () {
                HapticFeedback.mediumImpact();
                showMenu();
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14),
                decoration: BoxDecoration(
                  color: Colors.grey.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (widget.showStarredOnly)
                      const Padding(
                        padding: EdgeInsets.only(right: 6),
                        child: FaIcon(FontAwesomeIcons.solidStar, size: 12, color: Colors.amber),
                      )
                    else if (selectedFolder != null)
                      Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: FaIcon(folderIconToFa(selectedFolder.icon), size: 12, color: selectedFolder.colorValue),
                      ),
                    Text(
                      _label,
                      style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(width: 4),
                    Icon(Icons.keyboard_arrow_down, size: 18, color: Colors.grey[400]),
                  ],
                ),
              ),
            ),
          ),
          const Spacer(),
          _SearchButton(),
        ],
      ),
    );
  }
}

/// Search toggle, sitting inline with the filter dropdown rather than in the
/// shared home app bar.
class _SearchButton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer2<HomeProvider, ConversationProvider>(
      builder: (context, homeProvider, convoProvider, _) {
        // Same rule the app-bar button used: while a query is active the search
        // field itself is on screen, so the toggle stays hidden.
        if (convoProvider.previousQuery.isNotEmpty) return const SizedBox.shrink();
        final isActive = homeProvider.showConvoSearchBar;
        return Padding(
          padding: const EdgeInsets.only(left: 8),
          child: GestureDetector(
            onTap: () {
              HapticFeedback.mediumImpact();
              homeProvider.toggleConvoSearchBar();
            },
            child: Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: isActive ? Colors.white.withValues(alpha: 0.18) : Colors.grey.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.search, size: 18, color: isActive ? Colors.white : Colors.grey[400]),
            ),
          ),
        );
      },
    );
  }
}

/// Context menu for folder actions (Edit/Delete).
class _FolderContextMenu extends StatelessWidget {
  final Folder folder;

  const _FolderContextMenu({required this.folder});

  Future<void> _handleEdit(BuildContext context) async {
    Navigator.pop(context);
    await showCreateFolderBottomSheet(context, folderToEdit: folder);
  }

  Future<void> _handleDelete(BuildContext context) async {
    // Capture references before context becomes invalid
    final folderProvider = Provider.of<FolderProvider>(context, listen: false);
    final conversationProvider = Provider.of<ConversationProvider>(context, listen: false);
    final scaffoldMessenger = ScaffoldMessenger.of(context);
    final l10n = context.l10n;

    Navigator.pop(context);

    // Show delete folder sheet with move options
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
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
              scaffoldMessenger.showSnackBar(SnackBar(content: Text(l10n.failedToDeleteFolder)));
            }
          });
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Handle bar
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(color: Colors.grey[600], borderRadius: BorderRadius.circular(2)),
            ),
            const SizedBox(height: 16),

            // Folder preview
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: folder.colorValue.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  FaIcon(folderIconToFa(folder.icon), size: 18, color: folder.colorValue),
                  const SizedBox(width: 8),
                  Text(
                    folder.name,
                    style: TextStyle(color: folder.colorValue, fontWeight: FontWeight.w600, fontSize: 16),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // Edit option
            ListTile(
              leading: const Icon(Icons.edit_outlined, color: Colors.white),
              title: Text(context.l10n.editFolder, style: const TextStyle(color: Colors.white)),
              onTap: () => _handleEdit(context),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),

            // Delete option (only for non-system folders)
            if (!folder.isSystem)
              ListTile(
                leading: const Icon(Icons.delete_outline, color: Colors.red),
                title: Text(context.l10n.deleteFolder, style: const TextStyle(color: Colors.red)),
                onTap: () => _handleDelete(context),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),

            // Cancel
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text(context.l10n.cancel, style: const TextStyle(color: Colors.grey, fontSize: 16)),
              ),
            ),
          ],
        ),
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
    return Container(
      decoration: const BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Consumer<FolderProvider>(
        builder: (context, provider, _) {
          final otherFolders = provider.folders.where((f) => f.id != folder.id).toList();

          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
                child: Row(
                  children: [
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: Colors.red.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Center(
                        child: FaIcon(folderIconToFa(folder.icon), size: 20, color: Colors.red.withValues(alpha: 0.8)),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            context.l10n.deleteQuoted(folder.name),
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w600,
                              color: ResponsiveHelper.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            context.l10n.moveConversationsTo(folder.conversationCount),
                            style: const TextStyle(fontSize: 13, color: ResponsiveHelper.textTertiary),
                          ),
                        ],
                      ),
                    ),
                    GestureDetector(
                      onTap: () => Navigator.pop(context),
                      child: const Icon(Icons.close, color: ResponsiveHelper.textTertiary, size: 24),
                    ),
                  ],
                ),
              ),

              // Folder options
              ConstrainedBox(
                constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.4),
                child: ListView(
                  shrinkWrap: true,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  children: [
                    // No folder option
                    _MoveOption(
                      icon: '🚫',
                      name: context.l10n.noFolder,
                      description: context.l10n.removeFromAllFolders,
                      color: Colors.grey,
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

              // Bottom padding
              const SizedBox(height: 16),
            ],
          );
        },
      ),
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
        color: ResponsiveHelper.backgroundTertiary,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: ResponsiveHelper.backgroundTertiary, width: 1),
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
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w500,
                          color: ResponsiveHelper.textPrimary,
                        ),
                      ),
                      if (description != null && description!.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 3),
                          child: Text(
                            description!,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 12, color: ResponsiveHelper.textTertiary),
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
