import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/home_bottom_bar.dart';

import 'task_categorization.dart';
import 'task_delete_undo.dart';
import 'task_page.dart';
import 'widgets/action_item_form_sheet.dart';
import 'widgets/action_item_shimmer_widget.dart';
import 'widgets/task_row_parts.dart';

// Re-export Goal from goals.dart for use in this file
export 'package:omi/backend/http/api/goals.dart' show Goal;

class ActionItemsPage extends StatefulWidget {
  const ActionItemsPage({super.key});

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
  bool _completedExpanded = false;

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
          bottom: homeBottomClearance(context),
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
        ],
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
        final categorizedItems = _categorizeItems(provider.actionItems, false);
        final completedItems = _completedItems(provider);
        final hasTasks = categorizedItems.values.any((l) => l.isNotEmpty) || completedItems.isNotEmpty;
        final apiPhase = provider.apiViewState.phase;
        // Successful empty results use the existing icon and conversation guidance.
        final showTypedStatus = apiPhase == ApiViewPhase.error ||
            apiPhase == ApiViewPhase.locked ||
            apiPhase == ApiViewPhase.terminal ||
            apiPhase == ApiViewPhase.authenticationRequired;

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
                          : !hasTasks
                              ? _buildEmptyTasksList()
                              : _buildTasksList(categorizedItems, completedItems, provider),
                ),
              ),
              // The empty state points to conversation capture on Home.
              if (hasTasks) _buildFab(),
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
        SliverPadding(padding: EdgeInsets.only(bottom: homeBottomClearance(context))),
      ],
    );
  }

  Widget _buildEmptyTasksList() {
    return CustomScrollView(
      controller: _scrollController,
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
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
          titleLayoutReference: context.l10n.noConversationsYet,
          message: context.l10n.tasksEmptyStateMessage,
        ),
      ),
    );
  }

  Widget _buildTasksList(
    Map<TaskCategory, List<ActionItemWithMetadata>> categorizedItems,
    List<ActionItemWithMetadata> completedItems,
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
          const SliverPadding(padding: EdgeInsets.only(top: 6)),

          // Overdue first, expanded by default: what slipped is the first thing on the page.
          if ((categorizedItems[TaskCategory.overdue] ?? []).isNotEmpty)
            SliverToBoxAdapter(
              child: _buildOverdueSection(items: categorizedItems[TaskCategory.overdue]!, provider: provider),
            ),

          // Then each dated section in order (empty ones skipped; overdue is above).
          for (final category in TaskCategory.values)
            if (category != TaskCategory.overdue && (categorizedItems[category] ?? []).isNotEmpty)
              SliverToBoxAdapter(
                child: _buildCategorySection(
                  category: category,
                  items: categorizedItems[category] ?? [],
                  provider: provider,
                ),
              ),

          // Done tasks last, folded: the list stays short, nothing is hidden on another screen.
          if (completedItems.isNotEmpty) SliverToBoxAdapter(child: _buildCompletedSection(completedItems, provider)),
        ],

        // Bottom padding so the last row scrolls clear of the nav bar
        SliverPadding(padding: EdgeInsets.only(bottom: homeBottomClearance(context))),
      ],
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
                              Text(title, style: _sectionLabelStyle),
                              if (orderedItems.isNotEmpty) ...[
                                const SizedBox(width: 6),
                                _SectionCount(orderedItems.length),
                              ],
                              const SizedBox(width: 4),
                              _SectionChevron(expanded: _noDeadlineExpanded),
                            ],
                          ),
                        )
                      else
                        Padding(
                          padding: _sectionHeaderLinePadding,
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(title, style: _sectionLabelStyle),
                              if (orderedItems.isNotEmpty) ...[
                                const SizedBox(width: 6),
                                _SectionCount(orderedItems.length),
                              ],
                            ],
                          ),
                        ),
                    ],
                  ),
                ),

                // Drop zone for first position
                if (orderedItems.isNotEmpty && (category != TaskCategory.noDeadline || _noDeadlineExpanded))
                  _buildFirstPositionDropZone(category, orderedItems, candidateData.isNotEmpty),

                // Task items, with a hairline between rows (see _buildTaskItemContent).
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
                      Text(context.l10n.tasksOverdue, style: _sectionLabelStyle),
                      const SizedBox(width: 6),
                      _SectionCount(orderedItems.length),
                      const SizedBox(width: 4),
                      _SectionChevron(expanded: _overdueExpanded),
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

  /// Done tasks, newest first.
  List<ActionItemWithMetadata> _completedItems(ActionItemsProvider provider) {
    DateTime? when(ActionItemWithMetadata i) => i.completedAt ?? i.updatedAt ?? i.createdAt;
    final items = provider.completedItems;
    items.sort((a, b) {
      final x = when(a), y = when(b);
      if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
      return y.compareTo(x);
    });
    return items;
  }

  /// "Completed n ›" under the open sections, folded by default. Open, it lists the done tasks
  /// (ring filled, text struck) with Clear on the right; a ring tap brings a task back.
  Widget _buildCompletedSection(List<ActionItemWithMetadata> items, ActionItemsProvider provider) {
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
                  onTap: () => setState(() => _completedExpanded = !_completedExpanded),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(context.l10n.completed, style: _sectionLabelStyle),
                      const SizedBox(width: 6),
                      _SectionCount(items.length),
                      const SizedBox(width: 4),
                      _SectionChevron(expanded: _completedExpanded),
                    ],
                  ),
                ),
                const Spacer(),
                if (_completedExpanded)
                  _SectionHeaderTapTarget(
                    semanticLabel: context.l10n.tasksClearCompleted,
                    reach: const EdgeInsets.only(left: 16),
                    onTap: () => _confirmClearCompleted(provider, items),
                    child: Text(context.l10n.clear, style: _sectionLabelStyle),
                  ),
              ],
            ),
          ),
          if (_completedExpanded) ...items.map((item) => _buildCompletedRow(item, items, provider)),
          const SizedBox(height: 12),
        ],
      ),
    );
  }

  /// A done row: no drag or swipe, the same tap and long-press as an open row.
  Widget _buildCompletedRow(
    ActionItemWithMetadata item,
    List<ActionItemWithMetadata> items,
    ActionItemsProvider provider,
  ) {
    BuildContext? rowContext;
    return GestureDetector(
      onLongPress: provider.isSelectionMode
          ? null
          : () {
              OmiHaptics.medium();
              _showTaskMenu(item, items, anchor: rowContext);
            },
      child: Builder(
        builder: (ctx) {
          rowContext = ctx;
          return _buildTaskItemContent(item, provider, 0, items);
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
                decoration: BoxDecoration(color: OmiColors.accent, borderRadius: OmiRadius.pillAll),
              ),
            _buildDraggableTaskItem(item, provider, indentLevel, indentWidth, categoryItems),
            // Drop indicator below
            if (isHovered && !_hoverAbove && candidateData.isNotEmpty)
              Container(
                height: 2,
                margin: EdgeInsets.only(left: barLeft, right: 4),
                decoration: BoxDecoration(color: OmiColors.accent, borderRadius: OmiRadius.pillAll),
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
    // A paywalled task: no drag, swipe or menu either; its tap goes to the plan page.
    if (item.isLocked) return taskContent;

    // The row's own context, so the long-press menu can anchor under it.
    BuildContext? rowContext;

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
        if (!_dragHasMoved) _showTaskMenu(item, categoryItems, anchor: rowContext);
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
      child: Builder(
        builder: (ctx) {
          rowContext = ctx;
          return taskContent;
        },
      ),
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
        decoration: BoxDecoration(color: OmiColors.danger, borderRadius: OmiRadius.smAll),
        child: Icon(Icons.delete_outline, color: OmiColors.textPrimary),
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

  /// Long-press menu: the conversation page's anchored menu, under the row that was held. Open
  /// and completion first, then the editing entries, Delete last.
  void _showTaskMenu(
    ActionItemWithMetadata item,
    List<ActionItemWithMetadata> categoryItems, {
    BuildContext? anchor,
  }) {
    final l10n = context.l10n;
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final index = categoryItems.indexWhere((i) => i.id == item.id);
    final maxIndent = index <= 0 ? 0 : (categoryItems[index - 1].indentLevel + 1).clamp(0, 3);
    final box = anchor?.findRenderObject() as RenderBox?;
    final screen = MediaQuery.sizeOf(context);
    final position = box != null && box.hasSize
        ? box.localToGlobal(Offset.zero) & box.size
        : Rect.fromCenter(center: Offset(screen.width / 2, screen.height / 2), width: 1, height: 1);
    showPullDownMenu(
      context: context,
      position: position,
      items: [
        PullDownMenuItem(title: l10n.open, icon: Icons.open_in_full_rounded, onTap: () => openTaskPage(context, item)),
        PullDownMenuItem(
          title: item.completed ? l10n.markIncomplete : l10n.markComplete,
          icon: item.completed ? Icons.undo_rounded : Icons.check_circle_outline,
          onTap: () => _toggleCompleted(provider, item),
        ),
        const PullDownMenuDivider.large(),
        if (!item.exported)
          PullDownMenuItem(title: l10n.exportButton, icon: Icons.ios_share_rounded, onTap: () => _exportTask(item)),
        if (!item.completed && item.indentLevel < maxIndent)
          PullDownMenuItem(
            title: l10n.indentTask,
            icon: Icons.format_indent_increase_rounded,
            onTap: () => _incrementIndent(item.id),
          ),
        if (!item.completed && item.indentLevel > 0)
          PullDownMenuItem(
            title: l10n.outdentTask,
            icon: Icons.format_indent_decrease_rounded,
            onTap: () => _decrementIndent(item.id),
          ),
        PullDownMenuItem(
          title: l10n.selectOption,
          icon: Icons.check_box_outlined,
          onTap: () {
            _searchFocusNode.unfocus();
            provider.startSelectionWithItem(item.id);
          },
        ),
        const PullDownMenuDivider.large(),
        PullDownMenuItem(
          title: l10n.deleteActionItem,
          icon: Icons.delete_outline,
          isDestructive: true,
          onTap: () => _deleteTask(item),
        ),
      ],
    );
  }

  /// One task to the connected task app, the way the selection bar exports several.
  Future<void> _exportTask(ActionItemWithMetadata item) async {
    OmiHaptics.light();
    final integrations = Provider.of<TaskIntegrationProvider>(context, listen: false);
    final connected = TaskIntegrationApp.values.where(integrations.isAppConnected).toList(growable: false);
    if (connected.isEmpty) {
      OmiFeedback.error(
        context,
        context.l10n.connectTaskAppToExport,
        actionLabel: context.l10n.connectAction,
        onAction: () => routeToPage(context, const TaskIntegrationsPage()),
      );
      return;
    }
    await Provider.of<ActionItemsProvider>(context, listen: false).exportItems(context, [item], connected.first);
  }

  TaskCategory _getCategoryForItem(ActionItemWithMetadata item) => categoryForItem(item, false);

  Widget _buildTaskItemContent(
    ActionItemWithMetadata item,
    ActionItemsProvider provider,
    double indentWidth,
    List<ActionItemWithMetadata> categoryItems,
  ) {
    final indentLevel = _getIndentLevel(item);
    final goalTitle = _getGoalTitleForTask(item);
    final isSelected = provider.isSelectionMode && provider.isItemSelected(item.id);
    final category = _getCategoryForItem(item);
    final dueLabel = _dueDayLabel(item, category);
    // Hairline under every row but a section's last, starting where the title starts.
    final showDivider = categoryItems.isNotEmpty && categoryItems.last.id != item.id;
    final titleInset = 4 + indentWidth + (indentLevel > 0 ? 11.5 : 0) + 44;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        if (item.isLocked) {
          _openUpgrade();
        } else if (provider.isSelectionMode) {
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
        child: Stack(
          children: [
            Padding(
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
                        decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.pillAll),
                      ),
                    ),
                  // Completion circle — always shown. Read-only in selection mode
                  // (the row tap drives selection there); tappable otherwise.
                  if (item.isLocked)
                    // Paywalled: the backend cuts the text short and refuses edits (402), so a lock
                    // stands where the ring would be and the row leads to the plan page.
                    Semantics(
                      button: true,
                      label: context.l10n.upgradeToUnlimited,
                      child: SizedBox(
                        width: 44,
                        height: 44,
                        child: Center(child: Icon(Icons.lock_outline, size: 20, color: OmiColors.textTertiary)),
                      ),
                    )
                  else
                    Semantics(
                      button: !provider.isSelectionMode,
                      checked: item.completed,
                      label: item.completed ? context.l10n.markIncomplete : context.l10n.markComplete,
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: provider.isSelectionMode ? null : () => _toggleCompleted(provider, item),
                        child: SizedBox(
                          width: 44,
                          height: 44,
                          child: Center(child: TaskCompletionMark(completed: item.completed)),
                        ),
                      ),
                    ),
                  // Task text
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            item.description,
                            style: OmiType.body.copyWith(
                              color: item.completed || item.isLocked ? OmiColors.textTertiary : OmiColors.textPrimary,
                              letterSpacing: -0.35,
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
                                Icon(Icons.check_circle_outline, size: 12, color: OmiColors.textTertiary),
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
                  // The due day where the section name doesn't already say it: red while overdue.
                  if (dueLabel != null)
                    Padding(
                      padding: const EdgeInsets.only(left: 8, right: 8),
                      child: Text(
                        dueLabel,
                        style: OmiType.subhead.copyWith(
                          color: category == TaskCategory.overdue && !item.completed
                              ? OmiColors.danger
                              : OmiColors.textTertiary,
                          fontFeatures: const [FontFeature.tabularFigures()],
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
            if (showDivider)
              Positioned(
                left: titleInset,
                right: 4,
                bottom: 0,
                child: Container(height: 0.5, color: OmiColors.border),
              ),
          ],
        ),
      ),
    );
  }

  /// "Wed", "Sun" within a week, "Oct 14" beyond it — only where the section name leaves the day
  /// open (Overdue and Later). Today, Tomorrow and No Deadline already say it.
  String? _dueDayLabel(ActionItemWithMetadata item, TaskCategory category) {
    final due = item.dueAt;
    if (item.completed || due == null || (category != TaskCategory.overdue && category != TaskCategory.later)) {
      return null;
    }
    final now = DateTime.now();
    final local = due.toLocal();
    final days =
        (DateTime(local.year, local.month, local.day).difference(DateTime(now.year, now.month, now.day)).inHours / 24)
            .round();
    final locale = Localizations.localeOf(context).toLanguageTag();
    return days.abs() < 7 ? DateFormat.E(locale).format(local) : DateFormat.MMMd(locale).format(local);
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

  void _showEditSheet(ActionItemWithMetadata item) {
    openTaskPage(context, item);
  }

  /// Where a paywalled task's tap goes, the same as a locked conversation's.
  void _openUpgrade() {
    OmiHaptics.selection();
    routeToPage(context, const UsagePage(showUpgradeDialog: true));
  }
}

/// Vertical padding of a task section header: the space above the label line
/// and the sliver of space between it and the first task row.
const EdgeInsets _sectionHeaderLinePadding = EdgeInsets.only(top: 16, bottom: 4);

/// A section header's label ("Today", "Overdue"): sentence case, quieter than the rows.
TextStyle get _sectionLabelStyle =>
    OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600);

/// The fold mark after a collapsible section's count: down when open, right when folded.
class _SectionChevron extends StatelessWidget {
  const _SectionChevron({required this.expanded});

  final bool expanded;

  @override
  Widget build(BuildContext context) {
    return Icon(
      expanded ? Icons.keyboard_arrow_down_rounded : Icons.keyboard_arrow_right_rounded,
      color: OmiColors.textTertiary,
      size: 16,
    );
  }
}

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
  const _SectionHeaderTapTarget({required this.onTap, required this.child, required this.reach, this.semanticLabel});

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
