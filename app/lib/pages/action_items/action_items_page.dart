import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';

import 'task_categorization.dart';
import 'task_delete_undo.dart';
import 'widgets/action_item_form_sheet.dart';
import 'widgets/action_item_shimmer_widget.dart';
import 'widgets/goal_form_sheet.dart';
import 'widgets/task_row_parts.dart';

// Re-export Goal from goals.dart for use in this file
export 'package:omi/backend/http/api/goals.dart' show Goal;

class ActionItemsPage extends StatefulWidget {
  final VoidCallback? onAddGoal;

  const ActionItemsPage({super.key, this.onAddGoal});

  @override
  State<ActionItemsPage> createState() => _ActionItemsPageState();
}

class _ActionItemsPageState extends State<ActionItemsPage> with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();

  // Task -> goal mapping
  final Map<String, String> _taskGoalLinks = {};

  // Track the item being hovered over during drag
  String? _hoveredItemId;
  bool _hoverAbove = false; // true = insert above, false = insert below
  int _hoverIndent = 0; // target indent_level for the drop slot

  // Whether the current long-press drag has actually moved (reorder) or stayed still (select)
  bool _dragHasMoved = false;

  // Horizontal anchor for the active long-press drag — the feedback widget's
  // top-left X at first onMove. Indent target = origin indent + round(deltaX / step).
  static const double _indentStep = 28.0;
  double? _dragStartX;

  // Overdue section expanded by default — missed deadlines are the most
  // important thing to surface, hiding them behind a tap caused regret.
  bool _overdueExpanded = true;

  bool _noDeadlineExpanded = true;

  // Search header lifecycle objects.
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocusNode = FocusNode();
  final Debouncer _searchDebouncer = Debouncer(delay: const Duration(milliseconds: 400));

  @override
  bool get wantKeepAlive => true;

  void scrollToTop() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(0, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
    }
  }

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    _loadTaskGoalLinks();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      PlatformManager.instance.analytics.actionItemsPageOpened();
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      final phase = provider.apiViewState.phase;
      final typedResultAlreadyProjected = phase == ApiViewPhase.error ||
          phase == ApiViewPhase.locked ||
          phase == ApiViewPhase.terminal ||
          phase == ApiViewPhase.authenticationRequired ||
          phase == ApiViewPhase.empty;
      if (provider.actionItems.isEmpty && !typedResultAlreadyProjected) {
        provider.ensureLoaded(showShimmer: true);
      }
      final taskIntegrationProvider = Provider.of<TaskIntegrationProvider>(context, listen: false);
      if (!taskIntegrationProvider.hasLoaded && !taskIntegrationProvider.isLoading) {
        taskIntegrationProvider.loadFromBackend();
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

  String? _getGoalTitleForTask(ActionItemWithMetadata item) {
    final goalId = _taskGoalLinks[item.id];
    if (goalId == null) return null;
    final goals = Provider.of<GoalsProvider>(context, listen: false).goals;
    for (final goal in goals) {
      if (goal.id == goalId) return goal.title;
    }
    return null;
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    _searchController.dispose();
    _searchFocusNode.dispose();
    _searchDebouncer.cancel();
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
    PlatformManager.instance.analytics.actionItemCompleted(fromTab: 'Tasks');
  }

  void _showCreateActionItemSheet({DateTime? defaultDueDate}) {
    showActionItemFormSheet(context, defaultDueDate: defaultDueDate);
  }

  void _showCreateGoalSheet() {
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
    showGoalFormSheet(
      context,
      onSave: (title, current, target, _) async {
        final created = await goalsProvider.createGoal(
          title: title,
          goalType: 'numeric',
          targetValue: target,
          currentValue: current,
        );
        if (created != null) {
          PlatformManager.instance.analytics.goalCreated(
            goalId: created.id,
            titleLength: title.length,
            targetValue: target,
            source: 'tasks_page',
          );
        }
      },
    );
  }

  Widget _buildFab() {
    return Consumer<ActionItemsProvider>(
      builder: (context, provider, _) {
        // The selection action bar is mounted at the bottom of the Stack —
        // when selection is active we suppress the FAB so the two don't
        // visually compete.
        if (provider.isSelectionMode) return const SizedBox.shrink();
        return Positioned(
          right: 20,
          // Rides on top of the nav bar, so it follows the bar's height and the
          // system inset the bar reserves rather than a literal tuned to one device.
          bottom: bottomNavBarClearance(context),
          child: Semantics(
            button: true,
            label: context.l10n.newTask,
            excludeSemantics: true,
            onTap: () => _showCreateActionItemSheet(defaultDueDate: _getDefaultDueDateForCategory(TaskCategory.today)),
            child: FloatingActionButton(
              heroTag: 'action_items_fab',
              onPressed: () {
                OmiHaptics.light();
                _showCreateActionItemSheet(defaultDueDate: _getDefaultDueDateForCategory(TaskCategory.today));
              },
              backgroundColor: OmiColors.accent,
              foregroundColor: OmiColors.onAccent,
              child: const Icon(Icons.add),
            ),
          ),
        );
      },
    );
  }

  Widget _buildPageHeader(ActionItemsProvider provider) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 12, 4),
      child: Row(
        children: [
          Expanded(
            child: OmiSearchField(
              placeholder: context.l10n.searchActionItems,
              controller: _searchController,
              focusNode: _searchFocusNode,
              onChanged: (value) {
                _searchDebouncer.run(() {
                  if (!mounted) return;
                  provider.setSearchQuery(value);
                });
              },
              onCleared: () {
                _searchDebouncer.cancel();
                provider.clearSearchQuery();
              },
            ),
          ),
          const SizedBox(width: 4),
          _buildOverflowMenu(provider),
        ],
      ),
    );
  }

  Widget _buildOverflowMenu(ActionItemsProvider provider) {
    final showingCompleted = provider.showCompletedView;
    final hasItems = provider.actionItems.isNotEmpty;
    final allSelected = hasItems && provider.selectedCount == provider.actionItems.length;

    return PullDownButton(
      itemBuilder: (context) => [
        PullDownMenuItem(
          title: context.l10n.selectActionItems,
          iconWidget: const Icon(Icons.check_box_outlined, size: 18),
          onTap: () {
            OmiHaptics.light();
            _searchFocusNode.unfocus();
            provider.startSelection();
          },
        ),
        PullDownMenuItem(
          title: allSelected ? context.l10n.deselectAllTasksMenu : context.l10n.selectAllTasksMenu,
          iconWidget: Icon(allSelected ? Icons.deselect_rounded : Icons.select_all_rounded, size: 18),
          onTap: () {
            OmiHaptics.light();
            _searchFocusNode.unfocus();
            if (allSelected) {
              provider.clearSelection();
            } else {
              if (!provider.isSelectionMode) provider.startSelection();
              provider.selectAllItems();
            }
          },
        ),
        PullDownMenuItem(
          title: showingCompleted ? context.l10n.hideCompletedTasks : context.l10n.showCompletedTasks,
          iconWidget: Icon(showingCompleted ? Icons.visibility_off_outlined : Icons.visibility_outlined, size: 18),
          onTap: () {
            OmiHaptics.light();
            provider.toggleShowCompletedView();
          },
        ),
      ],
      buttonBuilder: (context, showMenu) => OmiIconButton.filled(
        icon: const Icon(Icons.more_horiz_rounded),
        label: context.l10n.moreOptions,
        color: OmiColors.textSecondary,
        diameter: 40,
        onPressed: () {
          OmiHaptics.selection();
          showMenu();
        },
      ),
    );
  }

  Widget _buildNoSearchResultsContent() {
    return OmiEmptyState(icon: Icons.search_off_rounded, title: context.l10n.noResultsFound);
  }

  // Categorize items by deadline
  Map<TaskCategory, List<ActionItemWithMetadata>> _categorizeItems(
    List<ActionItemWithMetadata> items,
    bool showCompleted,
  ) {
    // Extracted to task_categorization.dart so the bucketing rule is testable
    // against the shared contracts/parity fixtures.
    return categorizeTasks(items, showCompleted);
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
      case TaskCategory.overdue:
        return context.l10n.tasksOverdue;
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
      case TaskCategory.overdue:
        // Yesterday, so the task stays in overdue after rebuild
        return DateTime(now.year, now.month, now.day - 1, 23, 59);
    }
  }

  void _updateTaskCategory(ActionItemWithMetadata item, TaskCategory newCategory) {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final newDueDate = _getDefaultDueDateForCategory(newCategory);
    provider.updateActionItemDueDate(item, newDueDate);
  }

  /// Deleting a whole section at once cannot be undone: confirm every time (contract §4).
  Future<void> _confirmClearCompleted(ActionItemsProvider provider, List<ActionItemWithMetadata> items) async {
    OmiHaptics.light();
    final l10n = context.l10n;
    final shouldClear = await showOmiConfirm(
      context,
      title: l10n.deleteTasksTitle(items.length),
      message: l10n.thisActionCannotBeUndone,
      confirmLabel: l10n.delete,
      destructive: true,
    );
    if (!shouldClear) return;
    await Future.wait(items.map((item) => provider.deleteActionItem(item)));
  }

  int _getIndentLevel(ActionItemWithMetadata item) {
    return item.indentLevel;
  }

  void _incrementIndent(String itemId) {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final item = provider.actionItems.where((i) => i.id == itemId).firstOrNull;
    if (item == null) return;
    final current = item.indentLevel;
    if (current < 3) {
      provider.updateItemIndentLevel(itemId, current + 1);
    }
    OmiHaptics.light();
  }

  void _decrementIndent(String itemId) {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final item = provider.actionItems.where((i) => i.id == itemId).firstOrNull;
    if (item == null) return;
    final current = item.indentLevel;
    if (current > 0) {
      provider.updateItemIndentLevel(itemId, current - 1);
    }
    OmiHaptics.light();
  }

  // Get ordered items for a category, respecting sort_order from model
  List<ActionItemWithMetadata> _getOrderedItems(TaskCategory category, List<ActionItemWithMetadata> items) {
    final sorted = List<ActionItemWithMetadata>.from(items);
    sorted.sort((a, b) {
      // Items with sortOrder > 0 come first, sorted ascending
      if (a.sortOrder > 0 && b.sortOrder > 0) {
        return a.sortOrder.compareTo(b.sortOrder);
      }
      if (a.sortOrder > 0) return -1;
      if (b.sortOrder > 0) return 1;
      // Fallback: sort by dueAt then createdAt
      final aDue = a.dueAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      final bDue = b.dueAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      final dueCmp = aDue.compareTo(bDue);
      if (dueCmp != 0) return dueCmp;
      final aCreated = a.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      final bCreated = b.createdAt ?? DateTime.fromMillisecondsSinceEpoch(0);
      return aCreated.compareTo(bCreated);
    });
    return sorted;
  }

  // Reorder item within category
  void _reorderItemInCategory(
    ActionItemWithMetadata draggedItem,
    String targetItemId,
    bool insertAbove,
    TaskCategory category,
    List<ActionItemWithMetadata> categoryItems,
  ) {
    // Build the new order as a list of IDs
    final order = categoryItems.map((i) => i.id).toList();
    order.remove(draggedItem.id);

    final targetIndex = order.indexOf(targetItemId);
    if (targetIndex != -1) {
      final insertIndex = insertAbove ? targetIndex : targetIndex + 1;
      order.insert(insertIndex, draggedItem.id);
    } else {
      order.add(draggedItem.id);
    }

    // Assign sequential sort_order values
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final Map<String, int> updates = {};
    for (int i = 0; i < order.length; i++) {
      updates[order[i]] = (i + 1) * 1000;
    }
    provider.batchUpdateSortOrders(updates);

    setState(() {
      _hoveredItemId = null;
    });
    OmiHaptics.medium();
  }

  /// Every single-task delete: immediate, with Undo (D5).
  void _deleteTask(ActionItemWithMetadata item) {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    deleteTaskWithUndo(context, provider, item);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return Consumer<ActionItemsProvider>(
      builder: (context, provider, child) {
        final showCompleted = provider.showCompletedView;
        final categorizedItems = _categorizeItems(provider.actionItems, showCompleted);
        final apiPhase = provider.apiViewState.phase;
        final showTypedStatus = apiPhase == ApiViewPhase.error ||
            apiPhase == ApiViewPhase.locked ||
            apiPhase == ApiViewPhase.terminal ||
            apiPhase == ApiViewPhase.authenticationRequired ||
            apiPhase == ApiViewPhase.empty;

        return Scaffold(
          body: Stack(
            children: [
              GestureDetector(
                excludeFromSemantics: true,
                onTap: () {},
                child: RefreshIndicator(
                  onRefresh: () async {
                    OmiHaptics.medium();
                    return provider.forceRefreshActionItems();
                  },
                  child: provider.isLoading && provider.actionItems.isEmpty
                      ? _buildLoadingState()
                      : showTypedStatus
                          ? CustomScrollView(
                              controller: _scrollController,
                              physics: const AlwaysScrollableScrollPhysics(),
                              slivers: [
                                SliverFillRemaining(
                                  hasScrollBody: false,
                                  child: Center(child: ActionItemsApiStatus(provider: provider)),
                                ),
                              ],
                            )
                          : categorizedItems.values.every((l) => l.isEmpty)
                              ? _buildEmptyTasksList()
                              : _buildTasksList(categorizedItems, provider),
                ),
              ),
              // Hide the corner FAB when the empty state already
              // shows its own "Create Task" button — otherwise we
              // render two competing add buttons on top of each other.
              if (!categorizedItems.values.every((l) => l.isEmpty)) _buildFab(),
              // Selection-mode action bar is mounted at the home page's outer
              // Stack so it paints above the BottomNavBar (mirrors the
              // conversations merge bar). Don't mount it here.
            ],
          ),
        );
      },
    );
  }

  Widget _buildLoadingState() {
    return CustomScrollView(
      controller: _scrollController,
      physics: const NeverScrollableScrollPhysics(),
      slivers: [
        const SliverPadding(padding: EdgeInsets.only(top: 16)),
        const ActionItemsShimmerList(itemCount: 7),
        SliverPadding(padding: EdgeInsets.only(bottom: bottomNavBarClearance(context))),
      ],
    );
  }

  Widget _buildEmptyTasksList() {
    return CustomScrollView(
      controller: _scrollController,
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        const SliverPadding(padding: EdgeInsets.only(top: 12)),
        SliverToBoxAdapter(child: _buildGoalsRow()),
        const SliverPadding(padding: EdgeInsets.only(top: 8)),
        SliverFillRemaining(hasScrollBody: false, child: Center(child: _buildEmptyTasksContent())),
      ],
    );
  }

  Widget _buildEmptyTasksContent() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 120),
      child: KeyedSubtree(
        key: const ValueKey('omi.action_items.empty'),
        child: OmiEmptyState(
          icon: Icons.task_alt_rounded,
          title: context.l10n.noTasksYet,
          message: context.l10n.tasksEmptyStateMessage,
          // Primary action: the obvious next step is to write a task.
          action: OmiButton(
            label: context.l10n.createActionItem,
            icon: Icons.add_rounded,
            size: OmiButtonSize.compact,
            onPressed: () {
              OmiHaptics.light();
              showActionItemFormSheet(context);
            },
          ),
        ),
      ),
    );
  }

  Widget _buildTasksList(
    Map<TaskCategory, List<ActionItemWithMetadata>> categorizedItems,
    ActionItemsProvider provider,
  ) {
    final isSearching = provider.isSearching;
    final filteredItems = isSearching ? provider.filteredActionItems : const <ActionItemWithMetadata>[];

    return CustomScrollView(
      controller: _scrollController,
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        const SliverPadding(padding: EdgeInsets.only(top: 8)),
        SliverToBoxAdapter(child: _buildPageHeader(provider)),

        if (isSearching) ...[
          if (filteredItems.isEmpty)
            SliverFillRemaining(hasScrollBody: false, child: Center(child: _buildNoSearchResultsContent()))
          else
            SliverList(
              delegate: SliverChildBuilderDelegate((context, index) {
                final item = filteredItems[index];
                return Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: _buildTaskItem(
                    item,
                    provider,
                    category: _getCategoryForItem(item),
                    categoryItems: filteredItems,
                  ),
                );
              }, childCount: filteredItems.length),
            ),
        ] else ...[
          SliverToBoxAdapter(child: _buildGoalsRow()),
          const SliverPadding(padding: EdgeInsets.only(top: 6)),

          // Build each category section (skip empty ones, skip overdue — rendered separately below)
          for (final category in TaskCategory.values)
            if (category != TaskCategory.overdue && (categorizedItems[category] ?? []).isNotEmpty)
              SliverToBoxAdapter(
                child: _buildCategorySection(
                  category: category,
                  items: categorizedItems[category] ?? [],
                  provider: provider,
                ),
              ),

          // Overdue section — expanded by default
          if ((categorizedItems[TaskCategory.overdue] ?? []).isNotEmpty)
            SliverToBoxAdapter(
              child: _buildOverdueSection(items: categorizedItems[TaskCategory.overdue]!, provider: provider),
            ),
        ],

        // Bottom padding so the last row scrolls clear of the nav bar
        SliverPadding(padding: EdgeInsets.only(bottom: bottomNavBarClearance(context))),
      ],
    );
  }

  Widget _buildGoalsRow() {
    return Consumer2<GoalsProvider, ActionItemsProvider>(
      builder: (context, goalsProvider, actionProvider, child) {
        if (goalsProvider.isLoading) return const SizedBox.shrink();

        final goals = goalsProvider.goals;
        if (goals.isEmpty) return const SizedBox.shrink();

        return Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Padding(
                // The row is as tall as its 44pt add button; 6pt comes off each
                // side so the header keeps the height it had with a 32pt button,
                // and keeps it when the button is hidden instead of jumping.
                padding: const EdgeInsets.fromLTRB(4, 6, 0, 2),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
                  child: Row(
                    children: [
                      Semantics(header: true, child: Text(context.l10n.goals, style: OmiType.headline)),
                      const Spacer(),
                      if (!actionProvider.isSelectionMode) ...[
                        if (goals.length < 4)
                          OmiIconButton.filled(
                            label: context.l10n.addGoal,
                            diameter: 32,
                            fillColor: OmiColors.surface2,
                            color: OmiColors.textSecondary,
                            icon: const Icon(Icons.add),
                            onPressed: () {
                              OmiHaptics.light();
                              PlatformManager.instance.analytics.track('Add Goal Clicked from Tasks Page');
                              _showCreateGoalSheet();
                            },
                          ),
                      ],
                    ],
                  ),
                ),
              ),
              // Goal items
              ...goals.map((goal) => _buildGoalItem(goal, actionProvider)),
              const SizedBox(height: 8),
            ],
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
              color: isHovering ? OmiColors.surface1 : Colors.transparent,
              borderRadius: OmiRadius.mdAll,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Section header — quieter than the page title; reads as a label,
                // not a heading.
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Row(
                    children: [
                      if (category == TaskCategory.noDeadline)
                        _SectionHeaderTapTarget(
                          reach: const EdgeInsets.only(right: 24),
                          onTap: () => setState(() => _noDeadlineExpanded = !_noDeadlineExpanded),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                _noDeadlineExpanded ? Icons.expand_less : Icons.expand_more,
                                color: OmiColors.textTertiary,
                                size: 16,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                title.toUpperCase(),
                                style: _sectionLabelStyle,
                              ),
                              if (orderedItems.isNotEmpty) ...[
                                const SizedBox(width: 8),
                                _SectionCount(orderedItems.length),
                              ],
                            ],
                          ),
                        )
                      else
                        Padding(
                          padding: _sectionHeaderLinePadding,
                          child: Text(
                            title.toUpperCase(),
                            style: _sectionLabelStyle,
                          ),
                        ),
                      const Spacer(),
                      if (category != TaskCategory.noDeadline) ...[
                        if (provider.showCompletedView && orderedItems.isNotEmpty)
                          // The count and the ✕ are one control: "clear these N".
                          _SectionHeaderTapTarget(
                            semanticLabel: context.l10n.tasksClearCompleted,
                            reach: const EdgeInsets.only(left: 16),
                            onTap: () => _confirmClearCompleted(provider, orderedItems),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                _SectionCount(orderedItems.length),
                                const SizedBox(width: 8),
                                const Icon(Icons.close, size: 14, color: OmiColors.textTertiary),
                              ],
                            ),
                          )
                        else if (orderedItems.isNotEmpty)
                          Padding(
                            padding: _sectionHeaderLinePadding,
                            child: _SectionCount(orderedItems.length),
                          ),
                      ] else if (provider.showCompletedView && orderedItems.isNotEmpty && _noDeadlineExpanded)
                        _SectionHeaderTapTarget(
                          semanticLabel: context.l10n.tasksClearCompleted,
                          reach: const EdgeInsets.only(left: 30),
                          onTap: () => _confirmClearCompleted(provider, orderedItems),
                          child: const Icon(Icons.close, size: 14, color: OmiColors.textTertiary),
                        ),
                    ],
                  ),
                ),

                // Drop zone for first position
                if (orderedItems.isNotEmpty && (category != TaskCategory.noDeadline || _noDeadlineExpanded))
                  _buildFirstPositionDropZone(category, orderedItems, candidateData.isNotEmpty),

                // Task items. Row padding alone carries the rhythm — no
                // dividers between rows; matches Things 3 / Apple Reminders.
                if (category != TaskCategory.noDeadline || _noDeadlineExpanded)
                  ...orderedItems.map(
                    (item) => _buildTaskItem(item, provider, category: category, categoryItems: orderedItems),
                  ),

                // Spacing after section
                const SizedBox(height: 12),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildOverdueSection({required List<ActionItemWithMetadata> items, required ActionItemsProvider provider}) {
    final orderedItems = _getOrderedItems(TaskCategory.overdue, items);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Row(
              children: [
                _SectionHeaderTapTarget(
                  reach: const EdgeInsets.only(right: 24),
                  onTap: () {
                    setState(() {
                      _overdueExpanded = !_overdueExpanded;
                    });
                  },
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(_overdueExpanded ? Icons.expand_less : Icons.expand_more,
                          color: OmiColors.textTertiary, size: 16),
                      const SizedBox(width: 4),
                      Text(
                        context.l10n.tasksOverdue.toUpperCase(),
                        style: _sectionLabelStyle,
                      ),
                      const SizedBox(width: 8),
                      _SectionCount(orderedItems.length),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (_overdueExpanded) ...[
            _buildFirstPositionDropZone(TaskCategory.overdue, orderedItems, false),
            ...orderedItems.map(
              (item) => _buildTaskItem(item, provider, category: TaskCategory.overdue, categoryItems: orderedItems),
            ),
          ],
          const SizedBox(height: 12),
        ],
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
            color: showIndicator ? OmiColors.accent : Colors.transparent,
            borderRadius: OmiRadius.pillAll,
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
    final order = categoryItems.map((i) => i.id).toList();
    order.remove(draggedItem.id);
    order.insert(0, draggedItem.id);

    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final Map<String, int> updates = {};
    for (int i = 0; i < order.length; i++) {
      updates[order[i]] = (i + 1) * 1000;
    }
    provider.batchUpdateSortOrders(updates);

    setState(() {
      _hoveredItemId = null;
    });
    OmiHaptics.medium();
  }

  Widget _buildTaskItem(
    ActionItemWithMetadata item,
    ActionItemsProvider provider, {
    required TaskCategory category,
    required List<ActionItemWithMetadata> categoryItems,
  }) {
    final indentLevel = _getIndentLevel(item);
    final indentWidth = indentLevel * 28.0;
    final isHovered = _hoveredItemId == item.id;

    // Capture the DragTarget's own BuildContext so onMove uses the item's
    // RenderBox rather than the page-level RenderBox.
    BuildContext? itemContext;

    return DragTarget<ActionItemWithMetadata>(
      onWillAcceptWithDetails: (details) {
        // Accept if it's a different item
        return details.data.id != item.id;
      },
      onAcceptWithDetails: (details) {
        final draggedItem = details.data;
        final targetIndent = _hoverIndent;

        // Reorder within category
        _reorderItemInCategory(draggedItem, item.id, _hoverAbove, category, categoryItems);

        // Apply indent change from the drag's horizontal travel.
        if (draggedItem.indentLevel != targetIndent) {
          Provider.of<ActionItemsProvider>(context, listen: false).updateItemIndentLevel(draggedItem.id, targetIndent);
        }

        // Also update category if different
        final draggedCategory = _getCategoryForItem(draggedItem);
        if (draggedCategory != category) {
          _updateTaskCategory(draggedItem, category);
        }
      },
      onMove: (details) {
        // Use the item's own RenderBox (captured from builder) so the
        // above/below threshold is relative to the item, not the page.
        final box = (itemContext ?? context).findRenderObject() as RenderBox?;
        if (box == null) return;
        final localPosition = box.globalToLocal(details.offset);
        final isAbove = localPosition.dy < box.size.height / 2;

        // Anchor the horizontal drag origin on the first onMove; subsequent
        // moves measure delta from there so the user has to consciously
        // travel right/left to indent/outdent.
        _dragStartX ??= details.offset.dx;
        final deltaX = details.offset.dx - _dragStartX!;
        final draggedItem = details.data;
        final targetIdx = categoryItems.indexWhere((i) => i.id == item.id);
        final maxIndent = _maxIndentForDrop(
          draggedItem: draggedItem,
          targetIdx: targetIdx,
          isAbove: isAbove,
          categoryItems: categoryItems,
        );
        final newIndent = (draggedItem.indentLevel + (deltaX / _indentStep).round()).clamp(0, maxIndent);

        if (_hoveredItemId != item.id || _hoverAbove != isAbove || _hoverIndent != newIndent) {
          setState(() {
            _hoveredItemId = item.id;
            _hoverAbove = isAbove;
            _hoverIndent = newIndent;
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
      builder: (ctx, candidateData, rejectedData) {
        itemContext = ctx;
        // Drop bar mirrors the target indent so the user sees where the row
        // will land before they release.
        final barLeft = 4 + _hoverIndent * _indentStep;
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Drop indicator above
            if (isHovered && _hoverAbove && candidateData.isNotEmpty)
              Container(
                height: 2,
                margin: EdgeInsets.only(left: barLeft, right: 4),
                decoration: const BoxDecoration(color: OmiColors.accent, borderRadius: OmiRadius.pillAll),
              ),
            _buildDraggableTaskItem(item, provider, indentLevel, indentWidth, categoryItems),
            // Drop indicator below
            if (isHovered && !_hoverAbove && candidateData.isNotEmpty)
              Container(
                height: 2,
                margin: EdgeInsets.only(left: barLeft, right: 4),
                decoration: const BoxDecoration(color: OmiColors.accent, borderRadius: OmiRadius.pillAll),
              ),
          ],
        );
      },
    );
  }

  /// Walks the displayed [categoryItems] forward from [parent] and returns
  /// every contiguous descendant — rows with strictly greater indent_level,
  /// stopping at the first sibling/ancestor. The data model is flat (no
  /// parent_id), so the page is the right layer to compute this: it owns the
  /// category-grouped display order; the provider does not.
  List<String> _visibleDescendantIds(ActionItemWithMetadata parent, List<ActionItemWithMetadata> categoryItems) {
    final idx = categoryItems.indexWhere((i) => i.id == parent.id);
    if (idx < 0) return const [];
    final ids = <String>[];
    for (int i = idx + 1; i < categoryItems.length; i++) {
      if (categoryItems[i].indentLevel <= parent.indentLevel) break;
      ids.add(categoryItems[i].id);
    }
    return ids;
  }

  /// Caps the drop indent at one level deeper than the row immediately
  /// preceding the drop slot (skipping the dragged row itself). Without this,
  /// a user could indent past a parent that doesn't exist yet.
  int _maxIndentForDrop({
    required ActionItemWithMetadata draggedItem,
    required int targetIdx,
    required bool isAbove,
    required List<ActionItemWithMetadata> categoryItems,
  }) {
    if (targetIdx < 0) return 3;
    int idx = isAbove ? targetIdx - 1 : targetIdx;
    while (idx >= 0 && categoryItems[idx].id == draggedItem.id) {
      idx--;
    }
    if (idx < 0) return 0;
    return (categoryItems[idx].indentLevel + 1).clamp(0, 3);
  }

  Widget _buildDraggableTaskItem(
    ActionItemWithMetadata item,
    ActionItemsProvider provider,
    int indentLevel,
    double indentWidth,
    List<ActionItemWithMetadata> categoryItems,
  ) {
    final taskContent = _buildTaskItemContent(item, provider, indentWidth, categoryItems);

    // In selection mode: no drag, no swipe — just tappable content.
    if (provider.isSelectionMode) {
      return taskContent;
    }

    // Long-press and hold still opens the row menu; long-press and move drags (reorder, and
    // indent by horizontal travel).
    final draggable = LongPressDraggable<ActionItemWithMetadata>(
      data: item,
      delay: const Duration(milliseconds: 400),
      hapticFeedbackOnStart: true,
      onDragStarted: () {
        _dragHasMoved = false;
        _dragStartX = null;
        _hoverIndent = item.indentLevel;
        OmiHaptics.medium();
      },
      onDragUpdate: (_) {
        _dragHasMoved = true;
      },
      onDragEnd: (details) {
        if (!_dragHasMoved) _showTaskMenu(item, categoryItems);
        setState(() {
          _hoveredItemId = null;
          _dragHasMoved = false;
          _hoverIndent = 0;
          _dragStartX = null;
        });
      },
      feedback: Material(
        color: Colors.transparent,
        child: Container(
          width: MediaQuery.of(context).size.width - 64,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: OmiColors.surface2,
            borderRadius: OmiRadius.mdAll,
            boxShadow: [
              BoxShadow(color: Colors.black.withValues(alpha: 0.3), blurRadius: 10, offset: const Offset(0, 4)),
            ],
          ),
          child: Row(
            children: [
              TaskCompletionMark(completed: item.completed),
              const SizedBox(width: 12),
              Expanded(
                child: Text(item.description, style: OmiType.subhead, maxLines: 1, overflow: TextOverflow.ellipsis),
              ),
            ],
          ),
        ),
      ),
      childWhenDragging: Opacity(opacity: 0.3, child: taskContent),
      child: taskContent,
    );

    // One meaning on every row, at every indent level: swipe right completes (or reopens), swipe
    // left deletes with Undo. Indenting lives in the long-press menu and in drag.
    return Dismissible(
      key: Key('dismiss_${item.id}'),
      direction: DismissDirection.horizontal,
      dismissThresholds: const {DismissDirection.startToEnd: 0.3, DismissDirection.endToStart: 0.3},
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          await _toggleCompleted(provider, item);
          return false;
        }
        return true;
      },
      background: Container(
        alignment: Alignment.centerLeft,
        padding: const EdgeInsets.only(left: 20.0),
        decoration: BoxDecoration(
          color: item.completed ? OmiColors.surface3 : OmiColors.success,
          borderRadius: OmiRadius.smAll,
        ),
        child: Icon(item.completed ? Icons.undo : Icons.check, color: OmiColors.textPrimary),
      ),
      secondaryBackground: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20.0),
        decoration: const BoxDecoration(color: OmiColors.danger, borderRadius: OmiRadius.smAll),
        child: const Icon(Icons.delete_outline, color: OmiColors.textPrimary),
      ),
      onDismissed: (direction) {
        if (direction == DismissDirection.endToStart) {
          _deleteTask(item);
        }
      },
      child: draggable,
    );
  }

  Future<void> _toggleCompleted(ActionItemsProvider provider, ActionItemWithMetadata item) async {
    OmiHaptics.light();
    await provider.updateActionItemState(item, !item.completed);
    if (!item.completed) _onActionItemCompleted();
  }

  /// Long-press menu: the same shape as memories and conversations, with Select for multi-select
  /// and the indent controls that used to hide behind a swipe.
  void _showTaskMenu(ActionItemWithMetadata item, List<ActionItemWithMetadata> categoryItems) {
    final l10n = context.l10n;
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final index = categoryItems.indexWhere((i) => i.id == item.id);
    final maxIndent = index <= 0 ? 0 : (categoryItems[index - 1].indentLevel + 1).clamp(0, 3);
    showOmiRowMenu(
      context,
      title: item.description,
      actions: [
        OmiMenuAction(icon: Icons.open_in_full_rounded, label: l10n.open, onSelected: () => _showEditSheet(item)),
        OmiMenuAction(
          icon: item.completed ? Icons.undo_rounded : Icons.check_circle_outline,
          label: item.completed ? l10n.markIncomplete : l10n.markComplete,
          onSelected: () => _toggleCompleted(provider, item),
        ),
        if (item.indentLevel < maxIndent)
          OmiMenuAction(
            icon: Icons.format_indent_increase_rounded,
            label: l10n.indentTask,
            onSelected: () => _incrementIndent(item.id),
          ),
        if (item.indentLevel > 0)
          OmiMenuAction(
            icon: Icons.format_indent_decrease_rounded,
            label: l10n.outdentTask,
            onSelected: () => _decrementIndent(item.id),
          ),
        OmiMenuAction(
          icon: Icons.check_box_outlined,
          label: l10n.selectOption,
          onSelected: () {
            _searchFocusNode.unfocus();
            provider.startSelectionWithItem(item.id);
          },
        ),
        OmiMenuAction(
          icon: Icons.delete_outline,
          label: l10n.delete,
          isDestructive: true,
          onSelected: () => _deleteTask(item),
        ),
      ],
    );
  }

  TaskCategory _getCategoryForItem(ActionItemWithMetadata item) =>
      categoryForItem(item, Provider.of<ActionItemsProvider>(context, listen: false).showCompletedView);

  Widget _buildTaskItemContent(
    ActionItemWithMetadata item,
    ActionItemsProvider provider,
    double indentWidth,
    List<ActionItemWithMetadata> categoryItems,
  ) {
    final indentLevel = _getIndentLevel(item);
    final goalTitle = _getGoalTitleForTask(item);
    final isSelected = provider.isSelectionMode && provider.isItemSelected(item.id);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        if (provider.isSelectionMode) {
          OmiHaptics.selection();
          provider.toggleItemSelection(item.id, cascadeIds: _visibleDescendantIds(item, categoryItems));
        } else {
          _showEditSheet(item);
        }
      },
      child: AnimatedContainer(
        duration: OmiMotion.of(context).quick,
        margin: EdgeInsets.zero,
        decoration: BoxDecoration(
          color: isSelected ? OmiColors.surface2 : Colors.transparent,
          borderRadius: OmiRadius.smAll,
        ),
        child: Padding(
          padding: EdgeInsets.only(left: 4 + indentWidth, right: 4, top: 0, bottom: 0),
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
                    decoration: const BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.pillAll),
                  ),
                ),
              // Completion circle — always shown. Read-only in selection mode
              // (the row tap drives selection there); tappable otherwise.
              Semantics(
                button: !provider.isSelectionMode,
                checked: item.completed,
                label: item.completed ? context.l10n.markIncomplete : context.l10n.markComplete,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: provider.isSelectionMode ? null : () => _toggleCompleted(provider, item),
                  child: SizedBox(
                      width: 44, height: 48, child: Center(child: TaskCompletionMark(completed: item.completed))),
                ),
              ),
              // Task text
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        item.description,
                        style: OmiType.callout.copyWith(
                          color: item.completed ? OmiColors.textTertiary : OmiColors.textPrimary,
                          fontWeight: FontWeight.w500,
                          letterSpacing: -0.2,
                          decoration: item.completed ? TextDecoration.lineThrough : null,
                          decorationColor: OmiColors.textTertiary,
                        ),
                      ),
                      if (goalTitle != null) ...[
                        const SizedBox(height: 4),
                        Text(goalTitle, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                      ],
                      if (item.exported && item.exportPlatform != null) ...[
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            const Icon(Icons.check_circle_outline, size: 12, color: OmiColors.textTertiary),
                            const SizedBox(width: 4),
                            Text(
                              context.l10n.exportedToPlatform(_exportPlatformLabel(item.exportPlatform!)),
                              style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              // Trailing square selection box — only in selection mode.
              // Different shape + position from the leading completion circle
              // so completion vs. selection cannot be confused.
              if (provider.isSelectionMode)
                Padding(
                  padding: const EdgeInsets.only(left: 8, right: 8),
                  child: TaskSelectionSquare(selected: isSelected),
                ),
            ],
          ),
        ),
      ),
    );
  }

  String _exportPlatformLabel(String platform) {
    switch (platform) {
      case 'todoist':
        return 'Todoist';
      case 'asana':
        return 'Asana';
      case 'google_tasks':
        return 'Google Tasks';
      case 'clickup':
        return 'ClickUp';
      case 'apple_reminders':
        return 'Reminders';
      default:
        return platform;
    }
  }

  void _deleteGoal(Goal goal) {
    deleteGoalWithUndo(context, Provider.of<GoalsProvider>(context, listen: false), goal);
  }

  void _showEditSheet(ActionItemWithMetadata item) {
    showActionItemFormSheet(context, actionItem: item);
  }

  Widget _buildGoalItem(Goal goal, ActionItemsProvider provider) {
    final progress = goal.targetValue > 0 ? goal.currentValue / goal.targetValue : 0.0;
    final progressText = '(${goal.currentValue.toInt()}/${goal.targetValue.toInt()})';
    final displayTitle = '${goal.title} $progressText';

    final goalContent = GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        // Goals are not part of selection mode — selection only applies to
        // tasks (the action bar's Export action acts on tasks only).
        if (provider.isSelectionMode) return;
        PlatformManager.instance.analytics.goalItemTappedForEdit(goalId: goal.id, source: 'tasks_page');
        _showEditGoalSheet(goal);
      },
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 0),
        margin: const EdgeInsets.only(left: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            SizedBox(
              width: 44,
              height: 44,
              child: Center(
                child: SizedBox(
                  width: 22,
                  height: 22,
                  child: CustomPaint(
                    painter: GoalProgressPainter(
                      progress: progress.clamp(0.0, 1.0),
                      color: progress >= 1.0 ? TaskCompletionMark.doneColor : OmiColors.textTertiary,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                displayTitle,
                style: OmiType.subhead.copyWith(
                  color: progress >= 1.0 ? OmiColors.textTertiary : OmiColors.textPrimary,
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
    );

    if (provider.isSelectionMode) return goalContent;

    // Restorable: delete at once with Undo, no dialog (D5).
    return Dismissible(
      key: Key('goal_${goal.id}'),
      direction: DismissDirection.endToStart,
      onDismissed: (direction) {
        PlatformManager.instance.analytics.goalDeleted(goalId: goal.id, source: 'tasks_page', method: 'swipe');
        _deleteGoal(goal);
      },
      background: Container(
        margin: const EdgeInsets.symmetric(vertical: 6),
        decoration: const BoxDecoration(color: OmiColors.danger, borderRadius: OmiRadius.smAll),
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        child: const Icon(Icons.delete_outline, color: OmiColors.textPrimary),
      ),
      child: goalContent,
    );
  }

  void _showEditGoalSheet(Goal goal) {
    OmiHaptics.light();
    final goalsProvider = Provider.of<GoalsProvider>(context, listen: false);
    showGoalFormSheet(
      context,
      goal: goal,
      onSave: (title, current, target, _) async {
        await goalsProvider.updateGoal(goal.id, title: title, currentValue: current, targetValue: target);
        PlatformManager.instance.analytics.goalUpdated(goalId: goal.id, source: 'tasks_page');
      },
      onDelete: () {
        PlatformManager.instance.analytics.goalDeleted(goalId: goal.id, source: 'tasks_page', method: 'button');
        _deleteGoal(goal);
      },
    );
  }
}

/// Vertical padding of a task section header: the space above the label line
/// and the sliver of space between it and the first task row.
const EdgeInsets _sectionHeaderLinePadding = EdgeInsets.only(top: 16, bottom: 4);

/// A section header's label ("TODAY", "OVERDUE").
final TextStyle _sectionLabelStyle =
    OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600, letterSpacing: 0.8);

/// The count beside a section header, read out as "3 tasks" rather than a bare number.
class _SectionCount extends StatelessWidget {
  const _SectionCount(this.count);

  final int count;

  @override
  Widget build(BuildContext context) {
    return Text(
      '$count',
      semanticsLabel: context.l10n.tasksCountLabel(count),
      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
    );
  }
}

/// A tappable part of a task section header.
///
/// Section headers are one 12pt line of text, which made the collapse chevrons
/// ~19pt targets and the "clear completed" ✕ a 14pt one. A task row starts 4pt
/// below the line, so there is no room to grow a target downwards. Instead the
/// header's vertical padding moves inside each child ([_sectionHeaderLinePadding])
/// and the tappable ones own it, plus [reach] of width on the side that faces
/// the header's Spacer. The child stays where it was on the text line and
/// nothing in the list moves; the target becomes the header's full 36pt height.
class _SectionHeaderTapTarget extends StatelessWidget {
  const _SectionHeaderTapTarget({
    required this.onTap,
    required this.child,
    required this.reach,
    this.semanticLabel,
  });

  final VoidCallback onTap;
  final Widget child;
  final EdgeInsets reach;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: semanticLabel,
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Padding(padding: _sectionHeaderLinePadding + reach, child: child),
      ),
    );
  }
}
