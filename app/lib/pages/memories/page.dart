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
import 'widgets/category_chip.dart';

class MemoriesPage extends StatefulWidget {
  const MemoriesPage({super.key});

  @override
  State<MemoriesPage> createState() => MemoriesPageState();
}

class MemoriesPageState extends State<MemoriesPage> {
  final TextEditingController _searchController = TextEditingController();
  MemoryCategory? _selectedCategory;
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
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

  void _filterByCategory(MemoryCategory? category) {
    setState(() {
      _selectedCategory = category;
    });

    // Apply category filter to provider
    context.read<MemoriesProvider>().setCategoryFilter(category);
  }

  Map<MemoryCategory, int> _getCategoryCounts(List<Memory> memories) {
    var counts = <MemoryCategory, int>{};
    for (var memory in memories) {
      counts[memory.category] = (counts[memory.category] ?? 0) + 1;
    }
    return counts;
  }

  Widget _buildSearchBar() {
    return Consumer<MemoriesProvider>(
      builder: (context, provider, _) {
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
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
        );
      }
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<MemoriesProvider>(
      builder: (context, provider, _) {
        final unreviewedCount = provider.unreviewed.length;
        final categoryCounts = _getCategoryCounts(provider.memories);

        return PopScope(
          canPop: true,
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            body: provider.loading
                ? const Center(
                    child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ))
                : NestedScrollView(
                    controller: _scrollController,
                    headerSliverBuilder: (context, innerBoxIsScrolled) {
                      return [
                        // AppBar with the title and action buttons
                        SliverAppBar(
                          backgroundColor: Theme.of(context).colorScheme.primary,
                          pinned: true,
                          centerTitle: true,
                          title: const Text('Memories'),
                          actions: [
                            if (unreviewedCount > 0)
                              Stack(
                                alignment: Alignment.center,
                                children: [
                                  IconButton(
                                    icon: const Icon(Icons.reviews_outlined),
                                    onPressed: () {
                                      _showReviewSheet(provider.unreviewed);
                                      MixpanelManager().memoriesPageReviewBtn();
                                    },
                                    tooltip: 'Review memories',
                                  ),
                                  Positioned(
                                    top: 10,
                                    right: 10,
                                    child: Container(
                                      padding: const EdgeInsets.all(2),
                                      decoration: BoxDecoration(
                                        color: Colors.red,
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                      constraints: const BoxConstraints(
                                        minWidth: 16,
                                        minHeight: 16,
                                      ),
                                      child: Text(
                                        '$unreviewedCount',
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 10,
                                          fontWeight: FontWeight.bold,
                                        ),
                                        textAlign: TextAlign.center,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
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
                        ),

                        // Category filter
                        if (categoryCounts.isNotEmpty)
                          SliverToBoxAdapter(
                            child: Container(
                              height: 50,
                              margin: const EdgeInsets.fromLTRB(0, 0, 0, 8),
                              child: ListView(
                                scrollDirection: Axis.horizontal,
                                padding: const EdgeInsets.symmetric(horizontal: 16),
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.only(right: 8),
                                    child: FilterChip(
                                      label: Text(
                                        'All (${provider.memories.length})',
                                        style: TextStyle(
                                          color: _selectedCategory == null ? Colors.black : Colors.white70,
                                          fontWeight: _selectedCategory == null ? FontWeight.w600 : FontWeight.normal,
                                        ),
                                      ),
                                      selected: _selectedCategory == null,
                                      onSelected: (_) => _filterByCategory(null),
                                      backgroundColor: Colors.grey.shade800,
                                      selectedColor: Colors.white,
                                      checkmarkColor: Colors.black,
                                      showCheckmark: false,
                                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                    ),
                                  ),
                                  ...categoryCounts.entries.map((entry) {
                                    final category = entry.key;
                                    final count = entry.value;
                                    return Padding(
                                      padding: const EdgeInsets.only(right: 8),
                                      child: FilterChip(
                                        label: Text(
                                          '${category.toString().split('.').last} ($count)',
                                          style: TextStyle(
                                            color: _selectedCategory == category ? Colors.black : Colors.white70,
                                            fontWeight: _selectedCategory == category ? FontWeight.w600 : FontWeight.normal,
                                          ),
                                        ),
                                        selected: _selectedCategory == category,
                                        onSelected: (_) => _filterByCategory(category),
                                        backgroundColor: Colors.grey.shade800,
                                        selectedColor: Colors.white,
                                        checkmarkColor: Colors.black,
                                        showCheckmark: false,
                                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                      ),
                                    );
                                  }),
                                ],
                              ),
                            ),
                          ),

                        // Search bar that appears when scrolling
                        SliverPersistentHeader(
                          pinned: true,
                          floating: true,
                          delegate: _SliverSearchBarDelegate(
                            minHeight: 0,
                            maxHeight: 60,
                            child: Container(
                              color: Theme.of(context).colorScheme.primary,
                              child: _buildSearchBar(),
                            ),
                          ),
                        ),
                      ];
                    },
                    body: provider.filteredMemories.isEmpty
                        ? Center(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(Icons.note_add, size: 48, color: Colors.grey.shade600),
                                const SizedBox(height: 16),
                                Text(
                                  provider.searchQuery.isEmpty && _selectedCategory == null
                                      ? 'No memories yet'
                                      : _selectedCategory != null
                                          ? 'No memories in this category'
                                          : 'No memories found',
                                  style: TextStyle(
                                    color: Colors.grey.shade400,
                                    fontSize: 18,
                                  ),
                                ),
                                if (provider.searchQuery.isEmpty && _selectedCategory == null) ...[
                                  const SizedBox(height: 8),
                                  TextButton(
                                    onPressed: () => showMemoryDialog(context, provider),
                                    child: const Text('Add your first memory'),
                                  ),
                                ],
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

class _SliverSearchBarDelegate extends SliverPersistentHeaderDelegate {
  final double minHeight;
  final double maxHeight;
  final Widget child;

  _SliverSearchBarDelegate({
    required this.minHeight,
    required this.maxHeight,
    required this.child,
  });

  @override
  double get minExtent => minHeight;

  @override
  double get maxExtent => maxHeight;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    return SizedBox.expand(child: child);
  }

  @override
  bool shouldRebuild(_SliverSearchBarDelegate oldDelegate) {
    return maxHeight != oldDelegate.maxHeight ||
        minHeight != oldDelegate.minHeight ||
        child != oldDelegate.child;
  }
}
