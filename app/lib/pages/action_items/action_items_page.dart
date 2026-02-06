import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'widgets/action_item_form_sheet.dart';

// Re-export Goal from goals.dart for use in this file
export 'package:omi/backend/http/api/goals.dart' show Goal;

enum TaskCategory { today, tomorrow, noDeadline, later }

class ActionItemsPage extends StatefulWidget {
  final VoidCallback? onAddGoal;

  const ActionItemsPage({super.key, this.onAddGoal});

  @override
  State<ActionItemsPage> createState() => _ActionItemsPageState();
}

class _ActionItemsPageState extends State<ActionItemsPage> with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();
  final AppReviewService _appReviewService = AppReviewService();

  // Track indent levels for each task (task id -> indent level 0-3)
  final Map<String, int> _indentLevels = {};

  // Task -> goal mapping
  final Map<String, String> _taskGoalLinks = {};

  // Track custom order for each category (category -> list of item ids)
  final Map<TaskCategory, List<String>> _categoryOrder = {};

  // Track the item being hovered over during drag
  String? _hoveredItemId;
  bool _hoverAbove = false; // true = insert above, false = insert below

  @override
  bool get wantKeepAlive => true;

  void scrollToTop() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        0,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }
  }

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    _loadCategoryOrder();
    _loadTaskGoalLinks();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      MixpanelManager().actionItemsPageOpened();
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      if (provider.actionItems.isEmpty) {
        provider.fetchActionItems(showShimmer: true);
      }
    });
  }

  void _loadCategoryOrder() {
    final savedOrder = SharedPreferencesUtil().taskCategoryOrder;
    setState(() {
      for (final entry in savedOrder.entries) {
        try {
          final category = TaskCategory.values.firstWhere(
            (c) => c.name == entry.key,
            orElse: () => TaskCategory.noDeadline,
          );
          _categoryOrder[category] = entry.value;
        } catch (_) {}
      }
    });
  }

  void _loadTaskGoalLinks() {
    final savedLinks = SharedPreferencesUtil().taskGoalLinks;
    setState(() {
      _taskGoalLinks
        ..clear()
        ..addAll(savedLinks);
    });
    // Prune orphaned links after loading
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _pruneTaskGoalLinks();
    });
  }

  /// Remove task-goal links where the goal no longer exists
  void _pruneTaskGoalLinks() {
    final goals = Provider.of<GoalsProvider>(context, listen: false).goals;
    if (goals.isEmpty) return;
    final goalIds = goals.map((goal) => goal.id).toSet();
    final removed = _taskGoalLinks.keys.where((taskId) => !goalIds.contains(_taskGoalLinks[taskId])).toList();
    if (removed.isEmpty) return;
    for (final taskId in removed) {
      _taskGoalLinks.remove(taskId);
    }
    SharedPreferencesUtil().taskGoalLinks = Map<String, String>.from(_taskGoalLinks);
  }

  void _attachTaskToGoal(String taskId, String goalId) {
    setState(() {
      _taskGoalLinks[taskId] = goalId;
    });
    SharedPreferencesUtil().taskGoalLinks = Map<String, String>.from(_taskGoalLinks);
    HapticFeedback.lightImpact();
  }

  String? _getGoalTitleForTask(ActionItemWithMetadata item) {
    final goalId = _taskGoalLinks[item.id];
    if (goalId == null) return null;
    final goals = Provider.of<GoalsProvider>(context, listen: false).goals;
    for (final goal in goals) {
      if (goal.id == goalId) return goal.title;
    }
    return null;
  }

  void _saveCategoryOrder() {
    final Map<String, List<String>> toSave = {};
    for (final entry in _categoryOrder.entries) {
      toSave[entry.key.name] = entry.value;
    }
    SharedPreferencesUtil().taskCategoryOrder = toSave;
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      if (!provider.isFetching && provider.hasMore) {
        provider.loadMoreActionItems();
      }
    }
  }

  Future<void> _onActionItemCompleted() async {
    MixpanelManager().actionItemCompleted(fromTab: 'Tasks');

    final hasCompletedFirst = await _appReviewService.hasCompletedFirstActionItem();

    if (!hasCompletedFirst) {
      await _appReviewService.markFirstActionItemCompleted();

      if (mounted) {
        await _appReviewService.showReviewPromptIfNeeded(context, isProcessingFirstConversation: false);
      }
    }
  }

  void _showCreateActionItemSheet({DateTime? defaultDueDate}) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => ActionItemFormSheet(defaultDueDate: defaultDueDate),
    );
  }

  void _showCreateGoalSheet() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (sheetContext) => _GoalCreateSheet(
        onSave: (title, current, target) async {
          // Create goal via provider
          final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
          final created = await goalsProvider.createGoal(
            title: title,
            goalType: 'numeric',
            targetValue: target,
            currentValue: current,
          );
          if (created != null) {
            MixpanelManager()
                .goalCreated(goalId: created.id, titleLength: title.length, targetValue: target, source: 'tasks_page');
          }
        },
      ),
    );
  }

  Widget _buildFab() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 48.0),
      child: FloatingActionButton(
        heroTag: 'action_items_fab',
        onPressed: () {
          HapticFeedback.lightImpact();
          _showCreateActionItemSheet(
            defaultDueDate: _getDefaultDueDateForCategory(TaskCategory.today),
          );
        },
        backgroundColor: Colors.deepPurple,
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }

  // Categorize items by deadline
  Map<TaskCategory, List<ActionItemWithMetadata>> _categorizeItems(
      List<ActionItemWithMetadata> items, bool showCompleted) {
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
      if (item.completed && !showCompleted) continue;
      if (!item.completed && showCompleted) continue;

      // Skip old tasks without a future due date (only for non-completed)
      if (!showCompleted) {
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

  String _getCategoryTitle(BuildContext context, TaskCategory category) {
    switch (category) {
      case TaskCategory.today:
        return context.l10n.today;
      case TaskCategory.tomorrow:
        return context.l10n.tomorrow;
      case TaskCategory.noDeadline:
        return context.l10n.tasksNoDeadline;
      case TaskCategory.later:
        return context.l10n.tasksLater;
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

  // Get ordered items for a category, respecting custom order
  List<ActionItemWithMetadata> _getOrderedItems(
    TaskCategory category,
    List<ActionItemWithMetadata> items,
  ) {
    final order = _categoryOrder[category];
    if (order == null || order.isEmpty) {
      return items;
    }

    // Sort items based on custom order, new items go at the end
    final orderedItems = <ActionItemWithMetadata>[];
    final itemMap = {for (var item in items) item.id: item};

    // Add items in custom order
    for (final id in order) {
      if (itemMap.containsKey(id)) {
        orderedItems.add(itemMap[id]!);
        itemMap.remove(id);
      }
    }

    // Add any remaining items (new ones not in custom order)
    orderedItems.addAll(itemMap.values);

    return orderedItems;
  }

  // Reorder item within category
  void _reorderItemInCategory(
    ActionItemWithMetadata draggedItem,
    String targetItemId,
    bool insertAbove,
    TaskCategory category,
    List<ActionItemWithMetadata> categoryItems,
  ) {
    setState(() {
      // Initialize category order if needed
      if (!_categoryOrder.containsKey(category)) {
        _categoryOrder[category] = categoryItems.map((i) => i.id).toList();
      }

      final order = _categoryOrder[category]!;

      // Remove dragged item from its current position
      order.remove(draggedItem.id);

      // Find target position
      final targetIndex = order.indexOf(targetItemId);
      if (targetIndex != -1) {
        // Insert above or below target
        final insertIndex = insertAbove ? targetIndex : targetIndex + 1;
        order.insert(insertIndex, draggedItem.id);
      } else {
        // Target not found, add at end
        order.add(draggedItem.id);
      }

      // Clear hover state
      _hoveredItemId = null;
    });
    _saveCategoryOrder();
    HapticFeedback.mediumImpact();
  }

  // Delete task with swipe
  Future<void> _deleteTask(ActionItemWithMetadata item) async {
    HapticFeedback.mediumImpact();
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    await provider.deleteActionItem(item);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        final showCompleted = provider.showCompletedView;
        final categorizedItems = _categorizeItems(provider.actionItems, showCompleted);

        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          floatingActionButton: _buildFab(),
          body: GestureDetector(
            onTap: () {},
            child: RefreshIndicator(
              onRefresh: () async {
                HapticFeedback.mediumImpact();
                return provider.forceRefreshActionItems();
              },
              color: Colors.deepPurple,
              backgroundColor: Colors.white,
              child: provider.isLoading && provider.actionItems.isEmpty
                  ? _buildLoadingState()
                  : categorizedItems.values.every((l) => l.isEmpty)
                      ? _buildEmptyTasksList()
                      : _buildTasksList(categorizedItems, provider),
            ),
          ),
        );
      },
    );
  }

  Widget _buildLoadingState() {
    return const Center(
      child: CircularProgressIndicator(color: Colors.deepPurple),
    );
  }

  Widget _buildEmptyTasksList() {
    return CustomScrollView(
      controller: _scrollController,
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        const SliverPadding(padding: EdgeInsets.only(top: 12)),
        SliverToBoxAdapter(
          child: _buildGoalsRow(),
        ),
        const SliverPadding(padding: EdgeInsets.only(top: 24)),
        SliverToBoxAdapter(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 80,
                    height: 80,
                    decoration: BoxDecoration(
                      color: Colors.deepPurple.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: Icon(
                      Icons.check_circle_outline,
                      size: 40,
                      color: Colors.deepPurple.withOpacity(0.6),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    context.l10n.noTasksYet,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    context.l10n.tasksEmptyStateMessage,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.grey[400],
                      fontSize: 16,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SliverPadding(padding: EdgeInsets.only(bottom: 100)),
      ],
    );
  }

  Widget _buildTasksList(
    Map<TaskCategory, List<ActionItemWithMetadata>> categorizedItems,
    ActionItemsProvider provider,
  ) {
    return CustomScrollView(
      controller: _scrollController,
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        const SliverPadding(padding: EdgeInsets.only(top: 12)),
        SliverToBoxAdapter(
          child: _buildGoalsRow(),
        ),
        const SliverPadding(padding: EdgeInsets.only(top: 6)),

        // Build each category section (skip empty ones)
        for (final category in TaskCategory.values)
          if ((categorizedItems[category] ?? []).isNotEmpty)
            SliverToBoxAdapter(
              child: _buildCategorySection(
                category: category,
                items: categorizedItems[category] ?? [],
                provider: provider,
              ),
            ),

        // Bottom padding
        const SliverPadding(padding: EdgeInsets.only(bottom: 100)),
      ],
    );
  }

  Widget _buildGoalsRow() {
    return Consumer<GoalsProvider>(
      builder: (context, goalsProvider, child) {
        if (goalsProvider.isLoading) {
          return const SizedBox.shrink();
        }

        final goals = goalsProvider.goals;

        // If no goals, don't show anything
        if (goals.isEmpty) {
          return const SizedBox.shrink();
        }

        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 12, 4, 8),
                child: Row(
                  children: [
                    Text(
                      context.l10n.goals,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const Spacer(),
                    if (goals.length < 3)
                      GestureDetector(
                        onTap: () {
                          HapticFeedback.lightImpact();
                          MixpanelManager().track('Add Goal Clicked from Tasks Page');
                          _showCreateGoalSheet();
                        },
                        child: Container(
                          width: 32,
                          height: 32,
                          decoration: BoxDecoration(
                            color: Colors.grey.withValues(alpha: 0.12),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            Icons.add,
                            size: 18,
                            color: Colors.grey[400],
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              // Goal items
              ...goals.map((goal) => _buildGoalItem(goal)),
              // Spacing after section
              const SizedBox(height: 8),
            ],
          ),
        );
      },
    );
  }

  Widget _buildGoalDropTile(Goal? goal) {
    return DragTarget<ActionItemWithMetadata>(
      onWillAcceptWithDetails: (details) => goal != null,
      onAcceptWithDetails: (details) {
        if (goal == null) return;
        MixpanelManager().taskDraggedToGoal(taskId: details.data.id, goalId: goal.id);
        _attachTaskToGoal(details.data.id, goal.id);
      },
      builder: (context, candidateData, rejectedData) {
        final isHovering = candidateData.isNotEmpty && goal != null;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          height: 64,
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(goal == null ? 0.04 : 0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: isHovering ? Colors.white.withOpacity(0.5) : Colors.white.withOpacity(0.08),
              width: 1,
            ),
          ),
          child: Center(
            child: Text(
              goal?.title ?? '',
              textAlign: TextAlign.center,
              maxLines: 3,
              style: TextStyle(
                color: goal == null ? Colors.white.withOpacity(0.2) : Colors.white.withOpacity(0.9),
                fontSize: 12,
                fontWeight: FontWeight.w500,
                height: 1.2,
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildCategorySection({
    required TaskCategory category,
    required List<ActionItemWithMetadata> items,
    required ActionItemsProvider provider,
  }) {
    final title = _getCategoryTitle(context, category);
    final orderedItems = _getOrderedItems(category, items);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: DragTarget<ActionItemWithMetadata>(
        onWillAcceptWithDetails: (details) => true,
        onAcceptWithDetails: (details) {
          // Only change category if dropped on empty area (not on a specific item)
          if (_hoveredItemId == null) {
            _updateTaskCategory(details.data, category);
          }
        },
        builder: (context, candidateData, rejectedData) {
          final isHovering = candidateData.isNotEmpty && _hoveredItemId == null;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            decoration: BoxDecoration(
              color: isHovering ? const Color(0xFF252528) : Colors.transparent,
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
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const Spacer(),
                      if (orderedItems.isNotEmpty)
                        Text(
                          '${orderedItems.length}',
                          style: TextStyle(
                            color: Colors.grey[600],
                            fontSize: 14,
                          ),
                        ),
                    ],
                  ),
                ),

                // Drop zone for first position
                if (orderedItems.isNotEmpty)
                  _buildFirstPositionDropZone(category, orderedItems, candidateData.isNotEmpty),

                // Task items
                ...orderedItems.map((item) => _buildTaskItem(
                      item,
                      provider,
                      category: category,
                      categoryItems: orderedItems,
                    )),

                // Spacing after section
                const SizedBox(height: 8),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildFirstPositionDropZone(
    TaskCategory category,
    List<ActionItemWithMetadata> categoryItems,
    bool isDragging,
  ) {
    final isHoveredFirst = _hoveredItemId == '_first_${category.name}';

    return DragTarget<ActionItemWithMetadata>(
      onWillAcceptWithDetails: (details) {
        // Don't accept if it's already the first item
        if (categoryItems.isNotEmpty && details.data.id == categoryItems.first.id) {
          return false;
        }
        return true;
      },
      onAcceptWithDetails: (details) {
        final draggedItem = details.data;

        // Insert at first position
        _reorderItemToFirst(draggedItem, category, categoryItems);

        // Also update category if different
        final draggedCategory = _getCategoryForItem(draggedItem);
        if (draggedCategory != category) {
          _updateTaskCategory(draggedItem, category);
        }
      },
      onMove: (details) {
        if (_hoveredItemId != '_first_${category.name}') {
          setState(() {
            _hoveredItemId = '_first_${category.name}';
          });
        }
      },
      onLeave: (data) {
        if (_hoveredItemId == '_first_${category.name}') {
          setState(() {
            _hoveredItemId = null;
          });
        }
      },
      builder: (context, candidateData, rejectedData) {
        final showIndicator = isHoveredFirst && candidateData.isNotEmpty;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          height: showIndicator ? 6 : (isDragging ? 20 : 4),
          margin: const EdgeInsets.symmetric(horizontal: 4),
          decoration: BoxDecoration(
            color: showIndicator ? Colors.deepPurple : Colors.transparent,
            borderRadius: BorderRadius.circular(2),
          ),
        );
      },
    );
  }

  void _reorderItemToFirst(
    ActionItemWithMetadata draggedItem,
    TaskCategory category,
    List<ActionItemWithMetadata> categoryItems,
  ) {
    setState(() {
      // Initialize category order if needed
      if (!_categoryOrder.containsKey(category)) {
        _categoryOrder[category] = categoryItems.map((i) => i.id).toList();
      }

      final order = _categoryOrder[category]!;

      // Remove dragged item from its current position
      order.remove(draggedItem.id);

      // Insert at first position
      order.insert(0, draggedItem.id);

      // Clear hover state
      _hoveredItemId = null;
    });
    HapticFeedback.mediumImpact();
  }

  Widget _buildTaskItem(
    ActionItemWithMetadata item,
    ActionItemsProvider provider, {
    required TaskCategory category,
    required List<ActionItemWithMetadata> categoryItems,
  }) {
    final indentLevel = _getIndentLevel(item.id);
    final indentWidth = indentLevel * 28.0;
    final isHovered = _hoveredItemId == item.id;

    return DragTarget<ActionItemWithMetadata>(
      onWillAcceptWithDetails: (details) {
        // Accept if it's a different item
        return details.data.id != item.id;
      },
      onAcceptWithDetails: (details) {
        final draggedItem = details.data;

        // Reorder within category
        _reorderItemInCategory(
          draggedItem,
          item.id,
          _hoverAbove,
          category,
          categoryItems,
        );

        // Also update category if different
        final draggedCategory = _getCategoryForItem(draggedItem);
        if (draggedCategory != category) {
          _updateTaskCategory(draggedItem, category);
        }
      },
      onMove: (details) {
        // Determine if hovering on top or bottom half
        final RenderBox box = context.findRenderObject() as RenderBox;
        final localPosition = box.globalToLocal(details.offset);
        final isAbove = localPosition.dy < 20;

        if (_hoveredItemId != item.id || _hoverAbove != isAbove) {
          setState(() {
            _hoveredItemId = item.id;
            _hoverAbove = isAbove;
          });
        }
      },
      onLeave: (data) {
        if (_hoveredItemId == item.id) {
          setState(() {
            _hoveredItemId = null;
          });
        }
      },
      builder: (context, candidateData, rejectedData) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Drop indicator above
            if (isHovered && _hoverAbove && candidateData.isNotEmpty)
              Container(
                height: 2,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  color: Colors.deepPurple,
                  borderRadius: BorderRadius.circular(1),
                ),
              ),
            _buildDraggableTaskItem(item, provider, indentLevel, indentWidth),
            // Drop indicator below
            if (isHovered && !_hoverAbove && candidateData.isNotEmpty)
              Container(
                height: 2,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(
                  color: Colors.deepPurple,
                  borderRadius: BorderRadius.circular(1),
                ),
              ),
          ],
        );
      },
    );
  }

  Widget _buildDraggableTaskItem(
    ActionItemWithMetadata item,
    ActionItemsProvider provider,
    int indentLevel,
    double indentWidth,
  ) {
    final taskContent = _buildTaskItemContent(item, provider, indentWidth);

    // If at indent 0, allow swipe-right to indent and swipe-left to delete.
    if (indentLevel == 0) {
      return Dismissible(
        key: Key('dismiss_${item.id}'),
        direction: DismissDirection.horizontal,
        dismissThresholds: const {
          DismissDirection.startToEnd: 0.25,
          DismissDirection.endToStart: 0.3,
        },
        confirmDismiss: (direction) async {
          if (direction == DismissDirection.startToEnd) {
            _incrementIndent(item.id);
            return false;
          }
          return true;
        },
        background: Container(color: Colors.transparent),
        secondaryBackground: Container(
          alignment: Alignment.centerRight,
          padding: const EdgeInsets.only(right: 20.0),
          decoration: BoxDecoration(
            color: Colors.red,
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Icon(Icons.delete, color: Colors.white),
        ),
        onDismissed: (direction) {
          if (direction == DismissDirection.endToStart) {
            _deleteTask(item);
          }
        },
        child: LongPressDraggable<ActionItemWithMetadata>(
          data: item,
          delay: const Duration(milliseconds: 150),
          hapticFeedbackOnStart: true,
          onDragStarted: () {
            HapticFeedback.mediumImpact();
          },
          onDragEnd: (details) {
            setState(() {
              _hoveredItemId = null;
            });
          },
          feedback: Material(
            color: Colors.transparent,
            child: Container(
              width: MediaQuery.of(context).size.width - 64,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: const Color(0xFF2C2C2E),
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
                      style: const TextStyle(color: Colors.white, fontSize: 15),
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
            child: taskContent,
          ),
          child: taskContent,
        ),
      );
    }

    // If indented, use GestureDetector for indent changes + draggable
    return GestureDetector(
      onHorizontalDragEnd: (details) {
        if (details.primaryVelocity != null) {
          if (details.primaryVelocity! > 200) {
            _incrementIndent(item.id);
          } else if (details.primaryVelocity! < -200) {
            _decrementIndent(item.id);
          }
        }
      },
      child: LongPressDraggable<ActionItemWithMetadata>(
        data: item,
        delay: const Duration(milliseconds: 150),
        hapticFeedbackOnStart: true,
        onDragStarted: () {
          HapticFeedback.mediumImpact();
        },
        onDragEnd: (details) {
          setState(() {
            _hoveredItemId = null;
          });
        },
        feedback: Material(
          color: Colors.transparent,
          child: Container(
            width: MediaQuery.of(context).size.width - 64,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: const Color(0xFF2C2C2E),
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
                    style: const TextStyle(color: Colors.white, fontSize: 15),
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
          child: taskContent,
        ),
        child: taskContent,
      ),
    );
  }

  TaskCategory _getCategoryForItem(ActionItemWithMetadata item) {
    final now = DateTime.now();
    final startOfTomorrow = DateTime(now.year, now.month, now.day + 1);
    final startOfDayAfterTomorrow = DateTime(now.year, now.month, now.day + 2);

    if (item.dueAt == null) {
      return TaskCategory.noDeadline;
    }
    final dueDate = item.dueAt!;
    if (dueDate.isBefore(startOfTomorrow)) {
      return TaskCategory.today;
    } else if (dueDate.isBefore(startOfDayAfterTomorrow)) {
      return TaskCategory.tomorrow;
    } else {
      return TaskCategory.later;
    }
  }

  Widget _buildTaskItemContent(
    ActionItemWithMetadata item,
    ActionItemsProvider provider,
    double indentWidth,
  ) {
    final indentLevel = _getIndentLevel(item.id);
    final goalTitle = _getGoalTitleForTask(item);

    return GestureDetector(
      onTap: () => _showEditSheet(item),
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 1),
        child: Dismissible(
          key: Key('${item.id}_dismiss'),
          direction: DismissDirection.none, // Disable dismiss, use swipe for indent
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
                        color: Colors.grey[700],
                        borderRadius: BorderRadius.circular(1),
                      ),
                    ),
                  ),
                // Checkbox
                GestureDetector(
                  onTap: () async {
                    HapticFeedback.lightImpact();
                    await provider.updateActionItemState(item, !item.completed);
                    if (!item.completed) _onActionItemCompleted();
                  },
                  child: _buildCheckbox(item.completed),
                ),
                const SizedBox(width: 12),
                // Task text
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.description,
                        style: TextStyle(
                          color: item.completed ? Colors.grey[600] : Colors.white,
                          fontSize: 15,
                          decoration: item.completed ? TextDecoration.lineThrough : null,
                        ),
                      ),
                      if (goalTitle != null) ...[
                        const SizedBox(height: 4),
                        Text(
                          goalTitle,
                          style: TextStyle(
                            color: Colors.grey[600],
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ],
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
      width: 22,
      height: 22,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: isCompleted ? Colors.amber : Colors.grey[600]!,
          width: 2,
        ),
        color: isCompleted ? Colors.amber : Colors.transparent,
      ),
      child: isCompleted ? const Icon(Icons.check, size: 14, color: Colors.black) : null,
    );
  }

  Future<void> _deleteGoal(Goal goal) async {
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
    await goalsProvider.deleteGoal(goal.id);
  }

  void _showEditSheet(ActionItemWithMetadata item) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => ActionItemFormSheet(actionItem: item),
    );
  }

  Widget _buildGoalItem(Goal goal) {
    final progress = goal.targetValue > 0 ? goal.currentValue / goal.targetValue : 0.0;
    final progressText = '(${goal.currentValue.toInt()}/${goal.targetValue.toInt()})';
    final displayTitle = '${goal.title} $progressText';

    return Dismissible(
      key: Key('goal_${goal.id}'),
      direction: DismissDirection.endToStart,
      confirmDismiss: (direction) async {
        HapticFeedback.mediumImpact();
        return await showDialog<bool>(
              context: context,
              builder: (context) => AlertDialog(
                backgroundColor: const Color(0xFF1F1F25),
                title: const Text('Delete Goal', style: TextStyle(color: Colors.white)),
                content: Text('Delete "${goal.title}"?', style: const TextStyle(color: Colors.white70)),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    child: const Text('Cancel'),
                  ),
                  TextButton(
                    onPressed: () => Navigator.pop(context, true),
                    style: TextButton.styleFrom(foregroundColor: Colors.red),
                    child: const Text('Delete'),
                  ),
                ],
              ),
            ) ??
            false;
      },
      onDismissed: (direction) async {
        MixpanelManager().goalDeleted(goalId: goal.id, source: 'tasks_page', method: 'swipe');
        await _deleteGoal(goal);
      },
      background: Container(
        margin: const EdgeInsets.symmetric(vertical: 6),
        decoration: BoxDecoration(
          color: Colors.red,
          borderRadius: BorderRadius.circular(8),
        ),
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        child: const Icon(Icons.delete_outline, color: Colors.white),
      ),
      child: GestureDetector(
        onTap: () {
          MixpanelManager().goalItemTappedForEdit(goalId: goal.id, source: 'tasks_page');
          _showEditGoalSheet(goal);
        },
        child: Container(
          color: Colors.transparent,
          padding: const EdgeInsets.symmetric(vertical: 6),
          margin: const EdgeInsets.only(left: 4),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // Circular progress indicator
              Container(
                width: 22,
                height: 22,
                child: CustomPaint(
                  painter: _CircularProgressPainter(
                    progress: progress.clamp(0.0, 1.0),
                    color: progress >= 1.0 ? Colors.amber : Colors.grey.shade600,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              // Goal title with progress
              Expanded(
                child: Text(
                  displayTitle,
                  style: TextStyle(
                    color: progress >= 1.0 ? Colors.grey.shade600 : Colors.white,
                    fontSize: 15,
                    decoration: progress >= 1.0 ? TextDecoration.lineThrough : null,
                    height: 1.4,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showEditGoalSheet(Goal goal) {
    HapticFeedback.lightImpact();
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (sheetContext) => _GoalEditSheet(
        goal: goal,
        onSave: (title, current, target) async {
          // Update goal via provider
          final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
          await goalsProvider.updateGoal(
            goal.id,
            title: title,
            currentValue: current,
            targetValue: target,
          );
          MixpanelManager().goalUpdated(goalId: goal.id, source: 'tasks_page');
        },
        onDelete: () {
          MixpanelManager().goalDeleted(goalId: goal.id, source: 'tasks_page', method: 'button');
          _deleteGoal(goal);
        },
      ),
    );
  }
}

/// Stateful widget for goal creation sheet that properly manages TextEditingController lifecycle
class _GoalCreateSheet extends StatefulWidget {
  final Function(String title, double current, double target) onSave;

  const _GoalCreateSheet({required this.onSave});

  @override
  State<_GoalCreateSheet> createState() => _GoalCreateSheetState();
}

class _GoalCreateSheetState extends State<_GoalCreateSheet> {
  late final TextEditingController titleController;
  late final TextEditingController currentController;
  late final TextEditingController targetController;

  @override
  void initState() {
    super.initState();
    titleController = TextEditingController();
    currentController = TextEditingController(text: '0');
    targetController = TextEditingController(text: '100');
  }

  @override
  void dispose() {
    titleController.dispose();
    currentController.dispose();
    targetController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        decoration: const BoxDecoration(
          color: Color(0xFF1A1A1A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        padding: const EdgeInsets.all(24),
        child: SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.only(bottom: 20),
                decoration: BoxDecoration(
                  color: Colors.grey.shade700,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Text(
                context.l10n.addGoal,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 24),
              // Title field
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    context.l10n.goalTitle,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: titleController,
                    autofocus: true,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: Colors.white.withOpacity(0.08),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide.none,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              // Current & Target fields
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.l10n.current,
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.5),
                            fontSize: 12,
                          ),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: currentController,
                          keyboardType: TextInputType.number,
                          style: const TextStyle(color: Colors.white, fontSize: 16),
                          decoration: InputDecoration(
                            filled: true,
                            fillColor: Colors.white.withOpacity(0.08),
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide.none,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.l10n.target,
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.5),
                            fontSize: 12,
                          ),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: targetController,
                          keyboardType: TextInputType.number,
                          style: const TextStyle(color: Colors.white, fontSize: 16),
                          decoration: InputDecoration(
                            filled: true,
                            fillColor: Colors.white.withOpacity(0.08),
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide.none,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () async {
                    final title = titleController.text.trim();
                    if (title.isEmpty) {
                      Navigator.pop(context);
                      return;
                    }

                    final current = double.tryParse(currentController.text) ?? 0;
                    final target = double.tryParse(targetController.text) ?? 100;

                    if (!context.mounted) return;
                    Navigator.pop(context);

                    widget.onSave(title, current, target);
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF22C55E),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: Text(context.l10n.addGoal),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Stateful widget for goal edit sheet that properly manages TextEditingController lifecycle
class _GoalEditSheet extends StatefulWidget {
  final Goal goal;
  final Function(String title, double current, double target) onSave;
  final Function() onDelete;

  const _GoalEditSheet({
    required this.goal,
    required this.onSave,
    required this.onDelete,
  });

  @override
  State<_GoalEditSheet> createState() => _GoalEditSheetState();
}

class _GoalEditSheetState extends State<_GoalEditSheet> {
  late final TextEditingController titleController;
  late final TextEditingController currentController;
  late final TextEditingController targetController;

  @override
  void initState() {
    super.initState();
    titleController = TextEditingController(text: widget.goal.title);
    currentController = TextEditingController(text: widget.goal.currentValue.toInt().toString());
    targetController = TextEditingController(text: widget.goal.targetValue.toInt().toString());
  }

  @override
  void dispose() {
    titleController.dispose();
    currentController.dispose();
    targetController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        decoration: const BoxDecoration(
          color: Color(0xFF1A1A1A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        padding: const EdgeInsets.all(24),
        child: SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.only(bottom: 20),
                decoration: BoxDecoration(
                  color: Colors.grey.shade700,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Text(
                context.l10n.editGoal,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 24),
              // Title field
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    context.l10n.goalTitle,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: titleController,
                    autofocus: true,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: Colors.white.withOpacity(0.08),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: BorderSide.none,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              // Current & Target fields
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.l10n.current,
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.5),
                            fontSize: 12,
                          ),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: currentController,
                          keyboardType: TextInputType.number,
                          style: const TextStyle(color: Colors.white, fontSize: 16),
                          decoration: InputDecoration(
                            filled: true,
                            fillColor: Colors.white.withOpacity(0.08),
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide.none,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.l10n.target,
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.5),
                            fontSize: 12,
                          ),
                        ),
                        const SizedBox(height: 8),
                        TextField(
                          controller: targetController,
                          keyboardType: TextInputType.number,
                          style: const TextStyle(color: Colors.white, fontSize: 16),
                          decoration: InputDecoration(
                            filled: true,
                            fillColor: Colors.white.withOpacity(0.08),
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide.none,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              Row(
                children: [
                  // Delete button
                  Expanded(
                    child: TextButton(
                      onPressed: () async {
                        Navigator.pop(context);
                        // Confirm and delete
                        final confirm = await showDialog<bool>(
                          context: context,
                          builder: (context) => AlertDialog(
                            backgroundColor: const Color(0xFF1F1F25),
                            title: const Text('Delete Goal', style: TextStyle(color: Colors.white)),
                            content:
                                Text('Delete "${widget.goal.title}"?', style: const TextStyle(color: Colors.white70)),
                            actions: [
                              TextButton(
                                onPressed: () => Navigator.pop(context, false),
                                child: const Text('Cancel'),
                              ),
                              TextButton(
                                onPressed: () => Navigator.pop(context, true),
                                style: TextButton.styleFrom(foregroundColor: Colors.red),
                                child: const Text('Delete'),
                              ),
                            ],
                          ),
                        );
                        if (confirm == true) {
                          widget.onDelete();
                        }
                      },
                      style: TextButton.styleFrom(
                        foregroundColor: Colors.red,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                      child: Text(context.l10n.delete),
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Save button
                  Expanded(
                    flex: 2,
                    child: ElevatedButton(
                      onPressed: () async {
                        final title = titleController.text.trim();
                        if (title.isEmpty) {
                          Navigator.pop(context);
                          return;
                        }

                        final current = double.tryParse(currentController.text) ?? widget.goal.currentValue;
                        final target = double.tryParse(targetController.text) ?? widget.goal.targetValue;

                        if (!context.mounted) return;
                        Navigator.pop(context);

                        widget.onSave(title, current, target);
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF22C55E),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      child: Text(context.l10n.save),
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
}

/// Custom painter for circular progress indicator (pie chart style)
class _CircularProgressPainter extends CustomPainter {
  final double progress;
  final Color color;

  _CircularProgressPainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    // Draw background circle (empty part)
    final bgPaint = Paint()
      ..color = color.withOpacity(0.2)
      ..style = PaintingStyle.fill;
    canvas.drawCircle(center, radius, bgPaint);

    // Draw progress arc (filled part)
    if (progress > 0) {
      final progressPaint = Paint()
        ..color = color
        ..style = PaintingStyle.fill;

      final rect = Rect.fromCircle(center: center, radius: radius);
      const startAngle = -90 * 3.14159 / 180; // Start from top
      final sweepAngle = progress * 2 * 3.14159; // Full circle is 2π

      canvas.drawArc(rect, startAngle, sweepAngle, true, progressPaint);
    }

    // Draw border circle
    final borderPaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    canvas.drawCircle(center, radius - 1, borderPaint);
  }

  @override
  bool shouldRepaint(_CircularProgressPainter oldDelegate) {
    return oldDelegate.progress != progress || oldDelegate.color != color;
  }
}
