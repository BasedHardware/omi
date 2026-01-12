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
  bool _isSaving = false;
  bool _saveFailed = false;

  @override
  void initState() {
    super.initState();
    _textController = TextEditingController(text: widget.memory?.content ?? '');
    _selectedVisibility = widget.memory?.visibility ?? MemoryVisibility.private;
    _selectedCategory = widget.memory?.category ?? MemoryCategory.manual;
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
                  selected: _selectedCategory == MemoryCategory.system,
                  label: 'About You',
                  icon: Icons.person_outlined,
                  onTap: () => setState(() => _selectedCategory = MemoryCategory.system),
                ),
                const SizedBox(width: 8),
                OmiChoiceChip(
                  selected: _selectedCategory == MemoryCategory.interesting,
                  label: 'Insights',
                  icon: Icons.lightbulb_outlined,
                  onTap: () => setState(() => _selectedCategory = MemoryCategory.interesting),
                ),
                const SizedBox(width: 8),
                OmiChoiceChip(
                  selected: _selectedCategory == MemoryCategory.manual,
                  label: 'Manual',
                  icon: Icons.edit_outlined,
                  onTap: () => setState(() => _selectedCategory = MemoryCategory.manual),
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

            const SizedBox(height: 24),

            // Error message
            if (_saveFailed) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.red.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Colors.red.withOpacity(0.3),
                    width: 1,
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.error_outline,
                      color: Colors.red.shade400,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    const Expanded(
                      child: Text(
                        'Failed to save. Please check your connection.',
                        style: TextStyle(
                          color: ResponsiveHelper.textSecondary,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],

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
                  label: _isSaving
                      ? 'Saving...'
                      : _saveFailed
                          ? 'Retry'
                          : (widget.memory != null ? 'Save Changes' : 'Create Memory'),
                  onPressed: _isSaving ? null : _saveMemory,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _saveMemory() async {
    final content = _textController.text.trim();
    if (content.isEmpty) return;

    setState(() {
      _isSaving = true;
      _saveFailed = false;
    });

    bool success;

    try {
      if (widget.memory != null) {
        // Edit existing memory
        success = await widget.provider.editMemory(widget.memory!, content);
        if (success && widget.memory!.visibility != _selectedVisibility) {
          await widget.provider.updateMemoryVisibility(widget.memory!, _selectedVisibility);
        }
        if (success) {
          MixpanelManager().memoriesPageEditedMemory();
        }
      } else {
        // Create new memory
        success = await widget.provider.createMemory(content, _selectedVisibility, _selectedCategory);
        if (success) {
          MixpanelManager().memoriesPageCreatedMemory(_selectedCategory);
        }
      }
    } catch (e) {
      success = false;
      debugPrint('Error saving memory: $e');
    }

    if (!mounted) return;

    setState(() {
      _isSaving = false;
      _saveFailed = !success;
    });

    if (success) {
      Navigator.pop(context);
    }
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
