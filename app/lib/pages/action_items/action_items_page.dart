import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'widgets/action_item_form_sheet.dart';

enum TaskCategory { today, tomorrow, noDeadline, later }

class ActionItemsPage extends StatefulWidget {
  const ActionItemsPage({super.key});

  @override
  State<ActionItemsPage> createState() => _ActionItemsPageState();
}

class _ActionItemsPageState extends State<ActionItemsPage> with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();
  final AppReviewService _appReviewService = AppReviewService();

  // Track indent levels for each task (task id -> indent level 0-3)
  final Map<String, int> _indentLevels = {};

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
          floatingActionButton: Padding(
            padding: const EdgeInsets.only(bottom: 100.0),
            child: FloatingActionButton(
              heroTag: 'action_items_fab',
              onPressed: () => _showCreateActionItemSheet(),
              backgroundColor: Colors.deepPurpleAccent,
              child: const Icon(Icons.add, color: Colors.white),
            ),
          ),
          body: RefreshIndicator(
            onRefresh: () async {
              HapticFeedback.mediumImpact();
              return provider.forceRefreshActionItems();
            },
            color: Colors.deepPurpleAccent,
            backgroundColor: Colors.white,
            child: provider.isLoading && provider.actionItems.isEmpty
                ? _buildLoadingState()
                : categorizedItems.values.every((l) => l.isEmpty)
                    ? _buildEmptyState()
                    : _buildTasksList(categorizedItems, provider),
          ),
        );
      },
    );
  }

  Widget _buildLoadingState() {
    return const Center(
      child: CircularProgressIndicator(color: Colors.deepPurpleAccent),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: Colors.deepPurpleAccent.withOpacity(0.1),
                borderRadius: BorderRadius.circular(24),
              ),
              child: Icon(
                Icons.check_circle_outline,
                size: 40,
                color: Colors.deepPurpleAccent.withOpacity(0.6),
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'No Tasks Yet',
              style: TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Tasks from your conversations will appear here.\nTap + to create one manually.',
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

  Widget _buildCategorySection({
    required TaskCategory category,
    required List<ActionItemWithMetadata> items,
    required ActionItemsProvider provider,
  }) {
    final title = _getCategoryTitle(category);
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
            color: showIndicator ? Colors.deepPurpleAccent : Colors.transparent,
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
                  color: Colors.deepPurpleAccent,
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
                  color: Colors.deepPurpleAccent,
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

    // If at indent 0, use Dismissible for swipe-to-delete with animation
    if (indentLevel == 0) {
      return Dismissible(
        key: Key('dismiss_${item.id}'),
        direction: DismissDirection.endToStart,
        dismissThresholds: const {DismissDirection.endToStart: 0.3},
        background: Container(
          alignment: Alignment.centerRight,
          padding: const EdgeInsets.only(right: 20.0),
          decoration: BoxDecoration(
            color: Colors.red,
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Icon(Icons.delete, color: Colors.white),
        ),
        onDismissed: (direction) {
          _deleteTask(item);
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
                  child: Text(
                    item.description,
                    style: TextStyle(
                      color: item.completed ? Colors.grey[600] : Colors.white,
                      fontSize: 15,
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

  void _showEditSheet(ActionItemWithMetadata item) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => ActionItemFormSheet(actionItem: item),
    );
  }
}
