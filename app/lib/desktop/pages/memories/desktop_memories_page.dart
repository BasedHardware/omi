import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/functions.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

import 'widgets/desktop_memory_item.dart';
import 'widgets/desktop_memory_dialog.dart';

// Filter options for the dropdown
enum FilterOption { interesting, system, all }

class DesktopMemoriesPage extends StatefulWidget {
  const DesktopMemoriesPage({super.key});

  @override
  State<DesktopMemoriesPage> createState() => DesktopMemoriesPageState();
}

class DesktopMemoriesPageState extends State<DesktopMemoriesPage> with AutomaticKeepAliveClientMixin, TickerProviderStateMixin {
  @override
  bool get wantKeepAlive => true;

  final TextEditingController _searchController = TextEditingController();
  MemoryCategory? _selectedCategory;
  final ScrollController _scrollController = ScrollController();

  // Animation controllers for modern feel
  late AnimationController _fadeController;
  late AnimationController _slideController;
  late AnimationController _pulseController;

  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _pulseAnimation;

  bool _animationsInitialized = false;

  // Filter options for the dropdown
  // Default will be set in initState based on current date
  late FilterOption _currentFilter;

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    _fadeController.dispose();
    _slideController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();

    // Initialize animations for modern feel
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _slideController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );

    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat(reverse: true);

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _fadeController, curve: Curves.easeOutCubic),
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.3),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _slideController, curve: Curves.easeOutCubic));

    _pulseAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    // Mark animations as initialized
    _animationsInitialized = true;

    // Set default filter based on current date
    final now = DateTime.now();
    final cutoffDate = DateTime(2025, 5, 31);

    if (now.isAfter(cutoffDate)) {
      _currentFilter = FilterOption.interesting;
    } else {
      _currentFilter = FilterOption.all;
    }

    (() async {
      final provider = context.read<MemoriesProvider>();
      await provider.init();

      // Apply the date-based default filter
      _applyFilter(_currentFilter);

      if (!mounted) return;
      final unreviewedMemories = provider.unreviewed;
      final home = context.read<HomeProvider>();
      if (unreviewedMemories.isNotEmpty && home.selectedIndex == 2) {
        _showReviewSheet(context, unreviewedMemories, provider);
      }

      // Start animations
      _fadeController.forward();
      _slideController.forward();
    }).withPostFrameCallback();
  }

  void _applyFilter(FilterOption option) {
    final provider = context.read<MemoriesProvider>();
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
        case FilterOption.all:
          _filterByCategory(null); // null means no category filter
          MixpanelManager().memoriesFiltered('all');
          break;
      }
    });
  }

  void _filterByCategory(MemoryCategory? category) {
    setState(() {
      _selectedCategory = category;
    });
    context.read<MemoriesProvider>().setCategoryFilter(category);
  }

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
        return Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                ResponsiveHelper.backgroundPrimary,
                ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
              ],
            ),
            borderRadius: BorderRadius.circular(20),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: Stack(
              children: [
                // Animated background pattern
                _buildAnimatedBackground(),

                // Main content with glassmorphism
                Container(
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.02),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Column(
                    children: [
                      // Modern header with controls
                      _buildModernHeader(provider),

                      // Main memories area
                      Expanded(
                        child: _animationsInitialized
                            ? FadeTransition(
                                opacity: _fadeAnimation,
                                child: SlideTransition(
                                  position: _slideAnimation,
                                  child: _buildMemoriesContent(provider),
                                ),
                              )
                            : _buildMemoriesContent(provider),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildAnimatedBackground() {
    if (!_animationsInitialized) {
      return Container(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: Alignment.topRight,
            radius: 2.0,
            colors: [
              ResponsiveHelper.purplePrimary.withOpacity(0.05),
              Colors.transparent,
            ],
          ),
        ),
      );
    }

    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        return Container(
          decoration: BoxDecoration(
            gradient: RadialGradient(
              center: Alignment.topRight,
              radius: 2.0,
              colors: [
                ResponsiveHelper.purplePrimary.withOpacity(0.05 + _pulseAnimation.value * 0.03),
                Colors.transparent,
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildModernHeader(MemoriesProvider provider) {
    return Container(
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          // Search field
          Expanded(
            child: Container(
              height: 44,
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                borderRadius: BorderRadius.circular(12),
              ),
              child: TextField(
                controller: _searchController,
                style: TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 14,
                ),
                decoration: InputDecoration(
                  hintText: '🔍 Search memories...',
                  hintStyle: TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 14,
                  ),
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 12,
                  ),
                ),
                onChanged: (value) {
                  provider.setSearchQuery(value);
                },
              ),
            ),
          ),

          const SizedBox(width: 12),

          // Filter dropdown
          _buildFilterDropdown(provider),

          const SizedBox(width: 12),

          // Add memory button
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => _showMemoryDialog(context, provider),
              borderRadius: BorderRadius.circular(12),
              child: Container(
                height: 44,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  Icons.add,
                  color: ResponsiveHelper.purplePrimary,
                  size: 20,
                ),
              ),
            ),
          ),

          const SizedBox(width: 8),

          // Management menu
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => _showManagementSheet(context, provider),
              borderRadius: BorderRadius.circular(12),
              child: Container(
                height: 44,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  Icons.more_vert,
                  color: ResponsiveHelper.textSecondary,
                  size: 20,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterDropdown(MemoriesProvider provider) {
    return Container(
      height: 44,
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
        borderRadius: BorderRadius.circular(12),
      ),
      child: PopupMenuButton<FilterOption>(
        color: ResponsiveHelper.backgroundSecondary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        offset: const Offset(0, 48),
        child: Container(
          height: 44,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.filter_list,
                color: ResponsiveHelper.textSecondary,
                size: 16,
              ),
              const SizedBox(width: 6),
              Text(
                _getFilterText(),
                style: TextStyle(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 12,
                ),
              ),
              const SizedBox(width: 6),
              Icon(
                Icons.keyboard_arrow_down,
                color: ResponsiveHelper.textSecondary,
                size: 16,
              ),
            ],
          ),
        ),
        itemBuilder: (context) => [
          _buildFilterItem(FilterOption.all, 'All Memories'),
          _buildFilterItem(FilterOption.interesting, 'Interesting'),
          _buildFilterItem(FilterOption.system, 'System'),
        ],
        onSelected: _applyFilter,
      ),
    );
  }

  PopupMenuItem<FilterOption> _buildFilterItem(FilterOption option, String title) {
    final isSelected = _currentFilter == option;
    return PopupMenuItem<FilterOption>(
      value: option,
      child: Row(
        children: [
          Icon(
            isSelected ? Icons.radio_button_checked : Icons.radio_button_unchecked,
            color: isSelected ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textTertiary,
            size: 16,
          ),
          const SizedBox(width: 8),
          Text(
            title,
            style: TextStyle(
              color: isSelected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  String _getFilterText() {
    switch (_currentFilter) {
      case FilterOption.interesting:
        return 'Interesting';
      case FilterOption.system:
        return 'System';
      case FilterOption.all:
        return 'All';
    }
  }

  Widget _buildMemoriesContent(MemoriesProvider provider) {
    if (provider.loading) {
      return _buildModernLoadingState();
    }

    if (provider.filteredMemories.isEmpty) {
      return _buildModernEmptyState(provider);
    }

    return _buildMemoriesList(provider);
  }

  Widget _buildModernLoadingState() {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: Colors.white.withOpacity(0.1),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.1),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _animationsInitialized
                ? AnimatedBuilder(
                    animation: _pulseController,
                    builder: (context, child) {
                      return Transform.scale(
                        scale: 1.0 + (_pulseAnimation.value * 0.1),
                        child: Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.purplePrimary,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: const CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            strokeWidth: 2,
                          ),
                        ),
                      );
                    },
                  )
                : Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.purplePrimary,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      strokeWidth: 2,
                    ),
                  ),
            const SizedBox(height: 16),
            Text(
              'Loading your memories...',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildModernEmptyState(MemoriesProvider provider) {
    Widget content = Container(
      padding: const EdgeInsets.all(40),
      margin: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: Colors.white.withOpacity(0.1),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
            blurRadius: 30,
            offset: const Offset(0, 15),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _animationsInitialized
              ? AnimatedBuilder(
                  animation: _pulseController,
                  builder: (context, child) {
                    return Transform.scale(
                      scale: 1.0 + (_pulseAnimation.value * 0.05),
                      child: Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Icon(
                          FontAwesomeIcons.brain,
                          size: 48,
                          color: ResponsiveHelper.purplePrimary,
                        ),
                      ),
                    );
                  },
                )
              : Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Icon(
                    FontAwesomeIcons.brain,
                    size: 48,
                    color: ResponsiveHelper.purplePrimary,
                  ),
                ),
          const SizedBox(height: 24),
          Text(
            provider.searchQuery.isEmpty && _selectedCategory == null ? '🧠 No memories yet' : '🔍 No memories found',
            style: TextStyle(
              color: ResponsiveHelper.textPrimary,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            provider.searchQuery.isEmpty && _selectedCategory == null ? 'Create your first memory to get started' : 'Try adjusting your search or filter',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: ResponsiveHelper.textSecondary,
              fontSize: 14,
              height: 1.5,
            ),
          ),
          if (provider.searchQuery.isEmpty && _selectedCategory == null) ...[
            const SizedBox(height: 24),
            Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () => _showMemoryDialog(context, provider),
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.purplePrimary,
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: [
                      BoxShadow(
                        color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                        blurRadius: 8,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Text(
                    'Add your first memory',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );

    return Center(
      child: _animationsInitialized
          ? FadeTransition(
              opacity: _fadeAnimation,
              child: content,
            )
          : content,
    );
  }

  Widget _buildMemoriesList(MemoriesProvider provider) {
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.only(left: 20, right: 20, bottom: 20),
      itemCount: provider.filteredMemories.length,
      itemBuilder: (context, index) {
        final memory = provider.filteredMemories[index];

        Widget memoryWidget = DesktopMemoryItem(
          memory: memory,
          provider: provider,
          onTap: _showQuickEditSheet,
        );

        return AnimatedContainer(
          duration: Duration(milliseconds: 300 + (index * 50)),
          curve: Curves.easeOutCubic,
          child: _animationsInitialized
              ? FadeTransition(
                  opacity: _fadeAnimation,
                  child: SlideTransition(
                    position: Tween<Offset>(
                      begin: Offset(0, 0.1 + (index * 0.02)),
                      end: Offset.zero,
                    ).animate(CurvedAnimation(
                      parent: _slideController,
                      curve: Interval(
                        (index * 0.1).clamp(0.0, 0.8),
                        1.0,
                        curve: Curves.easeOutCubic,
                      ),
                    )),
                    child: memoryWidget,
                  ),
                )
              : memoryWidget,
        );
      },
    );
  }

  void _showQuickEditSheet(BuildContext context, Memory memory, MemoriesProvider provider) {
    showDialog(
      context: context,
      builder: (context) => DesktopMemoryDialog(
        memory: memory,
        provider: provider,
      ),
    );
  }

  void _showMemoryDialog(BuildContext context, MemoriesProvider provider) {
    MixpanelManager().memoriesPageCreateMemoryBtn();
    showDialog(
      context: context,
      builder: (context) => DesktopMemoryDialog(
        provider: provider,
      ),
    );
  }

  void _showReviewSheet(BuildContext context, List<Memory> memories, MemoriesProvider existingProvider) async {
    if (memories.isEmpty || !mounted) return;
    // TODO: Implement desktop memory review sheet
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${memories.length} unreviewed memories found'),
        backgroundColor: ResponsiveHelper.purplePrimary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        duration: const Duration(milliseconds: 2000),
      ),
    );
  }

  void _showManagementSheet(BuildContext context, MemoriesProvider provider) {
    // TODO: Implement desktop memory management sheet
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Management options coming soon'),
        backgroundColor: ResponsiveHelper.purplePrimary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        duration: const Duration(milliseconds: 2000),
      ),
    );
  }
}
