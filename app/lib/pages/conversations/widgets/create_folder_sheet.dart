import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/folder.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/folders/folder_icon_mapper.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';

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

/// Available folder icons for selection (uses the shared list from folder_icon_mapper).
const List<String> folderIcons = folderIconStrings;

/// Bottom sheet for creating or editing a folder.
class CreateFolderBottomSheet extends StatefulWidget {
  final Folder? folderToEdit;

  const CreateFolderBottomSheet({super.key, this.folderToEdit});

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

  /// Whether anything differs from what the sheet opened with.
  bool get _isDirty {
    final folder = widget.folderToEdit;
    return _nameController.text.trim() != (folder?.name ?? '') ||
        _descriptionController.text.trim() != (folder?.description ?? '') ||
        _selectedIcon != (folder?.icon ?? folderIcons[0]) ||
        _selectedColor.toARGB32() != (folder?.colorValue ?? folderColors[0]).toARGB32();
  }

  /// A dirty editor asks before it closes (docs/ux-contract.md §2).
  Future<void> _confirmDiscard() async {
    final l10n = context.l10n;
    final discard = await showOmiConfirm(
      context,
      title: l10n.discardChangesTitle,
      message: l10n.discardChangesMessage,
      confirmLabel: l10n.discard,
      cancelLabel: l10n.keepEditing,
      destructive: true,
    );
    if (discard && mounted) Navigator.of(context).pop(false);
  }

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
      OmiFeedback.error(context, context.l10n.pleaseEnterFolderName);
      return;
    }

    setState(() => _isLoading = true);

    try {
      final folderProvider = Provider.of<FolderProvider>(context, listen: false);
      final colorHex = '#${_selectedColor.toARGB32().toRadixString(16).substring(2).toUpperCase()}';

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
          PlatformManager.instance.analytics.folderUpdated(folderId: widget.folderToEdit!.id, folderName: name);
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
          PlatformManager.instance.analytics.folderCreated(
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
        OmiFeedback.error(context, isEditing ? context.l10n.failedToUpdateFolder : context.l10n.failedToCreateFolder);
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  InputDecoration _fieldDecoration(String hint) => InputDecoration(
        filled: true,
        fillColor: OmiColors.surface2,
        border: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        isDense: true,
        hintText: hint,
        hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary),
      );

  @override
  Widget build(BuildContext context) {
    final labelStyle = OmiType.subhead.copyWith(fontWeight: FontWeight.w500, color: OmiColors.textTertiary);
    return PopScope(
      canPop: !_isDirty,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _confirmDiscard();
      },
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SizedBox(height: OmiSpacing.xs),
            TextField(
              controller: _nameController,
              autofocus: true,
              style: OmiType.callout.copyWith(height: 1.3),
              decoration: _fieldDecoration(context.l10n.folderName),
              textCapitalization: TextCapitalization.words,
              maxLength: 30,
              buildCounter: (context, {required currentLength, required isFocused, maxLength}) => null,
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) => _handleSubmit(),
            ),
            const SizedBox(height: OmiSpacing.md),
            TextField(
              controller: _descriptionController,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
              decoration: _fieldDecoration(context.l10n.descriptionOptional),
              maxLines: 2,
              maxLength: 100,
              buildCounter: (context, {required currentLength, required isFocused, maxLength}) => null,
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: OmiSpacing.lg),

            // Icon selection
            Text(context.l10n.icon, style: labelStyle),
            const SizedBox(height: 8),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(children: folderIcons.map((icon) => _buildIconOption(icon)).toList()),
            ),
            const SizedBox(height: OmiSpacing.md),

            // Color selection
            Text(context.l10n.color, style: labelStyle),
            const SizedBox(height: 8),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(children: folderColors.map((color) => _buildColorOption(color)).toList()),
            ),
            const SizedBox(height: OmiSpacing.lg),
            OmiButton(
              key: const Key('create_folder_submit'),
              label: isEditing ? context.l10n.save : context.l10n.create,
              isLoading: _isLoading,
              expand: true,
              onPressed: _isLoading ? null : _handleSubmit,
            ),
            const SizedBox(height: OmiSpacing.md),
          ],
        ),
      ),
    );
  }

  Widget _buildIconOption(String icon) {
    final isSelected = _selectedIcon == icon;
    return Semantics(
      button: true,
      selected: isSelected,
      label: icon,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          HapticFeedback.selectionClick();
          setState(() => _selectedIcon = icon);
        },
        // 40pt tile inside a 44pt target.
        child: Padding(
          padding: const EdgeInsets.fromLTRB(2, 2, 6, 2),
          child: Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: isSelected ? _selectedColor.withValues(alpha: 0.2) : OmiColors.surface2,
              borderRadius: OmiRadius.smAll,
              border: isSelected ? Border.all(color: _selectedColor, width: 1.5) : null,
            ),
            child: Center(
              child: FaIcon(
                folderIconToFa(icon),
                size: 16,
                color: isSelected ? _selectedColor : OmiColors.textSecondary,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildColorOption(Color color) {
    final isSelected = _selectedColor.toARGB32() == color.toARGB32();
    return Semantics(
      button: true,
      selected: isSelected,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          HapticFeedback.selectionClick();
          setState(() => _selectedColor = color);
        },
        // 32pt swatch inside a 44pt target.
        child: Padding(
          padding: const EdgeInsets.fromLTRB(6, 6, 6, 6),
          child: Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              border: Border.all(color: isSelected ? Colors.white : Colors.transparent, width: 2),
            ),
            child: isSelected ? const Icon(Icons.check, color: Colors.white, size: 16) : null,
          ),
        ),
      ),
    );
  }
}

/// Show the create folder bottom sheet.
///
/// An editor: drag-to-dismiss is off so a swipe cannot throw away edits; the X, the scrim and
/// system back ask first when something changed.
Future<bool> showCreateFolderBottomSheet(BuildContext context, {Folder? folderToEdit}) async {
  final result = await showOmiSheet<bool>(
    context: context,
    title: folderToEdit != null ? context.l10n.editFolder : context.l10n.newFolder,
    enableDrag: false,
    builder: (context) => CreateFolderBottomSheet(folderToEdit: folderToEdit),
  );
  return result ?? false;
}
