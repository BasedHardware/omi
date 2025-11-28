import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/ui_guidelines.dart';
import 'package:omi/widgets/extensions/functions.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

import 'widgets/memory_edit_sheet.dart';
import 'widgets/memory_item.dart';
import 'widgets/memory_dialog.dart';
import 'widgets/memory_review_sheet.dart';
import 'widgets/memory_management_sheet.dart';

// Filter options for the dropdown
enum FilterOption { interesting, system, manual, all }

class MemoriesPage extends StatefulWidget {
  const MemoriesPage({super.key});

  @override
  State<MemoriesPage> createState() => MemoriesPageState();
}

class _ReviewPromptHeaderDelegate extends SliverPersistentHeaderDelegate {
  final double height;
  final Widget child;

  _ReviewPromptHeaderDelegate({
    required this.height,
    required this.child,
  });

  @override
  double get minExtent => height;

  @override
  double get maxExtent => height;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    return SizedBox.expand(child: child);
  }

  @override
  bool shouldRebuild(_ReviewPromptHeaderDelegate oldDelegate) {
    return height != oldDelegate.height || child != oldDelegate.child;
  }
}

class MemoriesPageState extends State<MemoriesPage> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  final TextEditingController _searchController = TextEditingController();
  MemoryCategory? _selectedCategory;
  final ScrollController _scrollController = ScrollController();

  OverlayEntry? _deleteNotificationOverlay;
  // Filter options for the dropdown
  // Default will be set in initState based on current date
  late FilterOption _currentFilter;
  bool _isInitialLoad = true;

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    _removeDeleteNotification();
    super.dispose();
  }

  // Remove the delete notification overlay if it exists
  void _removeDeleteNotification() {
    _deleteNotificationOverlay?.remove();
    _deleteNotificationOverlay = null;
  }

  void showDeleteNotification(String memoryContent, Memory? memory) {
    _removeDeleteNotification();

    final provider = Provider.of<MemoriesProvider>(context, listen: false);

    _deleteNotificationOverlay = OverlayEntry(
      builder: (_) => Positioned(
        bottom: 20,
        left: 0,
        right: 0,
        child: Center(
          child: Material(
            color: Colors.transparent,
            child: Container(
              width: MediaQuery.of(context).size.width * 0.9,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: Colors.black87,
                borderRadius: BorderRadius.circular(8),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.2),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Row(
                children: [
                  const Expanded(
                    child: Text(
                      'Memory Deleted.',
                      style: TextStyle(color: Colors.white, fontSize: 14),
                    ),
                  ),
                  TextButton(
                    onPressed: () async {
                      final success = await provider.restoreLastDeletedMemory();
                      if (success) {
                        _removeDeleteNotification();
                      }
                    },
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      minimumSize: const Size(0, 36),
                    ),
                    child: const Text(
                      'Undo',
                      style: TextStyle(color: Colors.blue, fontWeight: FontWeight.w500),
                    ),
                  ),
                  IconButton(
                    onPressed: () {
                      _removeDeleteNotification();
                    },
                    icon: const Icon(Icons.close, color: Colors.white70, size: 20),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                    splashRadius: 20,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );

    Overlay.of(context).insert(_deleteNotificationOverlay!);

    Future.delayed(const Duration(seconds: 10), () {
      _removeDeleteNotification();
    });
  }

  @override
  void initState() {
    super.initState();
    // Set default filter to all
    _currentFilter = FilterOption.all;

    (() async {
      final provider = context.read<MemoriesProvider>();
      await provider.init();
      if (!mounted) return;

      // Apply the date-based default filter
      _applyFilter(_currentFilter);

      setState(() {
        _isInitialLoad = false;
      });

      final unreviewed = provider.unreviewed;
      final home = context.read<HomeProvider>();

      if (unreviewed.isNotEmpty && home.selectedIndex == 2) {
        _showReviewSheet(context, unreviewed, provider);
      }
    }).withPostFrameCallback();
  }

  void _applyFilter(FilterOption option) {
    setState(() {
      _currentFilter = option;
      switch (option) {
        case FilterOption.interesting:
          _filterByCategory(MemoryCategory.interesting);
          MixpanelManager().memoriesFiltered('interesting');
          break;
        case FilterOption.system:
          _filterByCategory(MemoryCategory.system);
          MixpanelManager().memoriesFiltered('system');
          break;
        case FilterOption.manual:
          _filterByCategory(MemoryCategory.manual);
          MixpanelManager().memoriesFiltered('manual');
          break;
        case FilterOption.all:
          _filterByCategory(null);
          MixpanelManager().memoriesFiltered('all');
          break;
      }
    });
  }

  void _filterByCategory(MemoryCategory? category) {
    if (!mounted) return;
    setState(() {
      _selectedCategory = category;
    });
    final provider = context.read<MemoriesProvider>();
    provider.setCategoryFilter(category);
  }

  // ignore: unused_element
  Map<MemoryCategory, int> _getCategoryCounts(List<Memory> memories) {
    var counts = <MemoryCategory, int>{};
    for (var memory in memories) {
      counts[memory.category] = (counts[memory.category] ?? 0) + 1;
    }
    return counts;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer<MemoriesProvider>(
      builder: (context, provider, _) {
        return PopScope(
          canPop: true,
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            floatingActionButton: Padding(
              padding: const EdgeInsets.only(bottom: 60.0),
              child: FloatingActionButton(
                heroTag: 'memories_fab',
                onPressed: () {
                  showMemoryDialog(context, provider);
                  MixpanelManager().memoriesPageCreateMemoryBtn();
                },
                backgroundColor: Colors.deepPurpleAccent,
                child: const Icon(
                  Icons.add,
                  color: Colors.white,
                ),
              ),
            ),
            body: RefreshIndicator(
              onRefresh: () async {
                HapticFeedback.mediumImpact();
                await provider.init();
              },
              color: Colors.deepPurpleAccent,
              backgroundColor: Colors.white,
              child: provider.loading && _isInitialLoad
                  ? CustomScrollView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      slivers: [
                        SliverToBoxAdapter(
                          child: Padding(
                            padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
                            child: Row(
                              children: [
                                Expanded(
                                  child: SizedBox(
                                    height: 44,
                                    child: SearchBar(
                                      hintText: 'Search ${provider.memories.length} Memories',
                                      leading: const Padding(
                                        padding: EdgeInsets.only(left: 6.0),
                                        child: Icon(FontAwesomeIcons.magnifyingGlass, color: Colors.white70, size: 14),
                                      ),
                                      backgroundColor: WidgetStateProperty.all(AppStyles.backgroundSecondary),
                                      elevation: WidgetStateProperty.all(0),
                                      padding: WidgetStateProperty.all(
                                        const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                                      ),
                                      hintStyle: WidgetStateProperty.all(
                                        TextStyle(color: AppStyles.textTertiary, fontSize: 14),
                                      ),
                                      textStyle: WidgetStateProperty.all(
                                        const TextStyle(color: AppStyles.textPrimary, fontSize: 14),
                                      ),
                                      shape: WidgetStateProperty.all(
                                        RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                SizedBox(
                                  width: 44,
                                  height: 44,
                                  child: _buildShimmerButton(),
                                ),
                                const SizedBox(width: 8),
                                SizedBox(
                                  width: 44,
                                  height: 44,
                                  child: _buildShimmerButton(),
                                ),
                                const SizedBox(width: 8),
                                SizedBox(
                                  width: 44,
                                  height: 44,
                                  child: _buildShimmerButton(),
                                ),
                              ],
                            ),
                          ),
                        ),
                        SliverFillRemaining(
                          child: _buildShimmerMemoryList(),
                        ),
                      ],
                    )
                  : CustomScrollView(
                      controller: _scrollController,
                      physics: const AlwaysScrollableScrollPhysics(),
                      slivers: [
                        SliverToBoxAdapter(
                          child: Padding(
                            padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
                            child: Row(
                              children: [
                                Consumer<HomeProvider>(builder: (context, home, child) {
                                  return Expanded(
                                    child: SizedBox(
                                      height: 44,
                                      child: SearchBar(
                                        hintText: 'Search ${provider.memories.length} Memories',
                                        leading: const Padding(
                                          padding: EdgeInsets.only(left: 6.0),
                                          child:
                                              Icon(FontAwesomeIcons.magnifyingGlass, color: Colors.white70, size: 14),
                                        ),
                                        backgroundColor: WidgetStateProperty.all(AppStyles.backgroundSecondary),
                                        elevation: WidgetStateProperty.all(0),
                                        padding: WidgetStateProperty.all(
                                          const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                                        ),
                                        focusNode: home.memoriesSearchFieldFocusNode,
                                        controller: _searchController,
                                        trailing: provider.searchQuery.isNotEmpty
                                            ? [
                                                IconButton(
                                                  icon: const Icon(Icons.close, color: Colors.white70, size: 16),
                                                  padding: EdgeInsets.zero,
                                                  constraints: const BoxConstraints(
                                                    minHeight: 36,
                                                    minWidth: 36,
                                                  ),
                                                  onPressed: () {
                                                    _searchController.clear();
                                                    provider.setSearchQuery('');
                                                    MixpanelManager().memorySearchCleared(provider.memories.length);
                                                  },
                                                )
                                              ]
                                            : null,
                                        hintStyle: WidgetStateProperty.all(
                                          TextStyle(color: AppStyles.textTertiary, fontSize: 14),
                                        ),
                                        textStyle: WidgetStateProperty.all(
                                          const TextStyle(color: AppStyles.textPrimary, fontSize: 14),
                                        ),
                                        shape: WidgetStateProperty.all(
                                          RoundedRectangleBorder(
                                            borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
                                          ),
                                        ),
                                        onChanged: (value) => provider.setSearchQuery(value),
                                        onSubmitted: (value) {
                                          if (value.isNotEmpty) {
                                            MixpanelManager().memorySearched(value, provider.filteredMemories.length);
                                          }
                                        },
                                      ),
                                    ),
                                  );
                                }),
                                const SizedBox(width: 8),
                                SizedBox(
                                  width: 44,
                                  height: 44,
                                  child: PopupMenuButton<FilterOption>(
                                    onSelected: _applyFilter,
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    color: AppStyles.backgroundSecondary,
                                    offset: const Offset(0, 8),
                                    elevation: 4,
                                    tooltip: 'Filter memories by category',
                                    position: PopupMenuPosition.under,
                                    itemBuilder: (BuildContext context) => <PopupMenuEntry<FilterOption>>[
                                      PopupMenuItem<FilterOption>(
                                        value: FilterOption.all,
                                        child: Row(
                                          children: [
                                            const Text(
                                              'All',
                                              style: TextStyle(color: Colors.white),
                                            ),
                                            const Spacer(),
                                            if (_currentFilter == FilterOption.all)
                                              const Icon(Icons.check, size: 16, color: Colors.white),
                                          ],
                                        ),
                                      ),
                                      PopupMenuItem<FilterOption>(
                                        value: FilterOption.interesting,
                                        child: Row(
                                          children: [
                                            const Text(
                                              'Interesting',
                                              style: TextStyle(color: Colors.white),
                                            ),
                                            const Spacer(),
                                            if (_currentFilter == FilterOption.interesting)
                                              const Icon(Icons.check, size: 16, color: Colors.white),
                                          ],
                                        ),
                                      ),
                                      PopupMenuItem<FilterOption>(
                                        value: FilterOption.system,
                                        child: Row(
                                          children: [
                                            const Text(
                                              'System',
                                              style: TextStyle(color: Colors.white),
                                            ),
                                            const Spacer(),
                                            if (_currentFilter == FilterOption.system)
                                              const Icon(Icons.check, size: 16, color: Colors.white),
                                          ],
                                        ),
                                      ),
                                      PopupMenuItem<FilterOption>(
                                        value: FilterOption.manual,
                                        child: Row(
                                          children: [
                                            const Text(
                                              'Manual',
                                              style: TextStyle(color: Colors.white),
                                            ),
                                            const Spacer(),
                                            if (_currentFilter == FilterOption.manual)
                                              const Icon(Icons.check, size: 16, color: Colors.white),
                                          ],
                                        ),
                                      ),
                                    ],
                                    child: Container(
                                      decoration: BoxDecoration(
                                        color: AppStyles.backgroundSecondary,
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: const Center(
                                        child: Icon(
                                          FontAwesomeIcons.filter,
                                          size: 16,
                                          color: Colors.white,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                SizedBox(
                                  width: 44,
                                  height: 44,
                                  child: ElevatedButton(
                                    onPressed: () {
                                      _showMemoryManagementSheet(context, provider);
                                    },
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: AppStyles.backgroundSecondary,
                                      foregroundColor: Colors.white,
                                      padding: EdgeInsets.zero,
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                    ),
                                    child: const Icon(FontAwesomeIcons.sliders, size: 16),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        if (provider.unreviewed.isNotEmpty)
                          SliverPersistentHeader(
                            pinned: true,
                            floating: true,
                            delegate: _ReviewPromptHeaderDelegate(
                              height: 56.0,
                              child: Material(
                                color: Theme.of(context).colorScheme.surfaceVariant,
                                elevation: 1,
                                child: InkWell(
                                  onTap: () => _showReviewSheet(context, provider.unreviewed, provider),
                                  child: Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 16.0),
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        Expanded(
                                          child: Row(
                                            children: [
                                              Icon(FontAwesomeIcons.listCheck,
                                                  color: Theme.of(context).colorScheme.onSurfaceVariant, size: 18),
                                              const SizedBox(width: 12),
                                              Flexible(
                                                child: Text(
                                                  '${provider.unreviewed.length} ${provider.unreviewed.length == 1 ? "memory" : "memories"} to review',
                                                  style: TextStyle(
                                                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                                                      fontWeight: FontWeight.w500),
                                                  overflow: TextOverflow.ellipsis,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        Padding(
                                          padding: const EdgeInsets.only(left: 8.0),
                                          child: Text('Review',
                                              style: TextStyle(
                                                  color: Theme.of(context).colorScheme.primary,
                                                  fontWeight: FontWeight.bold)),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        if (provider.filteredMemories.isEmpty)
                          SliverFillRemaining(
                            child: Center(
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(Icons.note_add, size: 48, color: Colors.grey.shade600),
                                  const SizedBox(height: 16),
                                  Text(
                                    provider.searchQuery.isEmpty && _selectedCategory == null
                                        ? 'No memories yet'
                                        : _selectedCategory != null
                                            ? _selectedCategory == MemoryCategory.interesting
                                                ? 'No interesting memories yet'
                                                : _selectedCategory == MemoryCategory.system
                                                    ? 'No system memories yet'
                                                    : 'No memories in this category'
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
                            ),
                          )
                        else
                          SliverPadding(
                            padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 120),
                            sliver: SliverList(
                              delegate: SliverChildBuilderDelegate(
                                (context, index) {
                                  final memory = provider.filteredMemories[index];
                                  return MemoryItem(
                                    memory: memory,
                                    provider: provider,
                                    onTap:
                                        (BuildContext context, Memory tappedMemory, MemoriesProvider tappedProvider) {
                                      MixpanelManager().memoryListItemClicked(tappedMemory);
                                      _showQuickEditSheet(context, tappedMemory, tappedProvider);
                                    },
                                  );
                                },
                                childCount: provider.filteredMemories.length,
                              ),
                            ),
                          ),
                      ],
                    ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildShimmerButton() {
    return Shimmer.fromColors(
      baseColor: AppStyles.backgroundSecondary,
      highlightColor: AppStyles.backgroundTertiary,
      child: Container(
        decoration: BoxDecoration(
          color: AppStyles.backgroundSecondary,
          borderRadius: BorderRadius.circular(12),
        ),
      ),
    );
  }

  Widget _buildShimmerMemoryList() {
    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16, bottom: 120),
      child: ListView.builder(
        itemCount: 8, // Show 8 shimmer items
        itemBuilder: (context, index) {
          return Shimmer.fromColors(
            baseColor: AppStyles.backgroundSecondary,
            highlightColor: AppStyles.backgroundTertiary,
            child: Container(
              margin: const EdgeInsets.only(bottom: AppStyles.spacingM),
              height: 88, // Approximate height of a memory item
              decoration: BoxDecoration(
                color: AppStyles.backgroundSecondary,
                borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
              ),
            ),
          );
        },
      ),
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

  void _showReviewSheet(BuildContext context, List<Memory> memories, MemoriesProvider existingProvider) async {
    if (memories.isEmpty || !mounted) return;
    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: false,
      isScrollControlled: true,
      builder: (sheetContext) {
        return ChangeNotifierProvider.value(
          value: existingProvider,
          child: MemoriesReviewSheet(
            memories: memories,
            provider: existingProvider,
          ),
        );
      },
    );
  }

  // ignore: unused_element
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
        backgroundColor: const Color(0xFF1F1F25),
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

  void scrollToTop() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        0.0,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeOutCubic,
      );
    }
  }

  void _showMemoryManagementSheet(BuildContext context, MemoriesProvider provider) {
    MixpanelManager().memoriesManagementSheetOpened();
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => MemoryManagementSheet(provider: provider),
    );
  }
}

// ignore: unused_element
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
    return maxHeight != oldDelegate.maxHeight || minHeight != oldDelegate.minHeight || child != oldDelegate.child;
  }
}
