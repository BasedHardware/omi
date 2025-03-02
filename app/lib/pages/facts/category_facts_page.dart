import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/providers/facts_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

class CategoryFactsPage extends StatelessWidget {
  final FactCategory category;
  final Function(BuildContext, FactsProvider, {Fact? fact}) showFactDialog;

  const CategoryFactsPage({
    super.key,
    required this.category,
    required this.showFactDialog,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<FactsProvider>(builder: (context, provider, child) {
      return Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        appBar: AppBar(
          backgroundColor: Theme.of(context).colorScheme.primary,
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                category.toString().split('.').last[0].toUpperCase() + category.toString().split('.').last.substring(1),
              ),
              Text(
                '${provider.filteredFacts.length} facts',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey.shade400,
                  fontWeight: FontWeight.normal,
                ),
              ),
            ],
          ),
          actions: [
            IconButton(
              icon: const Icon(Icons.add),
              onPressed: () {
                showFactDialog(context, provider);
                MixpanelManager().factsPageCreateFactBtn();
              },
            ),
          ],
        ),
        body: provider.filteredFacts.isEmpty
            ? Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.note_add, size: 48, color: Colors.grey.shade600),
                    const SizedBox(height: 16),
                    Text(
                      'No facts in this category yet',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 18,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () => showFactDialog(context, provider),
                      child: const Text('Add your first fact'),
                    ),
                  ],
                ),
              )
            : ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: provider.filteredFacts.length,
                itemBuilder: (context, index) {
                  final fact = provider.filteredFacts[index];
                  return Dismissible(
                    key: Key(fact.id),
                    direction: DismissDirection.endToStart,
                    onDismissed: (direction) {
                      provider.deleteFact(fact);
                      MixpanelManager().factsPageDeletedFact(fact);
                    },
                    background: Container(
                      margin: const EdgeInsets.only(bottom: 8),
                      decoration: BoxDecoration(
                        color: Colors.red.shade900,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      alignment: Alignment.centerRight,
                      padding: const EdgeInsets.only(right: 20),
                      child: const Icon(Icons.delete_outline, color: Colors.white),
                    ),
                    child: GestureDetector(
                      onTap: () => _showQuickEditSheet(context, fact, provider),
                      child: Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: ListTile(
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                          title: Text(
                            fact.content.decodeString,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
      );
    });
  }

  void _showQuickEditSheet(BuildContext context, Fact fact, FactsProvider provider) {
    final contentController = TextEditingController(text: fact.content.decodeString);
    contentController.selection = TextSelection.fromPosition(
      TextPosition(offset: contentController.text.length),
    );

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
        child: Container(
          decoration: BoxDecoration(
            color: Colors.grey.shade900,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
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
                        const Icon(Icons.label_outline, size: 14, color: Colors.white),
                        const SizedBox(width: 4),
                        Text(
                          fact.category.toString().split('.').last,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 14,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline, color: Colors.red),
                    onPressed: () => _showDeleteConfirmation(context, fact, provider),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: contentController,
                autofocus: true,
                maxLines: null,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  height: 1.4,
                ),
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.zero,
                  isDense: true,
                ),
                onSubmitted: (value) {
                  if (value.trim().isNotEmpty) {
                    provider.editFactProvider(fact, value, fact.category);
                  }
                  Navigator.pop(context);
                },
                onChanged: (value) {
                  if (value.trim().isNotEmpty) {
                    provider.editFactProvider(fact, value, fact.category);
                  }
                },
              ),
              const SizedBox(height: 12),
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

  void _showDeleteConfirmation(BuildContext context, Fact fact, FactsProvider provider) {
    if (Platform.isIOS) {
      showCupertinoDialog(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('Delete fact?'),
          content: const Text('This action cannot be undone.'),
          actions: [
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.pop(context),
              child: Text(
                'Cancel',
                style: TextStyle(color: Colors.grey[400]),
              ),
            ),
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () {
                provider.deleteFact(fact);
                Navigator.pop(context); // Close dialog
                Navigator.pop(context); // Close edit sheet
              },
              child: const Text('Delete'),
            ),
          ],
        ),
      );
    } else {
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: Colors.grey.shade900,
          surfaceTintColor: Colors.transparent,
          title: const Text(
            'Delete fact?',
            style: TextStyle(color: Colors.white, fontSize: 18),
          ),
          content: const Text(
            'This action cannot be undone.',
            style: TextStyle(color: Colors.white70, fontSize: 14),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(
                'Cancel',
                style: TextStyle(color: Colors.grey.shade400),
              ),
            ),
            TextButton(
              onPressed: () {
                provider.deleteFact(fact);
                Navigator.pop(context); // Close dialog
                Navigator.pop(context); // Close edit sheet
              },
              child: const Text(
                'Delete',
                style: TextStyle(color: Colors.red),
              ),
            ),
          ],
        ),
      );
    }
  }
}
