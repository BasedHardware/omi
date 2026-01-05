import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:provider/provider.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/desktop/pages/actions/widgets/desktop_action_item_form_dialog.dart';
import 'package:omi/ui/atoms/omi_button.dart';

enum TaskCategory { today, tomorrow, noDeadline, later }

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
  late AnimationController _pulseController;
  late Animation<double> _fadeAnimation;
  late Animation<double> _pulseAnimation;

  bool _animationsInitialized = false;
  bool _isReloading = false;
  late FocusNode _focusNode;

  // Track indent levels for each task (task id -> indent level 0-3)
  final Map<String, int> _indentLevels = {};

  // Show completed tasks
  bool _showCompleted = false;

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

    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat(reverse: true);

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _fadeController, curve: Curves.easeOutCubic),
    );

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

  // Categorize items by deadline
  Map<TaskCategory, List<ActionItemWithMetadata>> _categorizeItems(List<ActionItemWithMetadata> items) {
    final now = DateTime.now();
    final startOfTomorrow = DateTime(now.year, now.month, now.day + 1);
    final startOfDayAfterTomorrow = DateTime(now.year, now.month, now.day + 2);

    // Filter out old tasks without a future due date (older than 7 days)
    final sevenDaysAgo = now.subtract(const Duration(days: 7));

    final Map<TaskCategory, List<ActionItemWithMetadata>> categorized = {
      TaskCategory.today: [],
      TaskCategory.tomorrow: [],
      TaskCategory.noDeadline: [],
      TaskCategory.later: [],
    };

    for (var item in items) {
      // Skip completed items unless showing completed
      if (item.completed && !_showCompleted) continue;
      if (!item.completed && _showCompleted) continue;

      // Skip old tasks without a future due date (only for non-completed)
      if (!_showCompleted) {
        if (item.dueAt != null) {
          if (item.dueAt!.isBefore(sevenDaysAgo)) continue;
        } else {
          if (item.createdAt != null && item.createdAt!.isBefore(sevenDaysAgo)) continue;
        }
      }

      if (item.dueAt == null) {
        categorized[TaskCategory.noDeadline]!.add(item);
      } else {
        final dueDate = item.dueAt!;
        if (dueDate.isBefore(startOfTomorrow)) {
          categorized[TaskCategory.today]!.add(item);
        } else if (dueDate.isBefore(startOfDayAfterTomorrow)) {
          categorized[TaskCategory.tomorrow]!.add(item);
        } else {
          categorized[TaskCategory.later]!.add(item);
        }
      }
    }

    return categorized;
  }

  String _getCategoryTitle(TaskCategory category) {
    switch (category) {
      case TaskCategory.today:
        return 'Today';
      case TaskCategory.tomorrow:
        return 'Tomorrow';
      case TaskCategory.noDeadline:
        return 'No Deadline';
      case TaskCategory.later:
        return 'Later';
    }
  }

  DateTime? _getDefaultDueDateForCategory(TaskCategory category) {
    final now = DateTime.now();
    switch (category) {
      case TaskCategory.today:
        return DateTime(now.year, now.month, now.day, 23, 59);
      case TaskCategory.tomorrow:
        return DateTime(now.year, now.month, now.day + 1, 23, 59);
      case TaskCategory.noDeadline:
        return null;
      case TaskCategory.later:
        // Day after tomorrow
        return DateTime(now.year, now.month, now.day + 2, 23, 59);
    }
  }

  void _updateTaskCategory(ActionItemWithMetadata item, TaskCategory newCategory) {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final newDueDate = _getDefaultDueDateForCategory(newCategory);
    provider.updateActionItemDueDate(item, newDueDate);
  }

  int _getIndentLevel(String itemId) {
    return _indentLevels[itemId] ?? 0;
  }

  void _incrementIndent(String itemId) {
    setState(() {
      final current = _indentLevels[itemId] ?? 0;
      if (current < 3) {
        _indentLevels[itemId] = current + 1;
      }
    });
    HapticFeedback.lightImpact();
  }

  void _decrementIndent(String itemId) {
    setState(() {
      final current = _indentLevels[itemId] ?? 0;
      if (current > 0) {
        _indentLevels[itemId] = current - 1;
      }
    });
    HapticFeedback.lightImpact();
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
                final allItems = provider.actionItems;
                final categorizedItems = _categorizeItems(allItems);

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
                                  _buildHeader(),
                                  Expanded(
                                    child: _animationsInitialized
                                        ? FadeTransition(
                                            opacity: _fadeAnimation,
                                            child: _buildContent(provider, allItems, categorizedItems),
                                          )
                                        : _buildContent(provider, allItems, categorizedItems),
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
                                'Loading tasks...',
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
      ),
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

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
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
                      'Tasks',
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
                  'Swipe tasks to indent, drag between categories',
                  style: TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          // Show completed toggle
          MouseRegion(
            cursor: SystemMouseCursors.click,
            child: GestureDetector(
              onTap: () {
                setState(() {
                  _showCompleted = !_showCompleted;
                });
                HapticFeedback.lightImpact();
              },
              child: Container(
                padding: const EdgeInsets.all(8),
                margin: const EdgeInsets.only(right: 12),
                decoration: BoxDecoration(
                  color: _showCompleted
                      ? ResponsiveHelper.purplePrimary.withOpacity(0.2)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  _showCompleted ? Icons.check_circle : Icons.check_circle_outline,
                  color: _showCompleted ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textSecondary,
                  size: 20,
                ),
              ),
            ),
          ),
          OmiButton(
            label: 'Create',
            onPressed: () => _showCreateDialog(),
            icon: FontAwesomeIcons.plus,
          ),
        ],
      ),
    );
  }

  Future<void> _showCreateDialog({DateTime? defaultDueDate}) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => DesktopActionItemFormDialog(defaultDueDate: defaultDueDate),
    );

    if (result == true) {
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      provider.forceRefreshActionItems();
    }
  }

  Future<void> _handleReload() async {
    if (_isReloading) return;

    setState(() {
      _isReloading = true;
    });

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

  Widget _buildContent(
    ActionItemsProvider provider,
    List<ActionItemWithMetadata> allItems,
    Map<TaskCategory, List<ActionItemWithMetadata>> categorizedItems,
  ) {
    if (provider.isLoading && allItems.isEmpty) {
      return _buildLoadingState();
    }

    if (allItems.isEmpty && !_showCompleted) {
      return _buildEmptyState();
    }

    return CustomScrollView(
      controller: _scrollController,
      slivers: [
        const SliverPadding(padding: EdgeInsets.only(top: 8)),

        for (final category in TaskCategory.values)
          SliverToBoxAdapter(
            child: _buildCategorySection(
              category: category,
              items: categorizedItems[category] ?? [],
              provider: provider,
            ),
          ),

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

  Widget _buildCategorySection({
    required TaskCategory category,
    required List<ActionItemWithMetadata> items,
    required ActionItemsProvider provider,
  }) {
    final title = _getCategoryTitle(category);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
      child: DragTarget<ActionItemWithMetadata>(
        onWillAcceptWithDetails: (details) => true,
        onAcceptWithDetails: (details) {
          _updateTaskCategory(details.data, category);
        },
        builder: (context, candidateData, rejectedData) {
          final isHovering = candidateData.isNotEmpty;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            decoration: BoxDecoration(
              color: isHovering ? ResponsiveHelper.backgroundTertiary.withOpacity(0.5) : Colors.transparent,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                Padding(
                  padding: const EdgeInsets.fromLTRB(4, 12, 4, 8),
                  child: Row(
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          color: ResponsiveHelper.textPrimary,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const Spacer(),
                      if (items.isNotEmpty)
                        Text(
                          '${items.length}',
                          style: const TextStyle(
                            color: ResponsiveHelper.textTertiary,
                            fontSize: 14,
                          ),
                        ),
                    ],
                  ),
                ),

                // Task items
                ...items.map((item) => _buildTaskItem(item, provider)),

                // Spacing after section
                const SizedBox(height: 8),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildTaskItem(ActionItemWithMetadata item, ActionItemsProvider provider) {
    final indentLevel = _getIndentLevel(item.id);
    final indentWidth = indentLevel * 28.0;

    return LongPressDraggable<ActionItemWithMetadata>(
      data: item,
      feedback: Material(
        color: Colors.transparent,
        child: Container(
          width: 400,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary,
            borderRadius: BorderRadius.circular(12),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.3),
                blurRadius: 10,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Row(
            children: [
              _buildCheckbox(item.completed),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  item.description,
                  style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 14),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
      childWhenDragging: Opacity(
        opacity: 0.3,
        child: _buildTaskItemContent(item, provider, indentWidth),
      ),
      child: _buildTaskItemContent(item, provider, indentWidth),
    );
  }

  Widget _buildTaskItemContent(
    ActionItemWithMetadata item,
    ActionItemsProvider provider,
    double indentWidth,
  ) {
    final indentLevel = _getIndentLevel(item.id);

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onHorizontalDragEnd: (details) {
          if (details.primaryVelocity != null) {
            if (details.primaryVelocity! > 200) {
              _incrementIndent(item.id);
            } else if (details.primaryVelocity! < -200) {
              _decrementIndent(item.id);
            }
          }
        },
        child: InkWell(
          onTap: () => _showEditDialog(item),
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: EdgeInsets.only(left: 4 + indentWidth, right: 4, top: 6, bottom: 6),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                // Indent line
                if (indentLevel > 0)
                  Padding(
                    padding: const EdgeInsets.only(right: 10),
                    child: Container(
                      width: 1.5,
                      height: 20,
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.textTertiary,
                        borderRadius: BorderRadius.circular(1),
                      ),
                    ),
                  ),
                // Checkbox
                GestureDetector(
                  onTap: () async {
                    await provider.updateActionItemState(item, !item.completed);
                  },
                  child: _buildCheckbox(item.completed),
                ),
                const SizedBox(width: 12),
                // Task text
                Expanded(
                  child: Text(
                    item.description,
                    style: TextStyle(
                      color: item.completed ? ResponsiveHelper.textTertiary : ResponsiveHelper.textPrimary,
                      fontSize: 14,
                      decoration: item.completed ? TextDecoration.lineThrough : null,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCheckbox(bool isCompleted) {
    return Container(
      width: 20,
      height: 20,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: isCompleted ? Colors.amber : ResponsiveHelper.textTertiary,
          width: 2,
        ),
        color: isCompleted ? Colors.amber : Colors.transparent,
      ),
      child: isCompleted
          ? const Icon(Icons.check, size: 12, color: Colors.black)
          : null,
    );
  }

  Future<void> _showEditDialog(ActionItemWithMetadata item) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (context) => DesktopActionItemFormDialog(actionItem: item),
    );

    if (result == true) {
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      provider.forceRefreshActionItems();
    }
  }

  Widget _buildLoadingState() {
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
        ),
        child: const Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(
              valueColor: AlwaysStoppedAnimation<Color>(ResponsiveHelper.purplePrimary),
            ),
            SizedBox(height: 16),
            Text(
              'Loading tasks...',
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(40),
        margin: const EdgeInsets.all(32),
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: Colors.white.withOpacity(0.1),
            width: 1,
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
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
              'No Tasks Yet',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 20,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Tasks from your conversations will appear here.\nClick Create to add one manually.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

extension PostFrameCallback on Function {
  void withPostFrameCallback() {
    WidgetsBinding.instance.addPostFrameCallback((_) => this());
  }
}
