import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';

import 'package:omi/ui/organisms/action_item.dart';
import 'package:omi/pages/action_items/widgets/action_item_filter_sheet.dart';
import 'widgets/desktop_action_group.dart';

class DesktopActionsPage extends StatefulWidget {
  const DesktopActionsPage({super.key});

  @override
  State<DesktopActionsPage> createState() => DesktopActionsPageState();
}

class DesktopActionsPageState extends State<DesktopActionsPage>
    with AutomaticKeepAliveClientMixin, TickerProviderStateMixin {
  @override
  bool get wantKeepAlive => true;

  bool _showGroupedView = false;
  final ScrollController _scrollController = ScrollController();

  late AnimationController _fadeController;
  late AnimationController _slideController;
  late AnimationController _pulseController;

  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _pulseAnimation;

  bool _animationsInitialized = false;

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    _fadeController.dispose();
    _slideController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);

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

    _animationsInitialized = true;

    (() async {
      MixpanelManager().actionItemsPageOpened();

      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      if (provider.actionItems.isEmpty) {
        provider.fetchActionItems(showShimmer: true);
      }

      _fadeController.forward();
      _slideController.forward();
    }).withPostFrameCallback();
  }

  void _onScroll() {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      if (!provider.isFetching && provider.hasMore) {
        provider.loadMoreActionItems();
      }
    }
  }



  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, _) {
        // Get incomplete and complete items
        final incompleteItems = provider.incompleteItems;
        final completedItems = provider.completedItems;
        final allItems = provider.actionItems;

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
                _buildAnimatedBackground(),
                Container(
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.02),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Column(
                    children: [
                      _buildHeader(incompleteItems),
                      Expanded(
                        child: _animationsInitialized
                            ? FadeTransition(
                                opacity: _fadeAnimation,
                                child: SlideTransition(
                                  position: _slideAnimation,
                                  child: _buildActionsContent(provider, allItems, incompleteItems, completedItems),
                                ),
                              )
                            : _buildActionsContent(provider, allItems, incompleteItems, completedItems),
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

  Widget _buildHeader(List<ActionItemWithMetadata> incompleteItems) {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        final incompleteCount = incompleteItems.length;
        final hasActiveFilter = provider.selectedStartDate != null || provider.selectedEndDate != null;

        return Container(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              Row(
                children: [
                  // Title section
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Row(
                          children: [
                            Icon(
                              FontAwesomeIcons.listCheck,
                              color: ResponsiveHelper.textSecondary,
                              size: 18,
                            ),
                            SizedBox(width: 12),
                            Text(
                              'Action Items',
                              style: TextStyle(
                                color: ResponsiveHelper.textPrimary,
                                fontSize: 20,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '$incompleteCount pending tasks',
                          style: const TextStyle(
                            color: ResponsiveHelper.textSecondary,
                            fontSize: 14,
                          ),
                        ),
                      ],
                    ),
                  ),

                  // Control buttons
                  Row(
                    children: [
                      // Date Filter Button
                      Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: () => ActionItemFilterSheet.show(context),
                          borderRadius: BorderRadius.circular(12),
                          child: Container(
                            height: 44,
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: hasActiveFilter
                                  ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                                  : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                              borderRadius: BorderRadius.circular(12),
                              border: hasActiveFilter
                                  ? Border.all(
                                      color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                                      width: 1,
                                    )
                                  : null,
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  FontAwesomeIcons.calendarDays,
                                  color: hasActiveFilter 
                                    ? ResponsiveHelper.purplePrimary 
                                    : ResponsiveHelper.textSecondary,
                                  size: 16,
                                ),
                                if (hasActiveFilter) ...[
                                  const SizedBox(width: 6),
                                  Container(
                                    width: 6,
                                    height: 6,
                                    decoration: const BoxDecoration(
                                      color: ResponsiveHelper.purplePrimary,
                                      shape: BoxShape.circle,
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      // View toggle button
                      Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: () {
                            setState(() {
                              _showGroupedView = !_showGroupedView;
                            });
                            MixpanelManager().actionItemsViewToggled(_showGroupedView);
                          },
                          borderRadius: BorderRadius.circular(12),
                          child: Container(
                            height: 44,
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: _showGroupedView
                                  ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                                  : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                              borderRadius: BorderRadius.circular(12),
                              border: _showGroupedView
                                  ? Border.all(
                                      color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                                      width: 1,
                                    )
                                  : null,
                            ),
                            child: Icon(
                              _showGroupedView ? FontAwesomeIcons.layerGroup : FontAwesomeIcons.list,
                              color: _showGroupedView ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                              size: 16,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              // Filter status indicator
              if (hasActiveFilter) ...[
                const SizedBox(height: 12),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.purplePrimary.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                      width: 1,
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        FontAwesomeIcons.filter,
                        size: 12,
                        color: ResponsiveHelper.purplePrimary.withOpacity(0.8),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        _getDateFilterDescription(provider),
                        style: TextStyle(
                          color: ResponsiveHelper.purplePrimary.withOpacity(0.9),
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const Spacer(),
                      Material(
                        color: Colors.transparent,
                        child: InkWell(
                          onTap: () {
                            provider.clearDateFilter();
                            MixpanelManager().actionItemsDateFilterCleared();
                          },
                          borderRadius: BorderRadius.circular(12),
                          child: Padding(
                            padding: const EdgeInsets.all(4),
                            child: Icon(
                              FontAwesomeIcons.xmark,
                              size: 10,
                              color: ResponsiveHelper.purplePrimary.withOpacity(0.8),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _buildActionsContent(
    ActionItemsProvider provider,
    List<ActionItemWithMetadata> allItems,
    List<ActionItemWithMetadata> incompleteItems,
    List<ActionItemWithMetadata> completedItems,
  ) {
    if (provider.isLoading && allItems.isEmpty) {
      return _buildModernLoadingState();
    }

    if (allItems.isEmpty) {
      return _buildModernEmptyState();
    }

    return CustomScrollView(
      controller: _scrollController,
      slivers: [
        // Pending tasks section
        if (incompleteItems.isNotEmpty)
          _showGroupedView ? _buildGroupedView(incompleteItems, false) : _buildFlatView(incompleteItems, false),

        // Completed tasks section
        if (completedItems.isNotEmpty) ...[
          SliverToBoxAdapter(
            child: Container(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
              child: Row(
                children: [
                  const Text(
                    'Completed',
                    style: TextStyle(
                      color: ResponsiveHelper.textPrimary,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      '${completedItems.length}',
                      style: const TextStyle(
                        color: ResponsiveHelper.textTertiary,
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          _showGroupedView ? _buildGroupedView(completedItems, true) : _buildFlatView(completedItems, true),
        ] else ...[
          SliverToBoxAdapter(
            child: Container(
              margin: const EdgeInsets.fromLTRB(20, 24, 20, 0),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Row(
                children: [
                  Icon(
                    FontAwesomeIcons.circleCheck,
                    color: ResponsiveHelper.textTertiary,
                    size: 16,
                  ),
                  SizedBox(width: 12),
                  Text(
                    'No completed items yet',
                    style: TextStyle(
                      color: ResponsiveHelper.textTertiary,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],

        // Loading indicator for pagination
        if (provider.isFetching)
          SliverToBoxAdapter(
            child: Container(
              padding: const EdgeInsets.all(16),
              child: const Center(
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
                ),
              ),
            ),
          ),

        const SliverPadding(padding: EdgeInsets.only(bottom: 20)),
      ],
    );
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
            const Text(
              'Loading your action items...',
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

  Widget _buildModernEmptyState() {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        final hasActiveFilters = provider.selectedStartDate != null || provider.selectedEndDate != null;
        
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
          child: hasActiveFilters 
            ? _buildFilteredEmptyState(provider)
            : _buildFirstTimeEmptyState(),
        );

        return Center(
          child: _animationsInitialized
              ? FadeTransition(
                  opacity: _fadeAnimation,
                  child: content,
                )
              : content,
        );
      },
    );
  }

  Widget _buildFilteredEmptyState(ActionItemsProvider provider) {
    return Column(
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
                      child: const Icon(
                        FontAwesomeIcons.calendarXmark,
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
                child: const Icon(
                  FontAwesomeIcons.calendarXmark,
                  size: 48,
                  color: ResponsiveHelper.purplePrimary,
                ),
              ),
        const SizedBox(height: 24),
        const Text(
          'No Action Items Found',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          _getFilterEmptyDescription(provider),
          textAlign: TextAlign.center,
          style: const TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 14,
            height: 1.5,
          ),
        ),
        const SizedBox(height: 24),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _buildActionButton(
              icon: FontAwesomeIcons.sliders,
              label: 'Adjust Filter',
              onPressed: () => ActionItemFilterSheet.show(context),
              isPrimary: true,
            ),
            const SizedBox(width: 12),
            _buildActionButton(
              icon: FontAwesomeIcons.xmark,
              label: 'Clear Filter',
              onPressed: () {
                provider.clearDateFilter();
                MixpanelManager().actionItemsDateFilterCleared();
              },
              isPrimary: false,
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildFirstTimeEmptyState() {
    return Column(
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
                      child: const Icon(
                        FontAwesomeIcons.circleCheck,
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
                child: const Icon(
                  FontAwesomeIcons.circleCheck,
                  size: 48,
                  color: ResponsiveHelper.purplePrimary,
                ),
              ),
        const SizedBox(height: 24),
        const Text(
          '✅ No Action Items',
          style: TextStyle(
            color: ResponsiveHelper.textPrimary,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Tasks and to-dos from your conversations will appear here once they are created.',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: ResponsiveHelper.textSecondary,
            fontSize: 14,
            height: 1.5,
          ),
        ),
      ],
    );
  }

  Widget _buildActionButton({
    required IconData icon,
    required String label,
    required VoidCallback onPressed,
    required bool isPrimary,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          decoration: BoxDecoration(
            color: isPrimary 
              ? ResponsiveHelper.purplePrimary
              : ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: isPrimary 
                ? ResponsiveHelper.purplePrimary.withOpacity(0.5)
                : ResponsiveHelper.backgroundTertiary,
              width: 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                size: 14,
                color: isPrimary ? Colors.white : ResponsiveHelper.textSecondary,
              ),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(
                  color: isPrimary ? Colors.white : ResponsiveHelper.textSecondary,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildGroupedView(List<ActionItemWithMetadata> items, bool showCompleted) {
    // Group items by conversation title
    final Map<String, List<ActionItemWithMetadata>> groupedItems = {};
    for (final item in items) {
      if (item.completed == showCompleted) {
        groupedItems.putIfAbsent(item.conversationTitle, () => []).add(item);
      }
    }

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          final conversationTitle = groupedItems.keys.elementAt(index);
          final conversationItems = groupedItems[conversationTitle]!;

          Widget groupWidget = DesktopActionGroup(
            conversationTitle: conversationTitle,
            actionItems: conversationItems,
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
                      child: groupWidget,
                    ),
                  )
                : groupWidget,
          );
        },
        childCount: groupedItems.length,
      ),
    );
  }

  Widget _buildFlatView(List<ActionItemWithMetadata> items, bool showCompleted) {
    final filteredItems = items.where((item) => item.completed == showCompleted).toList();

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          final item = filteredItems[index];

          Widget itemWidget = DesktopActionItem(
            actionItem: item,
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
                      child: itemWidget,
                    ),
                  )
                : itemWidget,
          );
        },
        childCount: filteredItems.length,
      ),
    );
  }

  String _getDateFilterDescription(ActionItemsProvider provider) {
    final startDate = provider.selectedStartDate;
    final endDate = provider.selectedEndDate;
    
    if (startDate != null && endDate != null) {
      // Check if it's today
      final now = DateTime.now();
      final todayStart = DateTime(now.year, now.month, now.day);
      final todayEnd = DateTime(now.year, now.month, now.day, 23, 59, 59);
      
      if (_isSameDay(startDate, todayStart) && _isSameDay(endDate, todayEnd)) {
        return 'Filtered by Today';
      }
      
      // Check if it's yesterday
      final yesterday = now.subtract(const Duration(days: 1));
      final yesterdayStart = DateTime(yesterday.year, yesterday.month, yesterday.day);
      final yesterdayEnd = DateTime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59);
      
      if (_isSameDay(startDate, yesterdayStart) && _isSameDay(endDate, yesterdayEnd)) {
        return 'Filtered by Yesterday';
      }
      
      // Check if it's this week
      final startOfWeek = now.subtract(Duration(days: now.weekday - 1));
      final startOfWeekFormatted = DateTime(startOfWeek.year, startOfWeek.month, startOfWeek.day);
      
      if (_isSameDay(startDate, startOfWeekFormatted) && _isSameDay(endDate, now)) {
        return 'Filtered by This Week';
      }
      
      // Check if it's this month
      final startOfMonth = DateTime(now.year, now.month, 1);
      
      if (_isSameDay(startDate, startOfMonth) && _isSameDay(endDate, now)) {
        return 'Filtered by This Month';
      }
      
      // Default: show date range
      return 'Filtered: ${_formatDate(startDate)} - ${_formatDate(endDate)}';
    } else if (startDate != null) {
      return 'Filtered from ${_formatDate(startDate)}';
    } else if (endDate != null) {
      return 'Filtered until ${_formatDate(endDate)}';
    }
    
    return 'Date filter active';
  }

  bool _isSameDay(DateTime date1, DateTime date2) {
    return date1.year == date2.year && 
           date1.month == date2.month && 
           date1.day == date2.day;
  }

  String _formatDate(DateTime date) {
    return '${date.day}/${date.month}/${date.year}';
  }

  String _formatDateForDisplay(DateTime date) {
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${months[date.month - 1]} ${date.day}, ${date.year}';
  }

  String _getFilterEmptyDescription(ActionItemsProvider provider) {
    final startDate = provider.selectedStartDate;
    final endDate = provider.selectedEndDate;
    
    if (startDate != null && endDate != null) {
      final daysDiff = endDate.difference(startDate).inDays;
      if (daysDiff == 0) {
        return 'No action items were created on ${_formatDateForDisplay(startDate)}. Try expanding your date range or clearing the filter.';
      }
      return 'No action items found in the selected ${daysDiff + 1}-day period. Try adjusting your date range for more results.';
    } else if (startDate != null) {
      return 'No action items found from ${_formatDateForDisplay(startDate)} onwards. Try selecting a different start date.';
    } else if (endDate != null) {
      return 'No action items found until ${_formatDateForDisplay(endDate)}. Try extending the end date or clearing the filter.';
    }
    
    return 'No action items match your current filter criteria. Try adjusting your settings.';
  }
}



extension PostFrameCallback on Function {
  void withPostFrameCallback() {
    WidgetsBinding.instance.addPostFrameCallback((_) => this());
  }
}
