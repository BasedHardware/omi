

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/functions.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/desktop_memory_item.dart';
import 'widgets/desktop_memory_dialog.dart';
import 'widgets/desktop_memory_management_dialog.dart';

import 'package:omi/ui/atoms/omi_search_input.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/molecules/omi_empty_state.dart';

enum FilterOption { interesting, system, manual, all }

class DesktopMemoriesPage extends StatefulWidget {
  const DesktopMemoriesPage({super.key});

  @override
  State<DesktopMemoriesPage> createState() => DesktopMemoriesPageState();
}

class DesktopMemoriesPageState extends State<DesktopMemoriesPage>
    with AutomaticKeepAliveClientMixin, TickerProviderStateMixin {
  @override
  bool get wantKeepAlive => true;

  final TextEditingController _searchController = TextEditingController();
  MemoryCategory? _selectedCategory;
  final ScrollController _scrollController = ScrollController();

  late AnimationController _fadeController;
  late AnimationController _slideController;
  late AnimationController _pulseController;

  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _pulseAnimation;

  bool _animationsInitialized = false;

  FilterOption _currentFilter = FilterOption.all;

  bool _isReloading = false;

  late FocusNode _focusNode;

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    _fadeController.dispose();
    _slideController.dispose();
    _pulseController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();

    _focusNode = FocusNode();

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
      await _handleRefresh();

      // Start animations
      _fadeController.forward();
      _slideController.forward();

      Future.delayed(const Duration(milliseconds: 100), () {
        if (mounted) {
          _focusNode.requestFocus();
        }
      });
    }).withPostFrameCallback();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _requestFocusIfPossible();
  }

  void _requestFocusIfPossible() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _focusNode.canRequestFocus) {
        _focusNode.requestFocus();
      }
    });
  }

  Future<void> _handleRefresh() async {
    final provider = context.read<MemoriesProvider>();
    await provider.init();

    await _applyFilter(_currentFilter);
  }

  Future<void> _applyFilter(FilterOption option) async {
    setState(() {
      _currentFilter = option;
      switch (option) {
        case FilterOption.interesting:
          _selectedCategory = MemoryCategory.interesting;
          break;
        case FilterOption.system:
          _selectedCategory = MemoryCategory.system;
          break;
        case FilterOption.manual:
          _selectedCategory = MemoryCategory.manual;
          break;
        case FilterOption.all:
          _selectedCategory = null;
          break;
      }
    });

    final provider = context.read<MemoriesProvider>();
    provider.clearCategoryFilter();

    if (!mounted) return;

    switch (option) {
      case FilterOption.interesting:
        provider.toggleCategoryFilter(MemoryCategory.interesting);
        MixpanelManager().memoriesFiltered('interesting');
        break;
      case FilterOption.system:
        provider.toggleCategoryFilter(MemoryCategory.system);
        MixpanelManager().memoriesFiltered('system');
        break;
      case FilterOption.manual:
        provider.toggleCategoryFilter(MemoryCategory.manual);
        MixpanelManager().memoriesFiltered('manual');
        break;
      case FilterOption.all:
        MixpanelManager().memoriesFiltered('all');
        break;
    }
  }

  Future<void> _handleReload() async {
    if (_isReloading) return;

    setState(() {
      _isReloading = true;
    });

    // Scroll to top
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        0,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }

    await _handleRefresh();

    if (mounted) {
      setState(() {
        _isReloading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return VisibilityDetector(
        key: const Key('desktop-memories-page'),
        onVisibilityChanged: (visibilityInfo) {
          if (visibilityInfo.visibleFraction > 0.1 && mounted) {
            _requestFocusIfPossible();
          }
        },
        child: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.keyR, meta: true): _handleReload,
          },
          child: Focus(
            focusNode: _focusNode,
            autofocus: true,
            child: GestureDetector(
              onTap: () {
                // Ensure focus is maintained when tapping on the widget
                if (!_focusNode.hasFocus) {
                  _focusNode.requestFocus();
                }
              },
              child: Consumer<MemoriesProvider>(
                builder: (context, provider, _) {
                  return Stack(
                    children: [
                      Container(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              ResponsiveHelper.backgroundPrimary,
                              ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
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
                                  color: Colors.white.withValues(alpha: 0.02),
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: Column(
                                  children: [
                                    _buildModernHeader(provider),

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
                      ),



                      // Loading overlay for CMD+R reload
                      if (_isReloading)
                        Container(
                          decoration: BoxDecoration(
                            color: Colors.black54,
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const CircularProgressIndicator(color: ResponsiveHelper.purplePrimary),
                                const SizedBox(height: 16),
                                Text(
                                  'Loading memories...',
                                  style: ResponsiveHelper(context).bodyLarge.copyWith(
                                        color: ResponsiveHelper.textPrimary,
                                      ),
                                ),
                              ],
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
            ),
          ),
        ));
  }

  Widget _buildAnimatedBackground() {
    if (!_animationsInitialized) {
      return Container(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: Alignment.topRight,
            radius: 2.0,
            colors: [
              ResponsiveHelper.purplePrimary.withValues(alpha: 0.05),
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
                ResponsiveHelper.purplePrimary.withValues(alpha: 0.05 + _pulseAnimation.value * 0.03),
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
          Expanded(
            child: OmiSearchInput(
              controller: _searchController,
              hint: 'Search memories...',
              onChanged: (value) {
                provider.setSearchQuery(value);
                if (value.isNotEmpty) {
                  MixpanelManager().memorySearched(value, provider.filteredMemories.length);
                }
              },
              onClear: () {
                _searchController.clear();
                provider.setSearchQuery('');
                MixpanelManager().memorySearchCleared(provider.memories.length);
              },
            ),
          ),
          const SizedBox(width: 12),
          _buildFilterDropdown(provider),
          const SizedBox(width: 12),
          OmiIconButton(
            icon: Icons.add,
            onPressed: () => _showMemoryDialog(context, provider),
            style: OmiIconButtonStyle.filled,
          ),
          const SizedBox(width: 8),
          OmiIconButton(
            icon: Icons.more_vert,
            onPressed: () => _showManagementSheet(context, provider),
            style: OmiIconButtonStyle.outline,
          ),
        ],
      ),
    );
  }

  Widget _buildFilterDropdown(MemoriesProvider provider) {
    return Container(
      height: 44,
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(12),
      ),
      child: PopupMenuButton<FilterOption>(
        color: ResponsiveHelper.backgroundSecondary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        offset: const Offset(0, 48),
        itemBuilder: (context) => [
          _buildFilterItem(FilterOption.all, 'All Memories'),
          _buildFilterItem(FilterOption.interesting, 'Interesting'),
          _buildFilterItem(FilterOption.system, 'System'),
          _buildFilterItem(FilterOption.manual, 'Manual'),
        ],
        onSelected: _applyFilter,
        child: Container(
          height: 44,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.filter_list,
                color: ResponsiveHelper.textSecondary,
                size: 16,
              ),
              const SizedBox(width: 6),
              Text(
                _getFilterText(),
                style: const TextStyle(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 12,
                ),
              ),
              const SizedBox(width: 6),
              const Icon(
                Icons.keyboard_arrow_down,
                color: ResponsiveHelper.textSecondary,
                size: 16,
              ),
            ],
          ),
        ),
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
      case FilterOption.manual:
        return 'Manual';
      case FilterOption.all:
        return 'All';
    }
  }

  Widget _buildMemoriesContent(MemoriesProvider provider) {
    if (provider.loading && provider.filteredMemories.isEmpty) {
      return _buildModernLoadingState();
    }

    if (provider.filteredMemories.isEmpty) {
      return RefreshIndicator(
        onRefresh: _handleRefresh,
        backgroundColor: ResponsiveHelper.backgroundTertiary,
        color: ResponsiveHelper.purplePrimary,
        child: Stack(
          children: [
            ListView(),
            _buildEmptyState(provider),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _handleRefresh,
      backgroundColor: ResponsiveHelper.backgroundTertiary,
      color: ResponsiveHelper.purplePrimary,
      child: _buildMemoriesList(provider),
    );
  }

  Widget _buildModernLoadingState() {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: Colors.white.withValues(alpha: 0.1),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.1),
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

  Widget _buildEmptyState(MemoriesProvider provider) {
    Widget content = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        OmiEmptyState(
          icon: FontAwesomeIcons.brain,
          title:
              provider.searchQuery.isEmpty && _selectedCategory == null ? '🧠 No memories yet' : '🔍 No memories found',
          message: provider.searchQuery.isEmpty && _selectedCategory == null
              ? 'Create your first memory to get started'
              : 'Try adjusting your search or filter',
          color: ResponsiveHelper.purplePrimary,
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
                      color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
                      blurRadius: 8,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: const Text(
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





  void _showManagementSheet(BuildContext context, MemoriesProvider provider) {
    showDialog(
      context: context,
      builder: (context) => DesktopMemoryManagementDialog(
        provider: provider,
      ),
    );
  }
}
