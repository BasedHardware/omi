import 'package:flutter/material.dart';
import 'package:omi/backend/schema/fact.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/facts_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

import 'delete_confirmation.dart';

class FactDialog extends StatefulWidget {
  final FactsProvider provider;
  final Fact? fact;

  const FactDialog({
    super.key,
    required this.provider,
    this.fact,
  });

  @override
  State<FactDialog> createState() => _FactDialogState();
}

class _FactDialogState extends State<FactDialog> {
  late TextEditingController contentController;
  late FactCategory selectedCategory;
  late FactVisibility selectedVisibility;

  @override
  void initState() {
    super.initState();
    contentController = TextEditingController(text: widget.fact?.content ?? '');
    contentController.selection = TextSelection.fromPosition(
      TextPosition(offset: contentController.text.length),
    );
    selectedCategory = widget.fact?.category ?? FactCategory.values.first;
    selectedVisibility = widget.fact?.visibility ?? FactVisibility.public;
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
            color: Colors.grey.shade900,
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
                    widget.fact != null ? 'Edit Memory' : 'New Memory',
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
                  color: Colors.grey.shade800,
                  borderRadius: BorderRadius.circular(12),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                child: TextField(
                  controller: contentController,
                  textInputAction: TextInputAction.done,
                  autofocus: true,
                  maxLines: null,
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
                  onSubmitted: (value) => _saveFact(value),
                ),
              ),
              if (widget.fact == null || !widget.fact!.manuallyAdded) ...[
                const SizedBox(height: 20),
                Text(
                  'Visibility',
                  style: TextStyle(
                    color: Colors.grey.shade400,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: FactVisibility.values.map((visibility) {
                    final isSelected = visibility == selectedVisibility;
                    return Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              visibility == FactVisibility.private ? Icons.lock_outline : Icons.public,
                              size: 16,
                              color: isSelected ? Colors.black : Colors.white70,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              visibility == FactVisibility.private ? 'Private' : 'Public',
                              style: TextStyle(
                                color: isSelected ? Colors.black : Colors.white70,
                                fontSize: 13,
                                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                              ),
                            ),
                          ],
                        ),
                        selected: isSelected,
                        showCheckmark: false,
                        backgroundColor: Colors.grey.shade800,
                        selectedColor: Colors.white,
                        onSelected: (bool selected) {
                          if (selected) {
                            setState(() => selectedVisibility = visibility);
                          }
                        },
                      ),
                    );
                  }).toList(),
                ),
              ],
              const SizedBox(height: 24),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.keyboard_return,
                          size: 13,
                          color: Colors.grey.shade400,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          'Press done to save',
                          style: TextStyle(
                            color: Colors.grey.shade400,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    '${contentController.text.length}/200',
                    style: TextStyle(
                      color: Colors.grey.shade500,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              if (widget.fact != null)
                TextButton.icon(
                  onPressed: () => _showDeleteConfirmation(context),
                  icon: const Icon(Icons.delete_outline, color: Colors.red, size: 18),
                  label: const Text(
                    'Delete Fact',
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

  void _saveFact(String value) {
    if (value.trim().isNotEmpty) {
      if (widget.fact != null) {
        widget.provider.editFact(widget.fact!, value);
        if (widget.fact!.visibility != selectedVisibility) {
          widget.provider.updateFactVisibility(widget.fact!, selectedVisibility);
        }
        MixpanelManager().factsPageEditedFact();
      } else {
        widget.provider.createFact(value, selectedVisibility);
        MixpanelManager().factsPageCreatedFact(FactCategory.values.first);
      }
      Navigator.pop(context);
    }
  }

  Future<void> _showDeleteConfirmation(BuildContext context) async {
    if (widget.fact == null) return;

    final shouldDelete = await DeleteConfirmation.show(context);
    if (shouldDelete) {
      widget.provider.deleteFact(widget.fact!);
      Navigator.pop(context); // Close edit sheet
    }
  }
}

// Helper function to show the fact dialog
Future<void> showFactDialog(BuildContext context, FactsProvider provider, {Fact? fact}) async {
  final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
  if (!connectivityProvider.isConnected) {
    ConnectivityProvider.showNoInternetDialog(context);
    return;
  }

  return showModalBottomSheet(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (context) => FactDialog(provider: provider, fact: fact),
  );
}
