import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/string.dart';

class DesktopMemoryItem extends StatelessWidget {
  final Memory memory;
  final MemoriesProvider provider;
  final Function(BuildContext, Memory, MemoriesProvider) onTap;

  const DesktopMemoryItem({
    super.key,
    required this.memory,
    required this.provider,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => onTap(context, memory, provider),
          borderRadius: BorderRadius.circular(16),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                width: 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withOpacity(0.05),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Category icon
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: _getCategoryColor().withOpacity(0.2),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    _getCategoryIcon(),
                    color: _getCategoryColor(),
                    size: 16,
                  ),
                ),

                const SizedBox(width: 12),

                // Memory content
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        memory.content.decodeString,
                        style: const TextStyle(
                          color: ResponsiveHelper.textPrimary,
                          fontSize: 15,
                          height: 1.4,
                        ),
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),

                const SizedBox(width: 12),

                _buildVisibilityIndicator(),

                const SizedBox(width: 8),

                _buildQuickActions(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildVisibilityIndicator() {
    return Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Icon(
        memory.visibility == MemoryVisibility.private ? Icons.lock_outline : Icons.public,
        size: 14,
        color: ResponsiveHelper.textTertiary,
      ),
    );
  }

  Widget _buildQuickActions() {
    return Builder(
      builder: (context) => PopupMenuButton<String>(
        color: ResponsiveHelper.backgroundSecondary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        child: Container(
          padding: const EdgeInsets.all(6),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Icon(
            Icons.more_vert,
            color: ResponsiveHelper.textSecondary,
            size: 16,
          ),
        ),
        itemBuilder: (context) => [
          const PopupMenuItem<String>(
            value: 'edit',
            child: Row(
              children: [
                Icon(
                  Icons.edit_outlined,
                  color: ResponsiveHelper.textSecondary,
                  size: 16,
                ),
                SizedBox(width: 8),
                Text(
                  'Edit',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          PopupMenuItem<String>(
            value: 'visibility',
            child: Row(
              children: [
                Icon(
                  memory.visibility == MemoryVisibility.private ? Icons.public : Icons.lock_outline,
                  color: ResponsiveHelper.textSecondary,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Text(
                  memory.visibility == MemoryVisibility.private ? 'Make Public' : 'Make Private',
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          PopupMenuItem<String>(
            value: 'delete',
            child: Row(
              children: [
                Icon(
                  Icons.delete_outline,
                  color: Colors.red.shade400,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Text(
                  'Delete',
                  style: TextStyle(
                    color: Colors.red.shade400,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
        ],
        onSelected: (value) => _handleMenuSelection(value, context),
      ),
    );
  }

  void _handleMenuSelection(String value, BuildContext context) {
    switch (value) {
      case 'edit':
        onTap(context, memory, provider);
        break;
      case 'visibility':
        final newVisibility = memory.visibility == MemoryVisibility.private ? MemoryVisibility.public : MemoryVisibility.private;
        provider.updateMemoryVisibility(memory, newVisibility);
        MixpanelManager().memoryVisibilityChanged(memory, newVisibility);
        break;
      case 'delete':
        _showDeleteConfirmation(context);
        break;
    }
  }

  void _showDeleteConfirmation(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: ResponsiveHelper.backgroundSecondary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
        title: const Text(
          'Delete Memory',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 18,
            fontWeight: FontWeight.w600,
          ),
        ),
        content: const Text(
          'Are you sure you want to delete this memory? This action cannot be undone.',
          style: TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 14,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text(
              'Cancel',
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
              ),
            ),
          ),
          TextButton(
            onPressed: () {
              provider.deleteMemory(memory);
              MixpanelManager().memoriesPageDeletedMemory(memory);
              Navigator.pop(context);
            },
            child: Text(
              'Delete',
              style: TextStyle(
                color: Colors.red.shade400,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Color _getCategoryColor() {
    switch (memory.category) {
      case MemoryCategory.interesting:
        return ResponsiveHelper.purplePrimary;
      case MemoryCategory.system:
        return Colors.orange;
    }
  }

  IconData _getCategoryIcon() {
    switch (memory.category) {
      case MemoryCategory.interesting:
        return Icons.lightbulb_outline;
      case MemoryCategory.system:
        return Icons.settings_outlined;
    }
  }

}

extension StringCapitalize on String {
  String capitalize() {
    if (isEmpty) return this;
    return this[0].toUpperCase() + substring(1);
  }
}
