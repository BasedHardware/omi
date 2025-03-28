import 'package:flutter/material.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/extensions/functions.dart';
import 'package:provider/provider.dart';

import 'widgets/memory_edit_sheet.dart';
import 'widgets/memory_item.dart';
import 'widgets/memory_dialog.dart';
import 'widgets/memory_review_sheet.dart';

class MemoriesPage extends StatefulWidget {
  const MemoriesPage({super.key});

  @override
  State<MemoriesPage> createState() => MemoriesPageState();
}

class MemoriesPageState extends State<MemoriesPage> {
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    () async {
      await context.read<MemoriesProvider>().init();

      final unreviewedMemories = context.read<MemoriesProvider>().unreviewed;
      if (unreviewedMemories.isNotEmpty) {
        _showReviewSheet(unreviewedMemories);
      }
    }.withPostFrameCallback();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoriesProvider>(
      builder: (context, provider, _) {
        return PopScope(
          canPop: true,
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            body: provider.loading
                ? const Center(
                    child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ))
                : CustomScrollView(
                    slivers: [
                      SliverAppBar(
                        backgroundColor: Theme.of(context).colorScheme.primary,
                        pinned: true,
                        snap: true,
                        floating: true,
                        title: const Text('My Memory'),
                        actions: [
                          IconButton(
                            icon: const Icon(Icons.delete_sweep_outlined),
                            onPressed: () {
                              _showDeleteAllConfirmation(context, provider);
                            },
                          ),
                          IconButton(
                            icon: const Icon(Icons.add),
                            onPressed: () {
                              showMemoryDialog(context, provider);
                              MixpanelManager().memoriesPageCreateMemoryBtn();
                            },
                          ),
                        ],
                        bottom: PreferredSize(
                          preferredSize: const Size.fromHeight(68),
                          child: Padding(
                            padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                            child: SearchBar(
                              hintText: 'Search Omi\'s memory about you',
                              leading: const Icon(Icons.search, color: Colors.white70),
                              backgroundColor: WidgetStateProperty.all(Colors.grey.shade900),
                              elevation: WidgetStateProperty.all(0),
                              padding: WidgetStateProperty.all(
                                const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                              ),
                              controller: _searchController,
                              trailing: provider.searchQuery.isNotEmpty
                                  ? [
                                      IconButton(
                                        icon: const Icon(Icons.close, color: Colors.white70),
                                        onPressed: () {
                                          _searchController.clear();
                                          setState(() {});
                                          provider.setSearchQuery('');
                                        },
                                      )
                                    ]
                                  : null,
                              hintStyle: WidgetStateProperty.all(
                                TextStyle(color: Colors.grey.shade400, fontSize: 14),
                              ),
                              shape: WidgetStateProperty.all(
                                RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                              onChanged: (value) => provider.setSearchQuery(value),
                            ),
                          ),
                        ),
                      ),
                      SliverPadding(
                        padding: const EdgeInsets.all(16),
                        sliver: provider.filteredMemories.isEmpty
                            ? SliverFillRemaining(
                                child: Center(
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(Icons.note_add, size: 48, color: Colors.grey.shade600),
                                      const SizedBox(height: 16),
                                      Text(
                                        provider.searchQuery.isEmpty ? 'No memories yet' : 'No memories found',
                                        style: TextStyle(
                                          color: Colors.grey.shade400,
                                          fontSize: 18,
                                        ),
                                      ),
                                      if (provider.searchQuery.isEmpty) ...[
                                        const SizedBox(height: 8),
                                        TextButton(
                                          onPressed: () => showMemoryDialog(context, provider),
                                          child: const Text('Add your first memory'),
                                        ),
                                      ],
                                    ],
                                  ),
                                ),
                              )
                            : SliverList(
                                delegate: SliverChildBuilderDelegate(
                                  (context, index) {
                                    final memory = provider.filteredMemories[index];
                                    return MemoryItem(
                                      memory: memory,
                                      provider: provider,
                                      onTap: _showQuickEditSheet,
                                    );
                                  },
                                  childCount: provider.filteredMemories.length,
                                ),
                              ),
                      ),
                    ],
                  ),
          ),
        );
      },
    );
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

  void _showReviewSheet(List<Memory> memories) async {
    if (memories.isEmpty) return;
    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: false,
      builder: (context) => ListenableProvider(
          create: (_) => MemoriesProvider(),
          builder: (context, _) {
            return MemoriesReviewSheet(
              memories: memories,
              provider: context.read<MemoriesProvider>(),
            );
          }),
    );
  }

  void _showDeleteAllConfirmation(BuildContext context, MemoriesProvider provider) {
    if (provider.memories.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No memories to delete'),
          duration: Duration(seconds: 2),
        ),
      );
      return;
    }

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text(
          'Clear Omi\'s Memory',
          style: TextStyle(color: Colors.white),
        ),
        content: Text(
          'Are you sure you want to clear Omi\'s memory? This action cannot be undone.',
          style: TextStyle(color: Colors.grey.shade300),
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
              provider.deleteAllMemories();
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Omi\'s memory about you has been cleared'),
                  duration: Duration(seconds: 2),
                ),
              );
            },
            child: const Text(
              'Clear Memory',
              style: TextStyle(color: Colors.red),
            ),
          ),
        ],
      ),
    );
  }
}
