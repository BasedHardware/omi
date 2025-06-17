import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

class DesktopMemoryDialog extends StatefulWidget {
  final Memory? memory;
  final MemoriesProvider provider;

  const DesktopMemoryDialog({
    super.key,
    this.memory,
    required this.provider,
  });

  @override
  State<DesktopMemoryDialog> createState() => _DesktopMemoryDialogState();
}

class _DesktopMemoryDialogState extends State<DesktopMemoryDialog> {
  late TextEditingController _textController;
  late MemoryVisibility _selectedVisibility;
  late MemoryCategory _selectedCategory;

  @override
  void initState() {
    super.initState();
    _textController = TextEditingController(text: widget.memory?.content ?? '');
    _selectedVisibility = widget.memory?.visibility ?? MemoryVisibility.public;
    _selectedCategory = widget.memory?.category ?? MemoryCategory.interesting;
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 480,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.2),
              blurRadius: 30,
              offset: const Offset(0, 15),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Row(
              children: [
                Text(
                  widget.memory != null ? '✏️ Edit Memory' : '✨ New Memory',
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const Spacer(),
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(
                    Icons.close,
                    color: ResponsiveHelper.textSecondary,
                    size: 20,
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),

            // Content input
            Container(
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                  width: 1,
                ),
              ),
              child: TextField(
                controller: _textController,
                maxLines: 6,
                autofocus: true,
                style: const TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 15,
                  height: 1.4,
                ),
                decoration: const InputDecoration(
                  hintText: 'What would you like to remember?',
                  hintStyle: TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 15,
                  ),
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.all(16),
                ),
              ),
            ),

            const SizedBox(height: 20),

            // Category selection
            const Text(
              'Category',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                _buildCategoryChip(MemoryCategory.interesting, 'Interesting', Icons.lightbulb_outline),
                const SizedBox(width: 8),
                _buildCategoryChip(MemoryCategory.system, 'System', Icons.settings_outlined),
              ],
            ),

            const SizedBox(height: 20),

            // Visibility selection
            const Text(
              'Visibility',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                _buildVisibilityChip(MemoryVisibility.public, 'Public', Icons.public, 'Will be used for personas'),
                const SizedBox(width: 8),
                _buildVisibilityChip(MemoryVisibility.private, 'Private', Icons.lock_outline, 'Will not be used'),
              ],
            ),

            const SizedBox(height: 32),

            // Actions
            Row(
              children: [
                if (widget.memory != null) ...[
                  TextButton.icon(
                    onPressed: _showDeleteConfirmation,
                    icon: Icon(
                      Icons.delete_outline,
                      color: Colors.red.shade400,
                      size: 18,
                    ),
                    label: Text(
                      'Delete',
                      style: TextStyle(
                        color: Colors.red.shade400,
                        fontSize: 14,
                      ),
                    ),
                  ),
                ],
                const Spacer(),
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text(
                    'Cancel',
                    style: TextStyle(
                      color: ResponsiveHelper.textSecondary,
                      fontSize: 14,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: _saveMemory,
                    borderRadius: BorderRadius.circular(12),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.purplePrimary,
                        borderRadius: BorderRadius.circular(12),
                        boxShadow: [
                          BoxShadow(
                            color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                            blurRadius: 8,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: Text(
                        widget.memory != null ? 'Save Changes' : 'Create Memory',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCategoryChip(MemoryCategory category, String label, IconData icon) {
    final isSelected = _selectedCategory == category;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => setState(() => _selectedCategory = category),
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: isSelected ? ResponsiveHelper.purplePrimary.withOpacity(0.2) : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                size: 16,
                color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
              ),
              const SizedBox(width: 6),
              Text(
                label,
                style: TextStyle(
                  color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                  fontSize: 12,
                  fontWeight: isSelected ? FontWeight.w500 : FontWeight.w400,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildVisibilityChip(MemoryVisibility visibility, String label, IconData icon, String subtitle) {
    final isSelected = _selectedVisibility == visibility;
    return Expanded(
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => setState(() => _selectedVisibility = visibility),
          borderRadius: BorderRadius.circular(8),
          child: Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: isSelected ? ResponsiveHelper.purplePrimary.withOpacity(0.2) : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                width: 1,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      icon,
                      size: 16,
                      color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      label,
                      style: TextStyle(
                        color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                        fontSize: 12,
                        fontWeight: isSelected ? FontWeight.w500 : FontWeight.w400,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: const TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 10,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _saveMemory() {
    final content = _textController.text.trim();
    if (content.isEmpty) return;

    if (widget.memory != null) {
      // Edit existing memory
      widget.provider.editMemory(widget.memory!, content);
      if (widget.memory!.visibility != _selectedVisibility) {
        widget.provider.updateMemoryVisibility(widget.memory!, _selectedVisibility);
      }
      MixpanelManager().memoriesPageEditedMemory();
    } else {
      // Create new memory
      widget.provider.createMemory(content, _selectedVisibility, _selectedCategory);
      MixpanelManager().memoriesPageCreatedMemory(_selectedCategory);
    }

    Navigator.pop(context);
  }

  void _showDeleteConfirmation() {
    if (widget.memory == null) return;

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
              widget.provider.deleteMemory(widget.memory!);
              MixpanelManager().memoriesPageDeletedMemory(widget.memory!);
              Navigator.pop(context);
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
}
