import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

/// Available folder colors for selection.
const List<Color> folderColors = [
  Color(0xFF3B82F6), // Blue
  Color(0xFFEF4444), // Red
  Color(0xFF10B981), // Green
  Color(0xFF8B5CF6), // Purple
  Color(0xFFF59E0B), // Amber
  Color(0xFF06B6D4), // Cyan
  Color(0xFFEC4899), // Pink
  Color(0xFF6366F1), // Indigo
  Color(0xFFF97316), // Orange
  Color(0xFF6B7280), // Gray
];

/// Available folder icons for selection.
const List<String> folderIcons = [
  '📁',
  '💼',
  '🏠',
  '📚',
  '👨‍👩‍👧‍👦',
  '❤️',
  '🎮',
  '✈️',
  '🏥',
  '🛒',
  '💰',
  '🎵',
  '🎨',
  '📝',
  '💬',
  '🌎',
  '🛠️',
  '🍔',
  '🏆',
  '🔒',
];

/// Bottom sheet for creating or editing a folder.
class CreateFolderBottomSheet extends StatefulWidget {
  final Folder? folderToEdit;

  const CreateFolderBottomSheet({
    super.key,
    this.folderToEdit,
  });

  @override
  State<CreateFolderBottomSheet> createState() => _CreateFolderBottomSheetState();
}

class _CreateFolderBottomSheetState extends State<CreateFolderBottomSheet> {
  late TextEditingController _nameController;
  late TextEditingController _descriptionController;
  Color _selectedColor = folderColors[0];
  String _selectedIcon = folderIcons[0];
  bool _isLoading = false;

  bool get isEditing => widget.folderToEdit != null;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.folderToEdit?.name ?? '');
    _descriptionController = TextEditingController(text: widget.folderToEdit?.description ?? '');

    if (widget.folderToEdit != null) {
      _selectedColor = widget.folderToEdit!.colorValue;
      _selectedIcon = widget.folderToEdit!.icon;
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _descriptionController.dispose();
    super.dispose();
  }

  Future<void> _handleSubmit() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please enter a folder name'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    setState(() => _isLoading = true);

    try {
      final folderProvider = Provider.of<FolderProvider>(context, listen: false);
      final colorHex = '#${_selectedColor.value.toRadixString(16).substring(2).toUpperCase()}';

      bool success;
      if (isEditing) {
        final result = await folderProvider.updateFolder(
          widget.folderToEdit!.id,
          name: name,
          description: _descriptionController.text.trim().isEmpty ? null : _descriptionController.text.trim(),
          color: colorHex,
          icon: _selectedIcon,
        );
        success = result != null;

        if (success) {
          MixpanelManager().folderUpdated(
            folderId: widget.folderToEdit!.id,
            folderName: name,
          );
        }
      } else {
        final result = await folderProvider.createFolder(
          name: name,
          description: _descriptionController.text.trim().isEmpty ? null : _descriptionController.text.trim(),
          color: colorHex,
          icon: _selectedIcon,
        );
        success = result != null;

        if (result != null) {
          MixpanelManager().folderCreated(
            folderId: result.id,
            folderName: name,
            icon: _selectedIcon,
            color: colorHex,
          );
        }
      }

      if (success && mounted) {
        Navigator.pop(context, true);
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to ${isEditing ? 'update' : 'create'} folder'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        decoration: const BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header with title and save button
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  isEditing ? 'Edit Folder' : 'New Folder',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                    color: ResponsiveHelper.textPrimary,
                  ),
                ),
                TextButton(
                  onPressed: _isLoading ? null : _handleSubmit,
                  child: _isLoading
                      ? const SizedBox(
                          height: 16,
                          width: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation<Color>(
                              ResponsiveHelper.purplePrimary,
                            ),
                          ),
                        )
                      : Text(
                          isEditing ? 'Save' : 'Create',
                          style: const TextStyle(
                            color: ResponsiveHelper.purplePrimary,
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Name input with background
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary,
                borderRadius: BorderRadius.circular(12),
              ),
              child: TextField(
                controller: _nameController,
                autofocus: true,
                style: const TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 16,
                  height: 1.3,
                ),
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.zero,
                  isDense: true,
                  hintText: 'Folder name',
                  hintStyle: TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 16,
                  ),
                ),
                textCapitalization: TextCapitalization.words,
                maxLength: 30,
                buildCounter: (context, {required currentLength, required isFocused, maxLength}) => null,
                onSubmitted: (_) => _handleSubmit(),
              ),
            ),
            const SizedBox(height: 16),

            // Description input with background
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary,
                borderRadius: BorderRadius.circular(12),
              ),
              child: TextField(
                controller: _descriptionController,
                style: const TextStyle(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 14,
                  height: 1.4,
                ),
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.zero,
                  isDense: true,
                  hintText: 'Description (optional)',
                  hintStyle: TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 14,
                  ),
                ),
                maxLines: 2,
                maxLength: 100,
                buildCounter: (context, {required currentLength, required isFocused, maxLength}) => null,
              ),
            ),
            const SizedBox(height: 20),

            // Icon selection
            const Text(
              'Icon',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: ResponsiveHelper.textTertiary,
              ),
            ),
            const SizedBox(height: 8),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: folderIcons.map((icon) => _buildIconOption(icon)).toList(),
              ),
            ),
            const SizedBox(height: 16),

            // Color selection
            const Text(
              'Color',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: ResponsiveHelper.textTertiary,
              ),
            ),
            const SizedBox(height: 8),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: folderColors.map((color) => _buildColorOption(color)).toList(),
              ),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }

  Widget _buildIconOption(String icon) {
    final isSelected = _selectedIcon == icon;
    return GestureDetector(
      onTap: () {
        HapticFeedback.selectionClick();
        setState(() => _selectedIcon = icon);
      },
      child: Container(
        width: 40,
        height: 40,
        margin: const EdgeInsets.only(right: 8),
        decoration: BoxDecoration(
          color: isSelected ? _selectedColor.withOpacity(0.2) : ResponsiveHelper.backgroundTertiary,
          borderRadius: BorderRadius.circular(10),
          border: isSelected ? Border.all(color: _selectedColor, width: 1.5) : null,
        ),
        child: Center(
          child: Text(icon, style: const TextStyle(fontSize: 18)),
        ),
      ),
    );
  }

  Widget _buildColorOption(Color color) {
    final isSelected = _selectedColor.value == color.value;
    return GestureDetector(
      onTap: () {
        HapticFeedback.selectionClick();
        setState(() => _selectedColor = color);
      },
      child: Container(
        width: 32,
        height: 32,
        margin: const EdgeInsets.only(right: 10),
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(
            color: isSelected ? Colors.white : Colors.transparent,
            width: 2,
          ),
        ),
        child: isSelected ? const Icon(Icons.check, color: Colors.white, size: 16) : null,
      ),
    );
  }
}

/// Show the create folder bottom sheet.
Future<bool> showCreateFolderBottomSheet(BuildContext context, {Folder? folderToEdit}) async {
  final result = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (context) => CreateFolderBottomSheet(folderToEdit: folderToEdit),
  );
  return result ?? false;
}
