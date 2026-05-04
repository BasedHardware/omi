import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/ui/atoms/omi_search_input.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'widgets/action_item_form_sheet.dart';

// Re-export Goal from goals.dart for use in this file
export 'package:omi/backend/http/api/goals.dart' show Goal;

enum TaskCategory { today, tomorrow, later, noDeadline, overdue }

class ActionItemsPage extends StatefulWidget {
  final VoidCallback? onAddGoal;

  const ActionItemsPage({super.key, this.onAddGoal});

  @override
  State<ActionItemsPage> createState() => _ActionItemsPageState();
}

class _ActionItemsPageState extends State<ActionItemsPage> with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();
  final AppReviewService _appReviewService = AppReviewService();

  // Task -> goal mapping
  final Map<String, String> _taskGoalLinks = {};

  // Track the item being hovered over during drag
  String? _hoveredItemId;
  bool _hoverAbove = false; // true = insert above, false = insert below

  // Whether the current long-press drag has actually moved (reorder) or stayed still (select)
  bool _dragHasMoved = false;

  // Overdue section expanded by default — missed deadlines are the most
  // important thing to surface, hiding them behind a tap caused regret.
  bool _overdueExpanded = true;

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
      MixpanelManager().actionItemsPageOpened();
      final provider = Provider.of<ActionItemsProvider>(context, listen: false);
      if (provider.actionItems.isEmpty) {
        provider.fetchActionItems(showShimmer: true);
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
            MixpanelManager().goalCreated(
              goalId: created.id,
              titleLength: title.length,
              targetValue: target,
              source: 'tasks_page',
            );
          }
        },
      ),
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
          bottom: 100,
          child: FloatingActionButton(
            heroTag: 'action_items_fab',
            onPressed: () {
              HapticFeedback.lightImpact();
              _showCreateActionItemSheet(defaultDueDate: _getDefaultDueDateForCategory(TaskCategory.today));
            },
            backgroundColor: Colors.deepPurple,
            child: const Icon(Icons.add, color: Colors.white),
          ),
        );
      },
    );
  }

  Widget _buildPageHeader(ActionItemsProvider provider) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 16, 4),
      child: Row(
        children: [
          Expanded(
            child: OmiSearchInput(
              controller: _searchController,
              focusNode: _searchFocusNode,
              hint: context.l10n.searchActionItems,
              highlightOnFocus: false,
              onChanged: (value) {
                _searchDebouncer.run(() {
                  if (!mounted) return;
                  provider.setSearchQuery(value);
                });
              },
              onClear: () {
                _searchController.clear();
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
    // "Select all" flips to "Deselect all" once every selectable task is
    // already selected. `selectAllItems()` skips items that are already
    // exported, so we compare against the unexported count — otherwise the
    // label never flips when any task has been exported before.
    final selectableCount = provider.actionItems.where((i) => !i.exported).length;
    final allSelected = selectableCount > 0 && provider.selectedCount == selectableCount;

    return PopupMenuButton<String>(
      tooltip: '',
      icon: Icon(Icons.more_horiz_rounded, color: Colors.grey[400], size: 22),
      color: const Color(0xFF1F1F25),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      onSelected: (value) {
        switch (value) {
          case 'select':
            HapticFeedback.lightImpact();
            _searchFocusNode.unfocus();
            provider.startSelection();
            break;
          case 'select_all':
            HapticFeedback.lightImpact();
            _searchFocusNode.unfocus();
            if (allSelected) {
              // Stay in selection mode but clear — user can re-pick individuals.
              provider.clearSelection();
            } else {
              if (!provider.isSelectionMode) provider.startSelection();
              provider.selectAllItems();
            }
            break;
          case 'toggle_completed':
            HapticFeedback.lightImpact();
            provider.toggleShowCompletedView();
            break;
        }
      },
      itemBuilder: (context) => [
        _menuItem(
          value: 'select',
          icon: Icons.check_box_outlined,
          label: context.l10n.selectActionItems,
        ),
        _menuItem(
          value: 'select_all',
          icon: allSelected ? Icons.deselect_rounded : Icons.select_all_rounded,
          label: allSelected ? context.l10n.deselectAllTasksMenu : context.l10n.selectAllTasksMenu,
        ),
        _menuItem(
          value: 'toggle_completed',
          icon: showingCompleted ? Icons.visibility_off_outlined : Icons.visibility_outlined,
          label: showingCompleted ? context.l10n.hideCompletedTasks : context.l10n.showCompletedTasks,
        ),
      ],
    );
  }

  PopupMenuItem<String> _menuItem({required String value, required IconData icon, required String label}) {
    return PopupMenuItem<String>(
      value: value,
      child: Row(
        children: [
          Icon(icon, color: Colors.white, size: 18),
          const SizedBox(width: 12),
          Text(label, style: const TextStyle(color: Colors.white, fontSize: 14)),
        ],
      ),
    );
  }

  Widget _buildNoSearchResultsContent() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.search_off_rounded, size: 48, color: Colors.grey[600]),
          const SizedBox(height: 12),
          Text(
            context.l10n.noResultsFound,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  // Categorize items by deadline
  Map<TaskCategory, List<ActionItemWithMetadata>> _categorizeItems(
    List<ActionItemWithMetadata> items,
    bool showCompleted,
  ) {
    final now = DateTime.now();
    final startOfToday = DateTime(now.year, now.month, now.day);
    final startOfTomorrow = DateTime(now.year, now.month, now.day + 1);
    final startOfDayAfterTomorrow = DateTime(now.year, now.month, now.day + 2);
    final sevenDaysAgo = now.subtract(const Duration(days: 7));

    final Map<TaskCategory, List<ActionItemWithMetadata>> categorized = {
      TaskCategory.today: [],
      TaskCategory.tomorrow: [],
      TaskCategory.noDeadline: [],
      TaskCategory.later: [],
      TaskCategory.overdue: [],
    };

    for (var item in items) {
      // Skip completed items unless showing completed
      if (item.completed && !showCompleted) continue;
      if (!item.completed && showCompleted) continue;

      if (item.dueAt == null) {
        // No deadline tasks older than 7 days go to overdue
        if (!showCompleted && item.createdAt != null && item.createdAt!.isBefore(sevenDaysAgo)) {
          categorized[TaskCategory.overdue]!.add(item);
        } else {
          categorized[TaskCategory.noDeadline]!.add(item);
        }
      } else {
        final dueDate = item.dueAt!;
        if (!showCompleted && dueDate.isBefore(startOfToday)) {
          // Due date in the past → overdue
          categorized[TaskCategory.overdue]!.add(item);
        } else if (dueDate.isBefore(startOfTomorrow)) {
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

  Future<void> _confirmClearCompleted(ActionItemsProvider provider, List<ActionItemWithMetadata> items) async {
    HapticFeedback.lightImpact();
    final shouldClear = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: const Color(0xFF1F1F22),
        title: Text(
          context.l10n.tasksClearCompleted,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
        content: Text(context.l10n.tasksCleanTodayMessage, style: TextStyle(color: Colors.grey[300], fontSize: 14)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(context.l10n.cancel, style: TextStyle(color: Colors.grey[400])),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: Text(context.l10n.delete, style: const TextStyle(fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );

    if (shouldClear != true) return;
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
    HapticFeedback.lightImpact();
  }

  void _decrementIndent(String itemId) {
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final item = provider.actionItems.where((i) => i.id == itemId).firstOrNull;
    if (item == null) return;
    final current = item.indentLevel;
    if (current > 0) {
      provider.updateItemIndentLevel(itemId, current - 1);
    }
    HapticFeedback.lightImpact();
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
    HapticFeedback.mediumImpact();
  }

  // Delete task with swipe
  void _deleteTask(ActionItemWithMetadata item) {
    HapticFeedback.mediumImpact();
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    provider.deleteActionItem(item);
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
          body: Stack(
            children: [
              GestureDetector(
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
              // Hide the purple corner FAB when the empty-state already
              // shows its own "Create Action Item" pill — otherwise we
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
    return const Center(child: CircularProgressIndicator(color: Colors.deepPurple));
  }

  Widget _buildEmptyTasksList() {
    return CustomScrollView(
      controller: _scrollController,
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        const SliverPadding(padding: EdgeInsets.only(top: 12)),
        SliverToBoxAdapter(child: _buildGoalsRow()),
        const SliverPadding(padding: EdgeInsets.only(top: 8)),
        SliverFillRemaining(
          hasScrollBody: false,
          child: Center(child: _buildEmptyTasksContent()),
        ),
      ],
    );
  }

  Widget _buildEmptyTasksContent() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 0, 32, 120),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Layered icon: soft purple aura behind a tactile glassy tile.
          Stack(
            alignment: Alignment.center,
            children: [
              Container(
                width: 160,
                height: 160,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      Colors.deepPurple.withValues(alpha: 0.35),
                      Colors.deepPurple.withValues(alpha: 0.0),
                    ],
                    stops: const [0.0, 1.0],
                  ),
                ),
              ),
              Container(
                width: 88,
                height: 88,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(26),
                  gradient: const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [Color(0xFF7B5CFF), Color(0xFF5733E0)],
                  ),
                  border: Border.all(color: Colors.white.withValues(alpha: 0.08), width: 1),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.deepPurple.withValues(alpha: 0.45),
                      blurRadius: 30,
                      spreadRadius: 2,
                      offset: const Offset(0, 12),
                    ),
                  ],
                ),
                child: const Icon(Icons.task_alt_rounded, size: 42, color: Colors.white),
              ),
            ],
          ),
          const SizedBox(height: 28),
          Text(
            context.l10n.noTasksYet,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.3,
            ),
          ),
          const SizedBox(height: 10),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 280),
            child: Text(
              context.l10n.tasksEmptyStateMessage,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.55),
                fontSize: 15,
                height: 1.5,
              ),
            ),
          ),
          const SizedBox(height: 28),
          // Primary action: open the new-task sheet so users have an obvious next step.
          GestureDetector(
            onTap: () {
              HapticFeedback.lightImpact();
              showModalBottomSheet(
                context: context,
                isScrollControlled: true,
                backgroundColor: Colors.transparent,
                builder: (_) => const ActionItemFormSheet(),
              );
            },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(28),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.35),
                    blurRadius: 18,
                    offset: const Offset(0, 6),
                  ),
                ],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.add_rounded, color: Color(0xFF1F1F25), size: 20),
                  const SizedBox(width: 8),
                  Text(
                    context.l10n.createActionItem,
                    style: const TextStyle(
                      color: Color(0xFF1F1F25),
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      letterSpacing: -0.1,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
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
            SliverFillRemaining(
              hasScrollBody: false,
              child: Center(child: _buildNoSearchResultsContent()),
            )
          else
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (context, index) {
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
                },
                childCount: filteredItems.length,
              ),
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

        // Bottom padding
        const SliverPadding(padding: EdgeInsets.only(bottom: 100)),
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
                padding: const EdgeInsets.fromLTRB(4, 12, 4, 8),
                child: Row(
                  children: [
                    Text(
                      context.l10n.goals,
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                    const Spacer(),
                    if (!actionProvider.isSelectionMode) ...[
                      if (goals.length < 4)
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
                            child: Icon(Icons.add, size: 18, color: Colors.grey[400]),
                          ),
                        ),
                    ],
                  ],
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
                // Section header — quieter than the page title; reads as a label,
                // not a heading.
                Padding(
                  padding: const EdgeInsets.fromLTRB(4, 16, 4, 4),
                  child: Row(
                    children: [
                      Text(
                        title.toUpperCase(),
                        style: TextStyle(
                          color: Colors.grey[500],
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.8,
                        ),
                      ),
                      const Spacer(),
                      if (provider.showCompletedView && orderedItems.isNotEmpty)
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text('${orderedItems.length}', style: TextStyle(color: Colors.grey[600], fontSize: 12)),
                            const SizedBox(width: 8),
                            GestureDetector(
                              onTap: () => _confirmClearCompleted(provider, orderedItems),
                              child: Icon(Icons.close, size: 14, color: Colors.grey[600]),
                            ),
                          ],
                        )
                      else if (orderedItems.isNotEmpty)
                        Text('${orderedItems.length}', style: TextStyle(color: Colors.grey[600], fontSize: 12)),
                    ],
                  ),
                ),

                // Drop zone for first position
                if (orderedItems.isNotEmpty)
                  _buildFirstPositionDropZone(category, orderedItems, candidateData.isNotEmpty),

                // Task items. Row padding alone carries the rhythm — no
                // dividers between rows; matches Things 3 / Apple Reminders.
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
            padding: const EdgeInsets.fromLTRB(4, 16, 4, 4),
            child: Row(
              children: [
                GestureDetector(
                  onTap: () {
                    setState(() {
                      _overdueExpanded = !_overdueExpanded;
                    });
                  },
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(_overdueExpanded ? Icons.expand_less : Icons.expand_more, color: Colors.grey[500], size: 16),
                      const SizedBox(width: 4),
                      Text(
                        context.l10n.tasksOverdue.toUpperCase(),
                        style: TextStyle(
                          color: Colors.grey[500],
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.8,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text('${orderedItems.length}', style: TextStyle(color: Colors.grey[600], fontSize: 12)),
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
    HapticFeedback.mediumImpact();
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

        // Reorder within category
        _reorderItemInCategory(draggedItem, item.id, _hoverAbove, category, categoryItems);

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
      builder: (ctx, candidateData, rejectedData) {
        itemContext = ctx;
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Drop indicator above
            if (isHovered && _hoverAbove && candidateData.isNotEmpty)
              Container(
                height: 2,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(color: Colors.deepPurple, borderRadius: BorderRadius.circular(1)),
              ),
            _buildDraggableTaskItem(item, provider, indentLevel, indentWidth),
            // Drop indicator below
            if (isHovered && !_hoverAbove && candidateData.isNotEmpty)
              Container(
                height: 2,
                margin: const EdgeInsets.symmetric(horizontal: 4),
                decoration: BoxDecoration(color: Colors.deepPurple, borderRadius: BorderRadius.circular(1)),
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

    // In selection mode: no drag, no swipe — just tappable content.
    if (provider.isSelectionMode) {
      return taskContent;
    }

    Widget makeDraggable(Widget child) {
      return LongPressDraggable<ActionItemWithMetadata>(
        data: item,
        delay: const Duration(milliseconds: 400),
        hapticFeedbackOnStart: true,
        onDragStarted: () {
          _dragHasMoved = false;
          HapticFeedback.mediumImpact();
        },
        onDragUpdate: (_) {
          _dragHasMoved = true;
        },
        onDragEnd: (details) {
          if (!_dragHasMoved) {
            // Long-press without movement → enter selection mode
            final p = Provider.of<ActionItemsProvider>(context, listen: false);
            p.startSelectionWithItem(item.id);
          }
          setState(() {
            _hoveredItemId = null;
            _dragHasMoved = false;
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
                BoxShadow(color: Colors.black.withValues(alpha: 0.3), blurRadius: 10, offset: const Offset(0, 4)),
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
        childWhenDragging: Opacity(opacity: 0.3, child: child),
        child: child,
      );
    }

    // If at indent 0, allow swipe-right to mark complete and swipe-left to delete.
    if (indentLevel == 0) {
      return Dismissible(
        key: Key('dismiss_${item.id}'),
        direction: provider.isSelectionMode ? DismissDirection.none : DismissDirection.horizontal,
        dismissThresholds: const {DismissDirection.startToEnd: 0.3, DismissDirection.endToStart: 0.3},
        confirmDismiss: (direction) async {
          if (direction == DismissDirection.startToEnd) {
            HapticFeedback.lightImpact();
            await provider.updateActionItemState(item, !item.completed);
            if (!item.completed) _onActionItemCompleted();
            return false;
          }
          return true;
        },
        background: Container(
          alignment: Alignment.centerLeft,
          padding: const EdgeInsets.only(left: 20.0),
          decoration: BoxDecoration(
            color: item.completed ? Colors.grey[700] : Colors.green[700],
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(item.completed ? Icons.undo : Icons.check, color: Colors.white),
        ),
        secondaryBackground: Container(
          alignment: Alignment.centerRight,
          padding: const EdgeInsets.only(right: 20.0),
          decoration: BoxDecoration(color: Colors.red, borderRadius: BorderRadius.circular(8)),
          child: const Icon(Icons.delete, color: Colors.white),
        ),
        onDismissed: (direction) {
          if (direction == DismissDirection.endToStart) {
            _deleteTask(item);
          }
        },
        child: provider.isSelectionMode ? taskContent : makeDraggable(taskContent),
      );
    }

    // If indented, use GestureDetector for indent changes + draggable
    return GestureDetector(
      onHorizontalDragEnd: provider.isSelectionMode
          ? null
          : (details) {
              if (details.primaryVelocity != null) {
                if (details.primaryVelocity! > 200) {
                  _incrementIndent(item.id);
                } else if (details.primaryVelocity! < -200) {
                  _decrementIndent(item.id);
                }
              }
            },
      child: provider.isSelectionMode ? taskContent : makeDraggable(taskContent),
    );
  }

  TaskCategory _getCategoryForItem(ActionItemWithMetadata item) {
    final now = DateTime.now();
    final startOfToday = DateTime(now.year, now.month, now.day);
    final startOfTomorrow = DateTime(now.year, now.month, now.day + 1);
    final startOfDayAfterTomorrow = DateTime(now.year, now.month, now.day + 2);

    if (item.dueAt == null) {
      final sevenDaysAgo = now.subtract(const Duration(days: 7));
      if (item.createdAt != null && item.createdAt!.isBefore(sevenDaysAgo)) {
        return TaskCategory.overdue;
      }
      return TaskCategory.noDeadline;
    }
    final dueDate = item.dueAt!;
    if (dueDate.isBefore(startOfToday)) {
      return TaskCategory.overdue;
    } else if (dueDate.isBefore(startOfTomorrow)) {
      return TaskCategory.today;
    } else if (dueDate.isBefore(startOfDayAfterTomorrow)) {
      return TaskCategory.tomorrow;
    } else {
      return TaskCategory.later;
    }
  }

  Widget _buildTaskItemContent(ActionItemWithMetadata item, ActionItemsProvider provider, double indentWidth) {
    final indentLevel = _getIndentLevel(item);
    final goalTitle = _getGoalTitleForTask(item);
    final isSelected = provider.isSelectionMode && provider.isItemSelected(item.id);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        if (provider.isSelectionMode) {
          HapticFeedback.selectionClick();
          provider.toggleItemSelection(item.id);
        } else {
          _showEditSheet(item);
        }
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        margin: EdgeInsets.zero,
        decoration: BoxDecoration(
          color: isSelected ? Colors.deepPurple.withValues(alpha: 0.15) : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
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
                    decoration: BoxDecoration(color: Colors.grey[700], borderRadius: BorderRadius.circular(1)),
                  ),
                ),
              // Completion circle — always shown. Read-only in selection mode
              // (the row tap drives selection there); tappable otherwise.
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: provider.isSelectionMode
                    ? null
                    : () async {
                        HapticFeedback.lightImpact();
                        await provider.updateActionItemState(item, !item.completed);
                        if (!item.completed) _onActionItemCompleted();
                      },
                child: SizedBox(
                  width: 44,
                  height: 48,
                  child: Center(child: _buildCheckbox(item.completed)),
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
                        style: TextStyle(
                          color: item.completed ? Colors.grey[500] : Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                          letterSpacing: -0.2,
                          decoration: item.completed ? TextDecoration.lineThrough : null,
                          decorationColor: Colors.grey[600],
                        ),
                      ),
                      if (goalTitle != null) ...[
                        const SizedBox(height: 4),
                        Text(goalTitle, style: TextStyle(color: Colors.grey[600], fontSize: 12)),
                      ],
                      if (item.exported && item.exportPlatform != null) ...[
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            Icon(Icons.check_circle_outline, size: 12, color: Colors.grey[600]),
                            const SizedBox(width: 4),
                            Text(
                              'Exported to ${_exportPlatformLabel(item.exportPlatform!)}',
                              style: TextStyle(color: Colors.grey[600], fontSize: 11),
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
              // Exported items show a disabled square — they can't be re-exported.
              if (provider.isSelectionMode)
                Padding(
                  padding: const EdgeInsets.only(left: 8, right: 8),
                  child:
                      item.exported ? _buildSelectionSquare(false, disabled: true) : _buildSelectionSquare(isSelected),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCheckbox(bool isCompleted) {
    if (isCompleted) {
      return Container(
        width: 22,
        height: 22,
        decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.amber),
        child: const Icon(Icons.check, size: 14, color: Colors.black),
      );
    }
    // Incomplete: dashed outline circle (Joi-inspired). Quieter than a solid
    // gray ring so the task title carries the visual weight.
    return CustomPaint(
      size: const Size(22, 22),
      painter: _DashedCirclePainter(color: Colors.grey[500]!, strokeWidth: 1.5, dashLength: 3, gapLength: 3),
    );
  }

  /// Trailing selection box rendered only in selection mode. Rounded **square**
  /// — different shape from the leading completion circle so users can't
  /// confuse "selected for bulk action" with "marked as done".
  Widget _buildSelectionSquare(bool isSelected, {bool disabled = false}) {
    if (disabled) {
      return Container(
        width: 22,
        height: 22,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: Colors.grey[800]!, width: 1.5),
          color: Colors.grey[850],
        ),
        child: Icon(Icons.check, size: 14, color: Colors.grey[600]),
      );
    }
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      width: 22,
      height: 22,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: isSelected ? Colors.deepPurple : Colors.grey[600]!, width: 2),
        color: isSelected ? Colors.deepPurple : Colors.transparent,
      ),
      child: isSelected ? const Icon(Icons.check, size: 14, color: Colors.white) : null,
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
        MixpanelManager().goalItemTappedForEdit(goalId: goal.id, source: 'tasks_page');
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
                    painter: _CircularProgressPainter(
                      progress: progress.clamp(0.0, 1.0),
                      color: progress >= 1.0 ? Colors.amber : Colors.grey.shade600,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
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
    );

    if (provider.isSelectionMode) return goalContent;

    return Dismissible(
      key: Key('goal_${goal.id}'),
      direction: DismissDirection.endToStart,
      confirmDismiss: (direction) async {
        HapticFeedback.mediumImpact();
        return await showDialog<bool>(
              context: context,
              builder: (context) => AlertDialog(
                backgroundColor: const Color(0xFF1F1F25),
                title: Text(context.l10n.deleteGoal, style: const TextStyle(color: Colors.white)),
                content: Text('Delete "${goal.title}"?', style: const TextStyle(color: Colors.white70)),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(context, false), child: Text(context.l10n.cancel)),
                  TextButton(
                    onPressed: () => Navigator.pop(context, true),
                    style: TextButton.styleFrom(foregroundColor: Colors.red),
                    child: Text(context.l10n.delete),
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
        decoration: BoxDecoration(color: Colors.red, borderRadius: BorderRadius.circular(8)),
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        child: const Icon(Icons.delete_outline, color: Colors.white),
      ),
      child: goalContent,
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
          await goalsProvider.updateGoal(goal.id, title: title, currentValue: current, targetValue: target);
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
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
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
                decoration: BoxDecoration(color: Colors.grey.shade700, borderRadius: BorderRadius.circular(2)),
              ),
              Text(
                context.l10n.addGoal,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 24),
              // Title field
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(context.l10n.goalTitle, style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12)),
                  const SizedBox(height: 8),
                  TextField(
                    controller: titleController,
                    autofocus: true,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: Colors.white.withOpacity(0.08),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
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
                          style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12),
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
                        Text(context.l10n.target, style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12)),
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
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
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

  const _GoalEditSheet({required this.goal, required this.onSave, required this.onDelete});

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
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
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
                decoration: BoxDecoration(color: Colors.grey.shade700, borderRadius: BorderRadius.circular(2)),
              ),
              Text(
                context.l10n.editGoal,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 24),
              // Title field
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(context.l10n.goalTitle, style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12)),
                  const SizedBox(height: 8),
                  TextField(
                    controller: titleController,
                    autofocus: true,
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: Colors.white.withOpacity(0.08),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
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
                          style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12),
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
                        Text(context.l10n.target, style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12)),
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
                            title: Text(context.l10n.deleteGoal, style: const TextStyle(color: Colors.white)),
                            content: Text(
                              'Delete "${widget.goal.title}"?',
                              style: const TextStyle(color: Colors.white70),
                            ),
                            actions: [
                              TextButton(
                                onPressed: () => Navigator.pop(context, false),
                                child: Text(context.l10n.cancel),
                              ),
                              TextButton(
                                onPressed: () => Navigator.pop(context, true),
                                style: TextButton.styleFrom(foregroundColor: Colors.red),
                                child: Text(context.l10n.delete),
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
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
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

/// Paints a dashed circle outline. Used for incomplete-task indicators —
/// signals "open" without competing with the title for visual weight.
class _DashedCirclePainter extends CustomPainter {
  final Color color;
  final double strokeWidth;
  final double dashLength;
  final double gapLength;

  _DashedCirclePainter({
    required this.color,
    required this.strokeWidth,
    required this.dashLength,
    required this.gapLength,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width / 2) - (strokeWidth / 2);
    final circumference = 2 * 3.141592653589793 * radius;
    final segmentLength = dashLength + gapLength;
    final segments = (circumference / segmentLength).floor();
    final adjustedSegment = circumference / segments;
    final dashAngle = (dashLength / adjustedSegment) * (2 * 3.141592653589793 / segments);
    final stepAngle = 2 * 3.141592653589793 / segments;

    for (var i = 0; i < segments; i++) {
      final startAngle = i * stepAngle;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        startAngle,
        dashAngle,
        false,
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_DashedCirclePainter oldDelegate) =>
      oldDelegate.color != color ||
      oldDelegate.strokeWidth != strokeWidth ||
      oldDelegate.dashLength != dashLength ||
      oldDelegate.gapLength != gapLength;
}
