import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/providers/home_provider.dart';

import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/home_bottom_bar.dart';

import 'project_task_sections.dart';
import 'task_categorization.dart';
import 'task_delete_undo.dart';
import 'task_hierarchy.dart';
import 'widgets/action_item_form_sheet.dart';
import 'widgets/action_item_shimmer_widget.dart';
import 'widgets/task_row_parts.dart';
import 'widgets/task_selection_action_bar.dart';

// Re-export Goal from goals.dart for use in this file
export 'package:omi/backend/http/api/goals.dart' show Goal;

class ActionItemsPage extends StatefulWidget {
  const ActionItemsPage({super.key, this.selectionBarInFallback = false});

  /// Mounts [TaskSelectionActionBar] over the Flutter presentation, for hosts (the native shell) that
  /// have no outer Stack carrying it. The native presentation has its own bottom bar.
  final bool selectionBarInFallback;

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

  // Native edit mode: each category section takes a reorder permutation. Never while searching or
  // selecting.
  bool _nativeReorderMode = false;

  /// Group the list by project instead of by due date (offered once projects exist).
  bool _groupByProject = false;

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

  late final ActionItemsProvider _selectionOwner;

  @override
  void initState() {
    super.initState();
    _selectionOwner = Provider.of<ActionItemsProvider>(context, listen: false);
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
    // The native selection has no route of its own: leaving the page ends it, after this frame.
    final owner = _selectionOwner;
    if (widget.selectionBarInFallback && nativePresentationEnabled && owner.isSelectionMode) {
      WidgetsBinding.instance.addPostFrameCallback((_) => owner.endSelection());
    }
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
        if (context.read<ReviewProvider?>()?.isOn ?? false)
          PullDownMenuItem(
            title: _groupByProject ? context.l10n.tasksGroupByDate : context.l10n.tasksGroupByProject,
            iconWidget: Icon(_groupByProject ? Icons.event_outlined : Icons.folder_outlined, size: 18),
            onTap: () {
              OmiHaptics.light();
              final review = context.read<ReviewProvider?>();
              if (!_groupByProject && review != null && review.projects.isEmpty) review.loadProjects();
              setState(() => _groupByProject = !_groupByProject);
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

  DateTime? _getDefaultDueDateForCategory(TaskCategory category) => defaultDueDateForCategory(category, DateTime.now());

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
  List<ActionItemWithMetadata> _getOrderedItems(TaskCategory category, List<ActionItemWithMetadata> items) =>
      orderedTaskItems(items);

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
    Provider.of<ActionItemsProvider>(context, listen: false).batchUpdateSortOrders(taskSortOrders(order));

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
        // Successful empty results use the existing icon and conversation guidance.
        final showTypedStatus = apiPhase == ApiViewPhase.error ||
            apiPhase == ApiViewPhase.locked ||
            apiPhase == ApiViewPhase.terminal ||
            apiPhase == ApiViewPhase.authenticationRequired;

        final classic = Scaffold(
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
              // The empty state points to conversation capture on Home.
              if (!categorizedItems.values.every((l) => l.isEmpty)) _buildFab(),
              // The classic shell mounts the selection action bar at the home page's outer Stack so it
              // paints above the BottomNavBar (mirrors the conversations merge bar). The native shell has
              // no such Stack, so its fallback carries the bar itself.
              if (widget.selectionBarInFallback)
                const Positioned(left: 0, right: 0, bottom: 0, child: TaskSelectionActionBar()),
            ],
          ),
        );
        return _buildNativeTasks(provider, categorizedItems, classic, failed: showTypedStatus);
      },
    );
  }

  /// The native Tasks list over the same provider and callbacks; [classic] is its complete fallback.
  /// Selection uses the system edit mode with a bottom bar, and Edit reorders a category in place.
  Widget _buildNativeTasks(
    ActionItemsProvider provider,
    Map<TaskCategory, List<ActionItemWithMetadata>> categorizedItems,
    Widget classic, {
    required bool failed,
  }) {
    final l10n = context.l10n;
    final selecting = provider.isSelectionMode;
    final reordering = _nativeReorderMode && !provider.isSearching && !selecting;
    final loading = provider.isLoading && provider.actionItems.isEmpty;
    final selectedCount = provider.selectedCount;
    final allSelected = provider.actionItems.isNotEmpty && selectedCount == provider.actionItems.length;
    final visible =
        failed ? const <String, List<ActionItemWithMetadata>>{} : _nativeVisibleTasks(provider, categorizedItems);
    final taskIds = {for (final items in visible.values) ...items.map((item) => 'task_${item.id}')};
    return IosNativeSurface(
      title: selecting ? l10n.selectedCount(selectedCount) : l10n.tasks,
      fallback: classic,
      loading: loading,
      failed: failed,
      // The Flutter typed status shows one generic copy for every failed phase.
      errorMessage: failed ? l10n.somethingWentWrong : null,
      empty: provider.isSearching ? l10n.noResultsFound : l10n.noTasksYet,
      searchPlaceholder: l10n.searchActionItems,
      searchValue: provider.searchQuery,
      search: (value) {
        if (_nativeReorderMode) setState(() => _nativeReorderMode = false);
        provider.setSearchQuery(value as String);
      },
      onRefresh: (_) => provider.forceRefreshActionItems(),
      toolbar: [
        if (selecting) ...[
          NativeRow('tasks_cancel', l10n.cancel, symbol: 'xmark', action: (_) => provider.endSelection()),
          NativeRow('tasks_select_all', allSelected ? l10n.deselectAllTasksMenu : l10n.selectAllTasksMenu,
              action: (_) => allSelected ? provider.clearSelection() : provider.selectAllItems()),
          NativeRow('tasks_completed', provider.showCompletedView ? l10n.hideCompletedTasks : l10n.showCompletedTasks,
              action: (_) => provider.toggleShowCompletedView()),
        ] else if (reordering) ...[
          NativeRow('tasks_home', l10n.home,
              symbol: 'house', action: (_) => context.read<HomeProvider>().setIndex(HomeProvider.homeTab)),
          NativeRow('tasks_reorder_done', l10n.done,
              symbol: 'checkmark', action: (_) => setState(() => _nativeReorderMode = false)),
        ] else ...[
          NativeRow('tasks_home', l10n.home,
              symbol: 'house', action: (_) => context.read<HomeProvider>().setIndex(HomeProvider.homeTab)),
          NativeRow('tasks_integrations', l10n.exportButton, symbol: 'square.and.arrow.up', action: (_) {
            OmiHaptics.selection();
            PlatformManager.instance.analytics.exportTasksBannerClicked();
            routeToPage(context, const TaskIntegrationsPage());
          }),
          NativeRow('tasks_add', l10n.newTask,
              symbol: 'plus',
              action: (_) =>
                  _showCreateActionItemSheet(defaultDueDate: _getDefaultDueDateForCategory(TaskCategory.today))),
          NativeRow('tasks_menu', l10n.moreOptions, kind: 'menu', symbol: 'ellipsis', options: {
            'completed': provider.showCompletedView ? l10n.hideCompletedTasks : l10n.showCompletedTasks,
            'select': l10n.selectActionItems,
            'selectAll': allSelected ? l10n.deselectAllTasksMenu : l10n.selectAllTasksMenu,
            if (!provider.isSearching) 'reorder': l10n.edit,
          }, action: (value) {
            if (value == 'completed') provider.toggleShowCompletedView();
            if (value == 'select') {
              _searchFocusNode.unfocus();
              provider.startSelection();
            }
            if (value == 'selectAll') {
              _searchFocusNode.unfocus();
              if (allSelected) {
                provider.clearSelection();
              } else {
                if (!provider.isSelectionMode) provider.startSelection();
                provider.selectAllItems();
              }
            }
            if (value == 'reorder' && !provider.isSearching && !provider.isSelectionMode) {
              setState(() => _nativeReorderMode = true);
            }
          }),
        ],
      ],
      selection: selecting
          ? NativeSelection(
              selectable: taskIds,
              selected: {
                for (final id in provider.selectedItems)
                  if (taskIds.contains('task_$id')) 'task_$id',
              },
              action: (value) => _applyNativeSelection(provider, value as List<String>),
            )
          : null,
      bottomBar: selecting
          ? [
              NativeRow('tasks_selected_count', l10n.selectedCount(selectedCount), kind: 'label'),
              NativeRow('tasks_delete', l10n.deleteSelected,
                  symbol: 'trash',
                  destructive: true,
                  enabled: selectedCount > 0,
                  action: (_) => confirmAndDeleteSelectedTasks(context, provider)),
              NativeRow('tasks_export', selectedCount > 0 ? '${l10n.exportButton} · $selectedCount' : l10n.exportButton,
                  symbol: 'square.and.arrow.up',
                  enabled: selectedCount > 0,
                  action: (_) => exportSelectedTasks(context, provider)),
            ]
          : const [],
      sections: [
        for (final MapEntry(key: id, value: items) in visible.entries)
          if (TaskCategory.values.asNameMap()[id] case final category?)
            NativeSection(
              id,
              [
                for (final item in items) _nativeTaskRow(provider, item, items, selecting: selecting),
                if (provider.showCompletedView && !reordering)
                  NativeRow('tasks_clear_$id', l10n.tasksClearCompleted,
                      destructive: true, action: (_) => _confirmClearCompleted(provider, items)),
              ],
              title: _getCategoryTitle(context, category),
              footer: l10n.tasksCountLabel(items.length),
              collapsible: category == TaskCategory.overdue || category == TaskCategory.noDeadline,
              reorder: reordering ? (value) => _applyNativeReorder(provider, category, value) : null,
            )
          else
            // Search results are one flat list in match order, open and completed alike, as in Flutter.
            NativeSection(id, [for (final item in items) _nativeTaskRow(provider, item, items, selecting: selecting)],
                footer: l10n.tasksCountLabel(items.length)),
        if (visible.isEmpty && !loading && !failed)
          NativeSection('empty', [
            provider.isSearching
                ? NativeRow('tasks_no_results', l10n.noResultsFound, kind: 'label')
                : NativeRow('tasks_empty', l10n.noTasksYet, kind: 'label', subtitle: l10n.tasksEmptyStateMessage),
          ]),
        if (provider.hasMore && !failed)
          NativeSection('pagination', [
            NativeRow('tasks_load_more', l10n.showMore,
                enabled: !provider.isFetching, action: (_) => provider.loadMoreActionItems())
          ]),
      ],
    );
  }

  /// The displayed rows by section id: each non-empty category in order, or while searching every match
  /// in one 'search' section, as the Flutter list shows them.
  Map<String, List<ActionItemWithMetadata>> _nativeVisibleTasks(
    ActionItemsProvider provider,
    Map<TaskCategory, List<ActionItemWithMetadata>> categorizedItems,
  ) {
    if (provider.isSearching) {
      final matches = provider.filteredActionItems;
      return {if (matches.isNotEmpty) 'search': matches};
    }
    return {
      for (final category in TaskCategory.values)
        if (_getOrderedItems(category, categorizedItems[category] ?? []) case final items when items.isNotEmpty)
          category.name: items,
    };
  }

  NativeRow _nativeTaskRow(
    ActionItemsProvider provider,
    ActionItemWithMetadata item,
    List<ActionItemWithMetadata> rows, {
    required bool selecting,
  }) {
    final l10n = context.l10n;
    final goalTitle = _getGoalTitleForTask(item);
    final indent = item.indentLevel.clamp(0, maxTaskIndent);
    final subtitle = [
      if (item.dueAt != null) OmiDateFormat.of(context).dateTime(item.dueAt!),
      if (goalTitle != null) goalTitle,
      if (item.exported && item.exportPlatform != null)
        l10n.exportedToPlatform(taskExportPlatformLabel(item.exportPlatform!)),
    ].join(' · ');
    if (selecting) {
      return NativeRow('task_${item.id}', item.description,
          kind: 'label', symbol: item.completed ? 'checkmark.circle' : 'circle', indent: indent, subtitle: subtitle);
    }
    return NativeRow('task_${item.id}', item.description,
        kind: 'task',
        value: item.completed,
        indent: indent,
        subtitle: subtitle,
        options: {
          'open': l10n.open,
          'select': l10n.selectOption,
          if (item.indentLevel < maxIndentFor(item, rows)) 'indent': l10n.indentTask,
          if (item.indentLevel > 0) 'outdent': l10n.outdentTask,
          'due': l10n.setDueDate,
          'complete': item.completed ? l10n.markIncomplete : l10n.markComplete,
          'delete': l10n.delete,
        },
        swipeLeading: const [
          'complete'
        ],
        swipeTrailing: const [
          'delete'
        ], action: (value) async {
      if (value is bool || value == 'complete') {
        await _toggleCompleted(provider, item);
      } else if (value == 'open') {
        _showEditSheet(item);
      } else if (value == 'delete') {
        _deleteTask(item);
      } else if (value == 'select') {
        _searchFocusNode.unfocus();
        if (_nativeReorderMode) setState(() => _nativeReorderMode = false);
        provider.startSelectionWithItem(item.id);
      } else if (value == 'indent') {
        _incrementIndent(item.id);
      } else if (value == 'outdent') {
        _decrementIndent(item.id);
      } else if (value == 'due') {
        // The choice applies only for the page and account that asked.
        final owner = AuthService.instance.captureSessionSnapshot();
        bool current() => mounted && owner != null && AuthService.instance.isSessionSnapshotCurrent(owner);
        await showOmiRowMenu(context, title: l10n.setDueDate, actions: [
          // The categories a drop could reach: the completed view has no Overdue section.
          for (final target in TaskCategory.values)
            if (target != _getCategoryForItem(item) && !(target == TaskCategory.overdue && provider.showCompletedView))
              OmiMenuAction(
                  icon: Icons.event_outlined,
                  label: _getCategoryTitle(context, target),
                  onSelected: () {
                    if (current()) _updateTaskCategory(item, target);
                  }),
        ]);
      }
    });
  }

  /// '_selection' is the complete desired set of visible rows. Rows it adds or drops select or deselect
  /// with their visible descendants, as a tap with cascade does; removals apply first.
  void _applyNativeSelection(ActionItemsProvider provider, List<String> desired) {
    final visible = _nativeVisibleTasks(provider, _categorizeItems(provider.actionItems, provider.showCompletedView));
    final wanted = desired.toSet();
    final changes = [
      for (final items in visible.values)
        for (final item in items)
          if (provider.isItemSelected(item.id) != wanted.contains('task_${item.id}'))
            (item, visibleDescendantIds(item, items), wanted.contains('task_${item.id}')),
    ];
    for (final (item, descendants, _) in changes.where((change) => !change.$3)) {
      for (final id in [item.id, ...descendants]) {
        provider.deselectItem(id);
      }
    }
    for (final (item, descendants, _) in changes.where((change) => change.$3)) {
      for (final id in [item.id, ...descendants]) {
        provider.selectItem(id);
      }
    }
  }

  /// '_reorder:<category>' is an exact permutation of the category's current rows. The new order is
  /// stored as sort orders, and a moved row deeper than its new predecessor allows is clamped, the same
  /// as a drop without horizontal travel. Category moves go through Set Due Date.
  void _applyNativeReorder(ActionItemsProvider provider, TaskCategory category, Object? value) {
    final current =
        orderedTaskItems(_categorizeItems(provider.actionItems, provider.showCompletedView)[category] ?? []);
    final byId = {for (final item in current) 'task_${item.id}': item};
    if (value is! List ||
        value.length != current.length ||
        value.toSet().length != value.length ||
        !value.every(byId.containsKey) ||
        provider.isSearching ||
        provider.isSelectionMode) {
      throw PlatformException(code: 'invalid_native_action');
    }
    final reordered = [for (final id in value) byId[id]!];
    provider.batchUpdateSortOrders(taskSortOrders([for (final item in reordered) item.id]));
    final moved = movedTaskIds(current.map((item) => item.id).toList(), reordered.map((item) => item.id).toList());
    for (final (index, item) in reordered.indexed) {
      if (!moved.contains(item.id)) continue;
      final maxIndent = maxIndentForDrop(draggedItem: item, targetIdx: index, isAbove: true, categoryItems: reordered);
      if (item.indentLevel > maxIndent) provider.updateItemIndentLevel(item.id, maxIndent);
    }
    OmiHaptics.medium();
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
      slivers: [SliverFillRemaining(hasScrollBody: false, child: Center(child: _buildEmptyTasksContent()))],
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
        ] else if (_groupByProject) ...[
          const SliverPadding(padding: EdgeInsets.only(top: 6)),
          ...projectTaskSections(
            context: context,
            items: categorizedItems.values.expand((items) => items).toList(growable: false),
            projects: context.watch<ReviewProvider?>()?.projects ?? const {},
            buildRow: (item, group) =>
                _buildTaskItem(item, provider, category: _getCategoryForItem(item), categoryItems: group),
          ),
        ] else ...[
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
                        TaskSectionHeaderTapTarget(
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
                              Text(title, style: taskSectionLabelStyle),
                              if (orderedItems.isNotEmpty) ...[
                                const SizedBox(width: 8),
                                TaskSectionCount(orderedItems.length),
                              ],
                            ],
                          ),
                        )
                      else
                        Padding(
                          padding: taskSectionHeaderLinePadding,
                          child: Text(title, style: taskSectionLabelStyle),
                        ),
                      const Spacer(),
                      if (category != TaskCategory.noDeadline) ...[
                        if (provider.showCompletedView && orderedItems.isNotEmpty)
                          // The count and the ✕ are one control: "clear these N".
                          TaskSectionHeaderTapTarget(
                            semanticLabel: context.l10n.tasksClearCompleted,
                            reach: const EdgeInsets.only(left: 16),
                            onTap: () => _confirmClearCompleted(provider, orderedItems),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                TaskSectionCount(orderedItems.length),
                                const SizedBox(width: 8),
                                Icon(Icons.close, size: 14, color: OmiColors.textTertiary),
                              ],
                            ),
                          )
                        else if (orderedItems.isNotEmpty)
                          Padding(padding: taskSectionHeaderLinePadding, child: TaskSectionCount(orderedItems.length)),
                      ] else if (provider.showCompletedView && orderedItems.isNotEmpty && _noDeadlineExpanded)
                        TaskSectionHeaderTapTarget(
                          semanticLabel: context.l10n.tasksClearCompleted,
                          reach: const EdgeInsets.only(left: 30),
                          onTap: () => _confirmClearCompleted(provider, orderedItems),
                          child: Icon(Icons.close, size: 14, color: OmiColors.textTertiary),
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
                TaskSectionHeaderTapTarget(
                  reach: const EdgeInsets.only(right: 24),
                  onTap: () {
                    setState(() {
                      _overdueExpanded = !_overdueExpanded;
                    });
                  },
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        _overdueExpanded ? Icons.expand_less : Icons.expand_more,
                        color: OmiColors.textTertiary,
                        size: 16,
                      ),
                      const SizedBox(width: 4),
                      Text(context.l10n.tasksOverdue, style: taskSectionLabelStyle),
                      const SizedBox(width: 8),
                      TaskSectionCount(orderedItems.length),
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

    Provider.of<ActionItemsProvider>(context, listen: false).batchUpdateSortOrders(taskSortOrders(order));

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
        final maxIndent = maxIndentForDrop(
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

  /// Long-press menu: the same shape as memories and conversations, with Select for multi-select
  /// and the indent controls that used to hide behind a swipe.
  void _showTaskMenu(ActionItemWithMetadata item, List<ActionItemWithMetadata> categoryItems) {
    final l10n = context.l10n;
    final provider = Provider.of<ActionItemsProvider>(context, listen: false);
    final maxIndent = maxIndentFor(item, categoryItems);
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
          provider.toggleItemSelection(item.id, cascadeIds: visibleDescendantIds(item, categoryItems));
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
                    decoration: BoxDecoration(color: OmiColors.surface3, borderRadius: OmiRadius.pillAll),
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
                            Icon(Icons.check_circle_outline, size: 12, color: OmiColors.textTertiary),
                            const SizedBox(width: 4),
                            Text(
                              context.l10n.exportedToPlatform(taskExportPlatformLabel(item.exportPlatform!)),
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

  void _showEditSheet(ActionItemWithMetadata item) {
    showActionItemFormSheet(context, actionItem: item);
  }
}
