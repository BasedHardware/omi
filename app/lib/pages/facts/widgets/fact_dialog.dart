import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/facts_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
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

  @override
  void initState() {
    super.initState();
    contentController = TextEditingController(text: widget.fact?.content ?? '');
    contentController.selection = TextSelection.fromPosition(
      TextPosition(offset: contentController.text.length),
    );
    selectedCategory = widget.fact?.category ?? widget.provider.selectedCategory ?? FactCategory.values.first;
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
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    widget.fact != null ? 'Edit Fact' : 'New Fact',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (widget.fact != null)
                    IconButton(
                      icon: const Icon(Icons.delete_outline, color: Colors.red, size: 22),
                      onPressed: () => _showDeleteConfirmation(context),
                    ),
                ],
              ),
              if (widget.fact == null || !widget.fact!.manuallyAdded) ...[
                const SizedBox(height: 16),
                SizedBox(
                  height: 34,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: FactCategory.values.length,
                    separatorBuilder: (context, _) => const SizedBox(width: 8),
                    itemBuilder: (context, index) {
                      final category = FactCategory.values[index];
                      final isSelected = category == selectedCategory;
                      return GestureDetector(
                        onTap: () => setState(() => selectedCategory = category),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                          decoration: BoxDecoration(
                            color: isSelected ? Colors.white.withOpacity(0.1) : Colors.grey.shade800,
                            borderRadius: BorderRadius.circular(17),
                            border: Border.all(
                              color: isSelected ? Colors.white : Colors.transparent,
                              width: 1,
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (isSelected) ...[
                                const Icon(
                                  Icons.check,
                                  size: 14,
                                  color: Colors.white,
                                ),
                                const SizedBox(width: 4),
                              ],
                              Text(
                                category.toString().split('.').last,
                                style: TextStyle(
                                  color: isSelected ? Colors.white : Colors.white70,
                                  fontSize: 13,
                                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ],
              const SizedBox(height: 24),
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
              const SizedBox(height: 16),
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
            ],
          ),
        ),
      ),
    );
  }

  void _saveFact(String value) {
    if (value.trim().isNotEmpty) {
      if (widget.fact != null) {
        widget.provider.editFact(widget.fact!, value, selectedCategory);
        MixpanelManager().factsPageEditedFact();
      } else {
        widget.provider.createFact(value, selectedCategory);
        MixpanelManager().factsPageCreatedFact(selectedCategory);
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
