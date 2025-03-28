import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:provider/provider.dart';

import 'widgets/memory_edit_sheet.dart';
import 'widgets/memory_item.dart';
import 'widgets/memory_dialog.dart';

class CategoryMemoriesPage extends StatelessWidget {
  final MemoryCategory category;

  const CategoryMemoriesPage({
    super.key,
    required this.category,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoriesProvider>(builder: (context, provider, child) {
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
                '${provider.filteredMemories.length} memories',
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
                showMemoryDialog(context, provider);
                MixpanelManager().memoriesPageCreateMemoryBtn();
              },
            ),
          ],
        ),
        body: provider.filteredMemories.isEmpty
            ? Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.note_add, size: 48, color: Colors.grey.shade600),
                    const SizedBox(height: 16),
                    Text(
                      'No memories in this category yet',
                      style: TextStyle(
                        color: Colors.grey.shade400,
                        fontSize: 18,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () => showMemoryDialog(context, provider),
                      child: const Text('Add your first memory'),
                    ),
                  ],
                ),
              )
            : ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: provider.filteredMemories.length,
                itemBuilder: (context, index) {
                  final memory = provider.filteredMemories[index];
                  return MemoryItem(
                    memory: memory,
                    provider: provider,
                    onTap: _showQuickEditSheet,
                  );
                },
              ),
      );
    });
  }

  void _showQuickEditSheet(BuildContext context, Memory memory, MemoriesProvider provider) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => MemoryEditSheet(
        memory: memory,
        provider: provider,
        onDelete: (_, __, ___) {},
      ),
    );
  }
}
