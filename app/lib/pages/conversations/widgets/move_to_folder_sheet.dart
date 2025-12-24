import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

class MoveToFolderSheet extends StatelessWidget {
  final String conversationId;
  final String? currentFolderId;

  const MoveToFolderSheet({
    super.key,
    required this.conversationId,
    this.currentFolderId,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Consumer<FolderProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
            return const SizedBox(
              height: 200,
              child: Center(
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                ),
              ),
            );
          }

          return Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Move to Folder',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        color: ResponsiveHelper.textPrimary,
                      ),
                    ),
                    GestureDetector(
                      onTap: () => Navigator.pop(context, false),
                      child: const Icon(
                        Icons.close,
                        color: ResponsiveHelper.textTertiary,
                        size: 24,
                      ),
                    ),
                  ],
                ),
              ),

              // Folder list
              if (provider.folders.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(
                    child: Text(
                      'No folders available',
                      style: TextStyle(color: ResponsiveHelper.textTertiary),
                    ),
                  ),
                )
              else
                ConstrainedBox(
                  constraints: BoxConstraints(
                    maxHeight: MediaQuery.of(context).size.height * 0.5,
                  ),
                  child: ListView.builder(
                    shrinkWrap: true,
                    padding: const EdgeInsets.only(bottom: 20),
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
                ),
            ],
          );
        },
      ),
    );
  }

  void _moveToFolder(
    BuildContext context,
    FolderProvider provider,
    String folderId,
  ) {
    HapticFeedback.selectionClick();
    // Close sheet immediately with the folder ID
    Navigator.of(context).pop(folderId);
    // Fire and forget - API call in background
    provider.moveConversation(conversationId, folderId);
  }
}

class _FolderListItem extends StatelessWidget {
  final Folder folder;
  final bool isCurrentFolder;
  final VoidCallback? onTap;

  const _FolderListItem({
    required this.folder,
    required this.isCurrentFolder,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      decoration: BoxDecoration(
        color: isCurrentFolder ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.1) : Colors.transparent,
        borderRadius: BorderRadius.circular(12),
        border: isCurrentFolder
            ? Border.all(color: ResponsiveHelper.purplePrimary, width: 1.5)
            : Border.all(color: ResponsiveHelper.backgroundTertiary, width: 1),
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
                // Folder icon
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    color: folder.colorValue.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Center(
                    child: Text(folder.icon, style: const TextStyle(fontSize: 20)),
                  ),
                ),
                const SizedBox(width: 14),

                // Folder info
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        folder.name,
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: isCurrentFolder ? FontWeight.w600 : FontWeight.w500,
                          color: isCurrentFolder ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textPrimary,
                        ),
                      ),
                      if (folder.description != null && folder.description!.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 3),
                          child: Text(
                            folder.description!,
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

                // Check mark for current folder
                if (isCurrentFolder) const Icon(Icons.check_circle, color: ResponsiveHelper.purplePrimary, size: 22),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Shows the move to folder bottom sheet.
/// Returns the new folder ID if moved, or 'no_folder' if removed from folders, null if cancelled.
Future<String?> showMoveToFolderSheet(
  BuildContext context, {
  required String conversationId,
  String? currentFolderId,
}) async {
  final result = await showModalBottomSheet<String?>(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (context) => MoveToFolderSheet(
      conversationId: conversationId,
      currentFolderId: currentFolderId,
    ),
  );
  return result;
}
