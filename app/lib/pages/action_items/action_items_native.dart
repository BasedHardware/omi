part of 'action_items_page.dart';

extension _ActionItemsNative on _ActionItemsPageState {
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
    // Watched so the toggle appears with Review and the groups follow the loaded projects.
    final reviewOn = context.watch<ReviewProvider?>()?.isOn ?? false;
    final groupTitle = _groupByProject ? l10n.tasksGroupByDate : l10n.tasksGroupByProject;
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
        if (_nativeReorderMode) _updateNative(() => _nativeReorderMode = false);
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
          if (reviewOn) NativeRow('tasks_group', groupTitle, action: (_) => _toggleGroupByProject()),
        ] else if (reordering) ...[
          NativeRow('tasks_home', l10n.home,
              symbol: 'house', action: (_) => context.read<HomeProvider>().setIndex(HomeProvider.homeTab)),
          NativeRow('tasks_reorder_done', l10n.done,
              symbol: 'checkmark', action: (_) => _updateNative(() => _nativeReorderMode = false)),
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
            if (reviewOn) 'groupByProject': groupTitle,
            if (!provider.isSearching) 'reorder': l10n.edit,
          }, action: (value) {
            if (value == 'completed') provider.toggleShowCompletedView();
            if (value == 'groupByProject' && reviewOn) _toggleGroupByProject();
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
              _updateNative(() => _nativeReorderMode = true);
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
              reorder: reordering ? (value) => _applyNativeReorder(provider, id, value) : null,
            )
          else if (isNativeProjectSection(id))
            nativeProjectTaskSection(
                context, id, [for (final item in items) _nativeTaskRow(provider, item, items, selecting: selecting)],
                reorder: reordering ? (value) => _applyNativeReorder(provider, id, value) : null)
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
    if (_groupByProject) return nativeProjectTaskGroups(context, categorizedItems.values);
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
        if (_nativeReorderMode) _updateNative(() => _nativeReorderMode = false);
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

  /// '_reorder:<section>' is an exact permutation of a category's or project group's current rows. The new
  /// order is stored as sort orders, and a moved row deeper than its new predecessor allows is clamped, the
  /// same as a drop without horizontal travel. Category moves go through Set Due Date.
  void _applyNativeReorder(ActionItemsProvider provider, String sectionId, Object? value) {
    final current =
        _nativeVisibleTasks(provider, _categorizeItems(provider.actionItems, provider.showCompletedView))[sectionId];
    final byId = {for (final item in current ?? const <ActionItemWithMetadata>[]) 'task_${item.id}': item};
    if (current == null ||
        value is! List ||
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
}
