import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/ui/organisms/desktop/action_item_desktop.dart';
import 'package:omi/desktop/pages/actions/widgets/desktop_action_item_form_dialog.dart';
import 'package:omi/ui/atoms/omi_button.dart';

class DesktopActionsPage extends StatefulWidget {
  const DesktopActionsPage({super.key});

  @override
  State<DesktopActionsPage> createState() => DesktopActionsPageState();
}

class DesktopActionsPageState extends State<DesktopActionsPage>
    with AutomaticKeepAliveClientMixin, TickerProviderStateMixin {
  @override
  bool get wantKeepAlive => true;

  final ScrollController _scrollController = ScrollController();

  late AnimationController _fadeController;
  late AnimationController _slideController;
  late AnimationController _pulseController;

  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _pulseAnimation;

  bool _animationsInitialized = false;

  String? _errorMessage;
  bool _hasNetworkError = false;
  bool _isReloading = false;
  late FocusNode _focusNode;

  // Tab state: 0 = To Do, 1 = Done, 2 = Snoozed
  int _selectedTabIndex = 0;

  void _requestFocusIfPossible() {
    if (mounted && _focusNode.canRequestFocus) {
      _focusNode.requestFocus();
    }
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
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
    _scrollController.addListener(_onScroll);
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
      MixpanelManager().actionItemsPageOpened();

      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      if (provider.actionItems.isEmpty) {
        provider.fetchActionItems(showShimmer: true);
      }

      _fadeController.forward();
      _slideController.forward();

      Future.delayed(const Duration(milliseconds: 100), () {
        _requestFocusIfPossible();
      });
    }).withPostFrameCallback();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    WidgetsBinding.instance.addPostFrameCallback((_) => _requestFocusIfPossible());
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
    return VisibilityDetector(
        key: const Key('desktop-actions-page'),
        onVisibilityChanged: (visibilityInfo) {
          if (visibilityInfo.visibleFraction > 0.1) {
            WidgetsBinding.instance.addPostFrameCallback((_) => _requestFocusIfPossible());
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
                if (!_focusNode.hasFocus) {
                  _focusNode.requestFocus();
                }
              },
              child: Consumer<ActionItemsProvider>(
                builder: (context, provider, _) {
                  // Get categorized items based on new logic
                  final todoItems = provider.todoItems;
                  final doneItems = provider.doneItems;
                  final snoozedItems = provider.snoozedItems;
                  final allItems = provider.actionItems;

                  // Get current tab items
                  final currentTabItems = _selectedTabIndex == 0
                      ? todoItems
                      : _selectedTabIndex == 1
                          ? doneItems
                          : snoozedItems;

                  return Stack(
                    children: [
                      Container(
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
                                    _buildHeader(todoItems, doneItems, snoozedItems),
                                    Expanded(
                                      child: _animationsInitialized
                                          ? FadeTransition(
                                              opacity: _fadeAnimation,
                                              child: SlideTransition(
                                                position: _slideAnimation,
                                                child: _buildActionsContent(provider, allItems, currentTabItems),
                                              ),
                                            )
                                          : _buildActionsContent(provider, allItems, currentTabItems),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
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
                                  'Loading action items...',
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

  Widget _buildHeader(List<ActionItemWithMetadata> todoItems, List<ActionItemWithMetadata> doneItems,
      List<ActionItemWithMetadata> snoozedItems) {
    return Container(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          // Title and create button row
          Row(
            children: [
              // Title section
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
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
                    SizedBox(height: 4),
                    Text(
                      'Tap to edit • Long press to select • Swipe for actions',
                      style: TextStyle(
                        color: ResponsiveHelper.textSecondary,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              // Create button
              OmiButton(
                label: 'Create',
                onPressed: _showCreateActionItemDialog,
                icon: FontAwesomeIcons.plus,
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Segmented Control - Full width like mobile
          Container(
            width: double.infinity,
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
              borderRadius: BorderRadius.circular(10),
            ),
            padding: const EdgeInsets.all(2),
            child: CupertinoSlidingSegmentedControl<int>(
              groupValue: _selectedTabIndex,
              onValueChanged: (int? value) {
                if (value != null) {
                  setState(() {
                    _selectedTabIndex = value;
                  });
                  HapticFeedback.selectionClick();

                  // Track tab change
                  final tabName = value == 0 ? 'To Do' : (value == 1 ? 'Done' : 'Snoozed');
                  MixpanelManager().actionItemTabChanged(tabName);
                }
              },
              backgroundColor: Colors.transparent,
              thumbColor: ResponsiveHelper.backgroundSecondary,
              padding: const EdgeInsets.all(0),
              children: {
                0: _buildTabLabel('To Do', todoItems.length),
                1: _buildTabLabel('Done', doneItems.length),
                2: _buildTabLabel('Snoozed', snoozedItems.length),
              },
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _showCreateActionItemDialog() async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => const DesktopActionItemFormDialog(),
    );

    if (result == true) {
      // Refresh the action items list
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      provider.forceRefreshActionItems();
    }
  }

  void _retryLoadingActionItems() {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    setState(() {
      _hasNetworkError = false;
      _errorMessage = null;
    });
    provider.fetchActionItems(showShimmer: true);
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

    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    await provider.forceRefreshActionItems();

    if (mounted) {
      setState(() {
        _isReloading = false;
      });
    }
  }

  Widget _buildTabLabel(String label, int count) {
    final int tabIndex = label == 'To Do' ? 0 : (label == 'Done' ? 1 : 2);
    final bool isSelected = _selectedTabIndex == tabIndex;

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w500,
              color: isSelected ? ResponsiveHelper.textPrimary : ResponsiveHelper.textSecondary,
            ),
          ),
          if (count > 0) ...[
            const SizedBox(width: 4),
            Text(
              '$count',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: isSelected ? ResponsiveHelper.textSecondary : ResponsiveHelper.textTertiary,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildActionsContent(
    ActionItemsProvider provider,
    List<ActionItemWithMetadata> allItems,
    List<ActionItemWithMetadata> currentTabItems,
  ) {
    if (_hasNetworkError && allItems.isEmpty) {
      return _buildErrorState();
    }

    if (provider.isLoading && allItems.isEmpty) {
      return _buildModernLoadingState();
    }

    if (allItems.isEmpty) {
      return _buildModernEmptyState();
    }

    return CustomScrollView(
      controller: _scrollController,
      slivers: [
        // Info banner for snoozed tab
        if (allItems.isNotEmpty && _selectedTabIndex == 2)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20.0, 0, 20.0, 12.0),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: ResponsiveHelper.textTertiary.withOpacity(0.3),
                    width: 1,
                  ),
                ),
                child: const Row(
                  children: [
                    Icon(
                      Icons.info_outline,
                      size: 16,
                      color: ResponsiveHelper.textTertiary,
                    ),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Old tasks are auto-snoozed after 3 days to keep your To Do list clean. You can still complete or delete them here.',
                        style: TextStyle(
                          color: ResponsiveHelper.textSecondary,
                          fontSize: 12,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),

        // Current Tab Items
        if (allItems.isNotEmpty && currentTabItems.isNotEmpty)
          _buildFlatView(currentTabItems, _selectedTabIndex == 1)
        else if (allItems.isNotEmpty && currentTabItems.isEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20.0),
              child: Container(
                height: 120,
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Center(
                  child: Text(
                    _getEmptyTabMessage(),
                    style: const TextStyle(
                      color: ResponsiveHelper.textSecondary,
                      fontSize: 14,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ),
          ),

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

        if (_hasNetworkError && allItems.isNotEmpty)
          SliverToBoxAdapter(
            child: Container(
              margin: const EdgeInsets.fromLTRB(20, 16, 20, 0),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.orange.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: Colors.orange.withOpacity(0.3),
                  width: 1,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    FontAwesomeIcons.triangleExclamation,
                    color: Colors.orange[300],
                    size: 16,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      _errorMessage ?? 'Some features may not work properly',
                      style: TextStyle(
                        color: Colors.orange[300],
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                  TextButton(
                    onPressed: _retryLoadingActionItems,
                    child: Text(
                      'Retry',
                      style: TextStyle(
                        color: Colors.orange[300],
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
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
      child: _buildFirstTimeEmptyState(),
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

  Widget _buildErrorState() {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(40),
        margin: const EdgeInsets.all(32),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: Colors.red.withOpacity(0.2),
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
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.red.withOpacity(0.1),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(
                FontAwesomeIcons.triangleExclamation,
                size: 48,
                color: Colors.red,
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'Unable to Load Action Items',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 20,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              _errorMessage ?? 'Please check your internet connection and try again.',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _retryLoadingActionItems,
              icon: const Icon(
                FontAwesomeIcons.arrowRotateRight,
                size: 16,
              ),
              label: const Text('Retry'),
              style: ElevatedButton.styleFrom(
                backgroundColor: ResponsiveHelper.purplePrimary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _getEmptyTabMessage() {
    switch (_selectedTabIndex) {
      case 0: // To Do
        return '🎉 All caught up!\nNo pending action items';
      case 1: // Done
        return 'No completed items yet';
      case 2: // Snoozed
        return '✅ No snoozed tasks\n\nOld tasks are auto-snoozed after 3 days to keep your To Do list clean';
      default:
        return 'No items';
    }
  }

  Widget _buildFlatView(List<ActionItemWithMetadata> items, bool showCompleted) {
    // For the new tab system, we don't need to filter by completion status
    // since the provider already returns the correct items for each tab
    final filteredItems = items;

    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          final item = filteredItems[index];

          Widget itemWidget = DesktopActionItem(
            actionItem: item,
            isSnoozedTab: _selectedTabIndex == 2,
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
}

extension PostFrameCallback on Function {
  void withPostFrameCallback() {
    WidgetsBinding.instance.addPostFrameCallback((_) => this());
  }
}
