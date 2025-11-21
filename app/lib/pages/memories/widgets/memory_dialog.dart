import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

import 'delete_confirmation.dart';

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
    return StatefulBuilder(
      builder: (context, setState) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        child: Container(
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    widget.memory != null ? 'Edit Memory' : 'New Memory',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  IconButton(
                    icon: Icon(
                      Icons.close,
                      color: Colors.grey.shade400,
                      size: 22,
                    ),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Container(
                decoration: BoxDecoration(
                  color: Color(0xFF35343B),
                  borderRadius: BorderRadius.circular(12),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                child: TextField(
                  controller: contentController,
                  textInputAction: TextInputAction.newline,
                  autofocus: true,
                  maxLines: null,
                  minLines: 3,
                  keyboardType: TextInputType.multiline,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    height: 1.4,
                  ),
                  decoration: const InputDecoration(
                    hintText: 'I like to eat ice cream...',
                    hintStyle: TextStyle(color: Colors.grey),
                    border: InputBorder.none,
                    contentPadding: EdgeInsets.zero,
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () {
                    if (contentController.text.trim().isNotEmpty) {
                      if (widget.memory != null) {
                        widget.provider.editMemory(widget.memory!, contentController.text);
                        MixpanelManager().memoriesPageEditedMemory();
                      } else {
                        widget.provider
                            .createMemory(contentController.text, MemoryVisibility.private, MemoryCategory.manual);
                        MixpanelManager().memoriesPageCreatedMemory(MemoryCategory.manual);
                      }
                      Navigator.pop(context);
                    }
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.deepPurpleAccent,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: Text(
                    widget.memory != null ? 'Update Memory' : 'Save Memory',
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              if (widget.memory != null)
                TextButton.icon(
                  onPressed: () => _showDeleteConfirmation(context),
                  icon: const Icon(Icons.delete_outline, color: Colors.red, size: 18),
                  label: const Text(
                    'Delete Memory',
                    style: TextStyle(color: Colors.red),
                  ),
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showDeleteConfirmation(BuildContext context) async {
    if (widget.memory == null) return;

    final shouldDelete = await DeleteConfirmation.show(context);
    if (shouldDelete) {
      widget.provider.deleteMemory(widget.memory!);
      Navigator.pop(context); // Close edit sheet
    }
  }
}

// Helper function to show the memory dialog
Future<void> showMemoryDialog(BuildContext context, MemoriesProvider provider, {Memory? memory}) async {
  final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
  if (!connectivityProvider.isConnected) {
    ConnectivityProvider.showNoInternetDialog(context);
    return;
  }

  return showModalBottomSheet(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (context) => MemoryDialog(provider: provider, memory: memory),
  );
}
