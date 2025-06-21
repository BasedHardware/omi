import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/ui/atoms/omi_choice_chip.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';

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
                OmiIconButton(
                  icon: Icons.close,
                  onPressed: () => Navigator.pop(context),
                  style: OmiIconButtonStyle.outline,
                  size: 36,
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
                OmiChoiceChip(
                  selected: _selectedCategory == MemoryCategory.interesting,
                  label: 'Interesting',
                  icon: Icons.lightbulb_outline,
                  onTap: () => setState(() => _selectedCategory = MemoryCategory.interesting),
                ),
                const SizedBox(width: 8),
                OmiChoiceChip(
                  selected: _selectedCategory == MemoryCategory.system,
                  label: 'System',
                  icon: Icons.settings_outlined,
                  onTap: () => setState(() => _selectedCategory = MemoryCategory.system),
                ),
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
                Expanded(
                  child: OmiChoiceChip(
                    selected: _selectedVisibility == MemoryVisibility.public,
                    label: 'Public',
                    icon: Icons.public,
                    expand: true,
                    onTap: () => setState(() => _selectedVisibility = MemoryVisibility.public),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OmiChoiceChip(
                    selected: _selectedVisibility == MemoryVisibility.private,
                    label: 'Private',
                    icon: Icons.lock_outline,
                    expand: true,
                    onTap: () => setState(() => _selectedVisibility = MemoryVisibility.private),
                  ),
                ),
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
                OmiButton(
                  label: 'Cancel',
                  onPressed: () => Navigator.pop(context),
                  type: OmiButtonType.text,
                ),
                const SizedBox(width: 12),
                OmiButton(
                  label: widget.memory != null ? 'Save Changes' : 'Create Memory',
                  onPressed: _saveMemory,
                ),
              ],
            ),
          ],
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

    OmiConfirmDialog.show(
      context,
      title: 'Delete Memory',
      message: 'Are you sure you want to delete this memory? This action cannot be undone.',
    ).then((confirmed) {
      if (confirmed == true) {
        widget.provider.deleteMemory(widget.memory!);
        MixpanelManager().memoriesPageDeletedMemory(widget.memory!);
        Navigator.pop(context);
        Navigator.pop(context);
      }
    });
  }
}
