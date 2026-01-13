import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

import 'delete_confirmation.dart';
import 'package:omi/utils/l10n_extensions.dart';

class MemoryDialog extends StatefulWidget {
  final MemoriesProvider provider;
  final Memory? memory;

  const MemoryDialog({
    super.key,
    required this.provider,
    this.memory,
  });

  @override
  State<MemoryDialog> createState() => _MemoryDialogState();
}

class _MemoryDialogState extends State<MemoryDialog> {
  late TextEditingController contentController;
  bool _isSaving = false;
  bool _saveFailed = false;

  @override
  void initState() {
    super.initState();
    contentController = TextEditingController(text: widget.memory?.content ?? '');
    contentController.selection = TextSelection.fromPosition(
      TextPosition(offset: contentController.text.length),
    );
  }

  @override
  void dispose() {
    contentController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isEditing = widget.memory != null;

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Container(
        decoration: const BoxDecoration(
          color: Color(0xFF1F1F25),
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        isEditing ? Icons.label_outline : Icons.add_circle_outline,
                        size: 14,
                        color: Colors.white,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        isEditing
                            ? (widget.memory!.category == MemoryCategory.manual
                                ? context.l10n.filterManual
                                : widget.memory!.category == MemoryCategory.interesting
                                    ? context.l10n.filterInteresting
                                    : context.l10n.filterSystem)
                            : context.l10n.newMemory,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                        ),
                      ),
                    ],
                  ),
                ),
                if (isEditing)
                  IconButton(
                    icon: const Icon(Icons.delete_outline, color: Colors.red),
                    onPressed: () => _showDeleteConfirmation(context),
                  )
                else
                  IconButton(
                    icon: Icon(Icons.close, color: Colors.grey.shade400),
                    onPressed: () => Navigator.pop(context),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 250),
              child: SingleChildScrollView(
                child: TextField(
                  controller: contentController,
                  autofocus: true,
                  maxLines: null,
                  minLines: 3,
                  textInputAction: TextInputAction.newline,
                  keyboardType: TextInputType.multiline,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    height: 1.4,
                  ),
                  decoration: InputDecoration(
                    hintText: isEditing ? null : context.l10n.memoryContentHint,
                    hintStyle: const TextStyle(color: Colors.grey),
                    border: InputBorder.none,
                    contentPadding: EdgeInsets.zero,
                    isDense: true,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 24),
            if (_saveFailed) ...[
              Text(
                context.l10n.failedToSaveMemory,
                style: const TextStyle(
                  color: Colors.redAccent,
                  fontSize: 13,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
            ],
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _isSaving ? null : _handleSave,
                style: ElevatedButton.styleFrom(
                  backgroundColor: _saveFailed ? Colors.orange : Colors.deepPurpleAccent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  disabledBackgroundColor: Colors.deepPurpleAccent.withOpacity(0.5),
                  disabledForegroundColor: Colors.white.withOpacity(0.7),
                ),
                child: _isSaving
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        ),
                      )
                    : Text(
                        _saveFailed ? context.l10n.retry : context.l10n.saveMemory,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _handleSave() async {
    if (contentController.text.trim().isEmpty) return;

    setState(() {
      _isSaving = true;
      _saveFailed = false;
    });

    final isEditing = widget.memory != null;
    bool success;

    try {
      if (isEditing) {
        success = await widget.provider.editMemory(widget.memory!, contentController.text);
        if (success) {
          MixpanelManager().memoriesPageEditedMemory();
        }
      } else {
        success = await widget.provider.createMemory(
          contentController.text,
          MemoryVisibility.private,
          MemoryCategory.manual,
        );
        if (success) {
          MixpanelManager().memoriesPageCreatedMemory(MemoryCategory.manual);
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

  Future<void> _showDeleteConfirmation(BuildContext context) async {
    if (widget.memory == null) return;

    final shouldDelete = await DeleteConfirmation.show(context);
    if (shouldDelete) {
      widget.provider.deleteMemory(widget.memory!);
      Navigator.pop(context);
    }
  }
}

// Helper function to show the memory dialog
Future<void> showMemoryDialog(BuildContext context, MemoriesProvider provider, {Memory? memory}) async {
  return showModalBottomSheet(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (context) => MemoryDialog(provider: provider, memory: memory),
  );
}
