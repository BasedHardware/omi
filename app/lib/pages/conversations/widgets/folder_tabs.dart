import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/pages/conversations/widgets/create_folder_sheet.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

class FolderTabs extends StatelessWidget {
  final List<Folder> folders;
  final String? selectedFolderId;
  final Function(String?) onFolderSelected;

  const FolderTabs({
    super.key,
    required this.folders,
    required this.selectedFolderId,
    required this.onFolderSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 44,
      margin: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          // Scrollable folder tabs
          Expanded(
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.only(left: 16),
              children: [
                // "All" tab
                _FolderTab(
                  label: 'All',
                  isSelected: selectedFolderId == null,
                  onTap: () => onFolderSelected(null),
                ),
                const SizedBox(width: 8),
                // Folder tabs
                ...folders.map((folder) => Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: _FolderTab(
                        label: folder.name,
                        icon: folder.icon,
                        color: folder.colorValue,
                        count: folder.conversationCount,
                        isSelected: selectedFolderId == folder.id,
                        onTap: () => onFolderSelected(folder.id),
                        folder: folder,
                      ),
                    )),
                // Extra padding at the end for scroll
                const SizedBox(width: 8),
              ],
            ),
          ),
          // Fixed add button
          _AddFolderButton(),
        ],
      ),
    );
  }
}

/// Individual folder tab with long-press context menu.
class _FolderTab extends StatelessWidget {
  final String label;
  final String? icon;
  final Color? color;
  final int? count;
  final bool isSelected;
  final VoidCallback onTap;
  final Folder? folder;

  const _FolderTab({
    required this.label,
    this.icon,
    this.color,
    this.count,
    required this.isSelected,
    required this.onTap,
    this.folder,
  });

  void _showContextMenu(BuildContext context) {
    if (folder == null) return; // No context menu for "All" tab

    HapticFeedback.mediumImpact();

    // Track context menu opened
    MixpanelManager().folderContextMenuOpened(
      folderId: folder!.id,
      folderName: folder!.name,
    );

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1F1F25),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => _FolderContextMenu(folder: folder!),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Use a visible color for "All" tab (white), otherwise use folder color
    final effectiveColor = color ?? Colors.white;

    return GestureDetector(
      onTap: () {
        // Track folder selection
        MixpanelManager().folderSelected(
          folderId: folder?.id,
          folderName: label,
        );
        onTap();
      },
      onLongPress: folder != null ? () => _showContextMenu(context) : null,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? effectiveColor.withValues(alpha: 0.15) : theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? effectiveColor : Colors.grey.withValues(alpha: 0.3),
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Text(icon!, style: const TextStyle(fontSize: 16)),
              const SizedBox(width: 6),
            ],
            Text(
              label,
              style: TextStyle(
                color: isSelected ? effectiveColor : theme.textTheme.bodyMedium?.color,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                fontSize: 14,
              ),
            ),
            if (count != null && count! > 0) ...[
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: isSelected ? effectiveColor.withValues(alpha: 0.3) : Colors.grey.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  count! > 99 ? '99+' : count.toString(),
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                    color: isSelected ? effectiveColor : Colors.grey[600],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Fixed add folder button on the right side.
class _AddFolderButton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(left: 8, right: 16),
      child: GestureDetector(
        onTap: () async {
          HapticFeedback.mediumImpact();
          MixpanelManager().createFolderButtonClicked();
          await showCreateFolderBottomSheet(context);
        },
        child: Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: Colors.grey.withValues(alpha: 0.15),
            shape: BoxShape.circle,
            border: Border.all(
              color: Colors.grey.withValues(alpha: 0.3),
            ),
          ),
          child: const Icon(
            Icons.add,
            size: 20,
            color: Colors.grey,
          ),
        ),
      ),
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
          MixpanelManager().folderDeleted(
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
              scaffoldMessenger.showSnackBar(
                const SnackBar(content: Text('Failed to delete folder')),
              );
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
              decoration: BoxDecoration(
                color: Colors.grey[600],
                borderRadius: BorderRadius.circular(2),
              ),
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
                  Text(folder.icon, style: const TextStyle(fontSize: 20)),
                  const SizedBox(width: 8),
                  Text(
                    folder.name,
                    style: TextStyle(
                      color: folder.colorValue,
                      fontWeight: FontWeight.w600,
                      fontSize: 16,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),

            // Edit option
            ListTile(
              leading: const Icon(Icons.edit_outlined, color: Colors.white),
              title: const Text('Edit Folder', style: TextStyle(color: Colors.white)),
              onTap: () => _handleEdit(context),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),

            // Delete option (only for non-system folders)
            if (!folder.isSystem)
              ListTile(
                leading: const Icon(Icons.delete_outline, color: Colors.red),
                title: const Text('Delete Folder', style: TextStyle(color: Colors.red)),
                onTap: () => _handleDelete(context),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),

            // Cancel
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text(
                  'Cancel',
                  style: TextStyle(color: Colors.grey, fontSize: 16),
                ),
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

  const _DeleteFolderSheet({
    required this.folder,
    required this.onDelete,
  });

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
                        child: Text(folder.icon, style: const TextStyle(fontSize: 22)),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Delete "${folder.name}"',
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w600,
                              color: ResponsiveHelper.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Move ${folder.conversationCount} conversations to:',
                            style: const TextStyle(
                              fontSize: 13,
                              color: ResponsiveHelper.textTertiary,
                            ),
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
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.of(context).size.height * 0.4,
                ),
                child: ListView(
                  shrinkWrap: true,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  children: [
                    // No folder option
                    _MoveOption(
                      icon: '🚫',
                      name: 'No folder',
                      description: 'Remove from all folders',
                      color: Colors.grey,
                      onTap: () => onDelete(null),
                    ),

                    // Other folders
                    ...otherFolders.map((f) => _MoveOption(
                          icon: f.icon,
                          name: f.name,
                          description: f.description,
                          color: f.colorValue,
                          onTap: () => onDelete(f.id),
                        )),
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
                  child: Center(
                    child: Text(icon, style: const TextStyle(fontSize: 20)),
                  ),
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
                            style: const TextStyle(
                              fontSize: 12,
                              color: ResponsiveHelper.textTertiary,
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

class FolderChip extends StatelessWidget {
  final Folder folder;
  final VoidCallback? onTap;

  const FolderChip({
    super.key,
    required this.folder,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: folder.colorValue.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(folder.icon, style: const TextStyle(fontSize: 12)),
            const SizedBox(width: 4),
            Text(
              folder.name,
              style: TextStyle(
                fontSize: 11,
                color: folder.colorValue,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
