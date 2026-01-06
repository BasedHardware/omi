import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/pages/conversations/widgets/create_folder_sheet.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

class FolderTabs extends StatefulWidget {
  final List<Folder> folders;
  final String? selectedFolderId;
  final Function(String?) onFolderSelected;
  final bool showStarredOnly;
  final VoidCallback onStarredToggle;
  final bool showDailySummaries;
  final VoidCallback onDailySummariesToggle;
  final bool hasDailySummaries;

  const FolderTabs({
    super.key,
    required this.folders,
    required this.selectedFolderId,
    required this.onFolderSelected,
    required this.showStarredOnly,
    required this.onStarredToggle,
    required this.showDailySummaries,
    required this.onDailySummariesToggle,
    required this.hasDailySummaries,
  });

  @override
  State<FolderTabs> createState() => _FolderTabsState();
}

class _FolderTabsState extends State<FolderTabs> {
  final ScrollController _scrollController = ScrollController();
  String? _previousSelectedFolderId;
  bool _previousShowStarredOnly = false;
  bool _previousShowDailySummaries = false;

  @override
  void initState() {
    super.initState();
    _previousSelectedFolderId = widget.selectedFolderId;
    _previousShowStarredOnly = widget.showStarredOnly;
    _previousShowDailySummaries = widget.showDailySummaries;
  }

  @override
  void didUpdateWidget(FolderTabs oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Auto-scroll to top when selection changes
    if (widget.selectedFolderId != _previousSelectedFolderId ||
        widget.showStarredOnly != _previousShowStarredOnly ||
        widget.showDailySummaries != _previousShowDailySummaries) {
      _previousSelectedFolderId = widget.selectedFolderId;
      _previousShowStarredOnly = widget.showStarredOnly;
      _previousShowDailySummaries = widget.showDailySummaries;
      _scrollToStart();
    }
  }

  void _scrollToStart() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        0,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  Widget _buildStarredTab() {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: _FolderTab(
        label: 'Starred',
        icon: '⭐',
        color: Colors.amber,
        isSelected: widget.showStarredOnly,
        skipFolderTracking: true,
        onTap: () {
          // Track starred filter toggle with the NEW state (opposite of current)
          MixpanelManager().starredFilterToggled(
            enabled: !widget.showStarredOnly,
            selectedFolderId: widget.selectedFolderId,
          );
          widget.onStarredToggle();
        },
      ),
    );
  }

  Widget _buildDailySummariesTab() {
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: _FolderTab(
        label: 'Recap',
        icon: '🕐',
        color: Colors.green,
        isSelected: widget.showDailySummaries,
        skipFolderTracking: true,
        onTap: () {
          // Track recap tab opened when toggling to true
          if (!widget.showDailySummaries) {
            MixpanelManager().recapTabOpened();
          }
          widget.onDailySummariesToggle();
        },
      ),
    );
  }

  Widget _buildFolderTab(Folder folder) {
    final isSelected = widget.selectedFolderId == folder.id;
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: _FolderTab(
        label: folder.name,
        icon: folder.icon,
        color: folder.colorValue,
        count: folder.conversationCount,
        isSelected: isSelected,
        // If already selected, clicking clears the selection
        onTap: () => widget.onFolderSelected(isSelected ? null : folder.id),
        folder: folder,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Build ordered list of tabs: All, Recap (if available), Starred, folders
    final List<Widget> tabs = [];

    // "All" tab always first - clears all filters when clicked
    tabs.add(_FolderTab(
      label: 'All',
      isSelected: widget.selectedFolderId == null && !widget.showStarredOnly && !widget.showDailySummaries,
      onTap: () {
        // Clear folder filter
        widget.onFolderSelected(null);
        // Clear starred filter if active
        if (widget.showStarredOnly) {
          widget.onStarredToggle();
        }
        // Clear daily summaries filter if active
        if (widget.showDailySummaries) {
          widget.onDailySummariesToggle();
        }
      },
    ));
    tabs.add(const SizedBox(width: 8));

    // Daily Summaries tab second (after All, before Starred) - only show if user has summaries
    if (widget.hasDailySummaries) {
      tabs.add(_buildDailySummariesTab());
    }

    // Starred tab
    tabs.add(_buildStarredTab());

    // If a folder is selected, show it first (after Starred)
    final selectedFolder = widget.selectedFolderId != null
        ? widget.folders.firstWhereOrNull((f) => f.id == widget.selectedFolderId)
        : null;
    if (selectedFolder != null) {
      tabs.add(_buildFolderTab(selectedFolder));
    }

    // Add remaining folders (excluding selected one)
    for (final folder in widget.folders) {
      if (folder.id != widget.selectedFolderId) {
        tabs.add(_buildFolderTab(folder));
      }
    }

    // Extra padding at the end for scroll
    tabs.add(const SizedBox(width: 8));

    return Container(
      height: 36,
      margin: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          // Scrollable folder tabs
          Expanded(
            child: ListView(
              controller: _scrollController,
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.only(left: 16),
              children: tabs,
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
  final bool skipFolderTracking;

  const _FolderTab({
    required this.label,
    this.icon,
    this.color,
    this.count,
    required this.isSelected,
    required this.onTap,
    this.folder,
    this.skipFolderTracking = false,
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
    // Use a visible color for "All" tab (white), otherwise use folder color
    final effectiveColor = color ?? Colors.white;

    return GestureDetector(
      onTap: () {
        // Track folder selection (skip for Starred tab which has its own tracking)
        if (!skipFolderTracking) {
          MixpanelManager().folderSelected(
            folderId: folder?.id,
            folderName: label,
          );
        }
        onTap();
      },
      onLongPress: folder != null ? () => _showContextMenu(context) : null,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? effectiveColor.withValues(alpha: 0.15) : Colors.grey.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: FaIcon(
                  folderIconToFa(icon),
                  size: 12,
                  color: isSelected ? effectiveColor : Colors.grey[400],
                ),
              ),
              const SizedBox(width: 5),
            ],
            Text(
              label,
              style: TextStyle(
                color: isSelected ? effectiveColor : Colors.grey[400],
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                fontSize: 13,
              ),
            ),
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
          width: 32,
          height: 32,
          decoration: BoxDecoration(
            color: Colors.grey.withValues(alpha: 0.12),
            shape: BoxShape.circle,
          ),
          child: Icon(
            Icons.add,
            size: 18,
            color: Colors.grey[400],
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
                  FaIcon(
                    folderIconToFa(folder.icon),
                    size: 18,
                    color: folder.colorValue,
                  ),
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
                        child: FaIcon(
                          folderIconToFa(folder.icon),
                          size: 20,
                          color: Colors.red.withValues(alpha: 0.8),
                        ),
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
                    child: FaIcon(
                      folderIconToFa(icon),
                      size: 18,
                      color: color,
                    ),
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
            Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: FaIcon(
                folderIconToFa(folder.icon),
                size: 10,
                color: folder.colorValue,
              ),
            ),
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
