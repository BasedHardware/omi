import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/action_items.dart' as api;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/services/action_item_export_service.dart';
import 'package:omi/pages/settings/task_integrations_page.dart';
import 'package:omi/services/apple_reminders_service.dart';
import 'package:omi/services/notifications/action_item_notification_handler.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';

class ActionItemsProvider extends ChangeNotifier {
  List<ActionItemWithMetadata> _actionItems = [];

  bool _isLoading = false;
  bool _isFetching = false;
  bool _hasMore = false;

  bool _includeCompleted = true;

  // UI filter: show completed tasks view
  bool _showCompletedView = false;

  // Date range filter
  DateTime? _startDate;
  DateTime? _endDate;

  // Debounce mechanism for refresh
  Timer? _refreshDebounceTimer;
  DateTime? _lastRefreshTime;
  static const Duration _refreshCooldown = Duration(seconds: 30);

  // Debounced persistence for sort order and indent level
  final Map<String, int> _pendingSortUpdates = {};
  final Map<String, int> _pendingIndentUpdates = {};
  Timer? _sortDebounce;
  Timer? _indentDebounce;

  // Multi-selection state
  bool _isSelectionMode = false;
  Set<String> _selectedItems = {};

  // Search state — lexical client-side filter over already-loaded items.
  // Backend vector search will replace the filter implementation behind
  // the same getters in a follow-up PR.
  String _searchQuery = '';

  // Getters
  List<ActionItemWithMetadata> get actionItems => _actionItems;
  bool get isLoading => _isLoading;
  bool get isFetching => _isFetching;
  bool get hasMore => _hasMore;
  bool get includeCompleted => _includeCompleted;
  bool get showCompletedView => _showCompletedView;
  DateTime? get startDate => _startDate;
  DateTime? get endDate => _endDate;
  bool get hasActiveFilter => _startDate != null || _endDate != null;

  // Selection getters
  bool get isSelectionMode => _isSelectionMode;
  Set<String> get selectedItems => _selectedItems;
  int get selectedCount => _selectedItems.length;
  bool get hasSelection => _selectedItems.isNotEmpty;

  // Search getters
  String get searchQuery => _searchQuery;
  bool get isSearching => _searchQuery.isNotEmpty;

  /// Items matching the active search query, or all items when no query is set.
  /// Lexical case-insensitive substring match on description.
  List<ActionItemWithMetadata> get filteredActionItems {
    if (_searchQuery.isEmpty) return _actionItems;
    final q = _searchQuery.toLowerCase();
    return _actionItems.where((i) => i.description.toLowerCase().contains(q)).toList();
  }

  // Group action items by completion status
  List<ActionItemWithMetadata> get incompleteItems => _actionItems.where((item) => item.completed == false).toList();

  List<ActionItemWithMetadata> get completedItems => _actionItems.where((item) => item.completed == true).toList();

  // New categorization with 3-day cutoff for tabs
  List<ActionItemWithMetadata> get todoItems {
    final now = DateTime.now();
    final threeDaysAgo = now.subtract(const Duration(days: 3));

    return _actionItems.where((item) {
      if (item.completed) return false;

      // Check if within 3 days based on due_at or created_at
      if (item.dueAt != null) {
        return item.dueAt!.isAfter(threeDaysAgo) || item.dueAt!.isAtSameMomentAs(threeDaysAgo);
      } else if (item.createdAt != null) {
        return item.createdAt!.isAfter(threeDaysAgo) || item.createdAt!.isAtSameMomentAs(threeDaysAgo);
      }

      // If no dates, include in To Do by default
      return true;
    }).toList();
  }

  List<ActionItemWithMetadata> get doneItems {
    return _actionItems.where((item) => item.completed == true).toList();
  }

  List<ActionItemWithMetadata> get snoozedItems {
    final now = DateTime.now();
    final threeDaysAgo = now.subtract(const Duration(days: 3));

    return _actionItems.where((item) {
      if (item.completed) return false;

      // Check if past 3 days based on due_at or created_at
      if (item.dueAt != null) {
        return item.dueAt!.isBefore(threeDaysAgo);
      } else if (item.createdAt != null) {
        return item.createdAt!.isBefore(threeDaysAgo);
      }

      // If no dates, don't include in snoozed
      return false;
    }).toList();
  }

  ActionItemsProvider() {
    _preload();
  }

  void _preload() async {
    await fetchActionItems();
    _migrateCategoryOrderFromPrefs();
  }

  /// One-time migration: convert SharedPreferences taskCategoryOrder to sort_order on items
  Future<void> _migrateCategoryOrderFromPrefs() async {
    final savedOrder = SharedPreferencesUtil().taskCategoryOrder;
    if (savedOrder.isEmpty) return;

    final Map<String, int> sortUpdates = {};
    for (final entry in savedOrder.entries) {
      final ids = entry.value;
      for (int i = 0; i < ids.length; i++) {
        sortUpdates[ids[i]] = (i + 1) * 1000;
      }
    }

    if (sortUpdates.isNotEmpty) {
      batchUpdateSortOrders(sortUpdates);
      // Clear old prefs after migration
      SharedPreferencesUtil().taskCategoryOrder = {};
    }
  }

  void setLoading(bool value) {
    _isLoading = value;
    notifyListeners();
  }

  void setFetching(bool value) {
    _isFetching = value;
    notifyListeners();
  }

  Future<void> fetchActionItems({bool showShimmer = false}) async {
    if (showShimmer) {
      setLoading(true);
    } else {
      setFetching(true);
    }

    try {
      final response = await api.getActionItems(
        limit: 100,
        offset: 0,
        completed: _includeCompleted ? null : false,
        startDate: _startDate,
        endDate: _endDate,
      );

      _actionItems = response.actionItems;
      _hasMore = response.hasMore;
    } catch (e) {
      Logger.debug('Error fetching action items: $e');
    } finally {
      if (showShimmer) {
        setLoading(false);
      } else {
        setFetching(false);
      }
    }

    notifyListeners();
  }

  Future<void> loadMoreActionItems() async {
    if (_isFetching || !_hasMore) return;

    setFetching(true);

    try {
      final response = await api.getActionItems(
        limit: 50,
        offset: _actionItems.length,
        completed: _includeCompleted ? null : false,
        startDate: _startDate,
        endDate: _endDate,
      );

      _actionItems.addAll(response.actionItems);
      _hasMore = response.hasMore;
    } catch (e) {
      Logger.debug('Error loading more action items: $e');
    } finally {
      setFetching(false);
    }

    notifyListeners();
  }

  Future<void> updateActionItemState(ActionItemWithMetadata item, bool newState) async {
    try {
      final itemInList = _findAndUpdateItemState(item.id, newState);
      if (itemInList != null) {
        notifyListeners();
      }

      final success = await api.updateActionItem(
        item.id,
        description: item.description,
        completed: newState,
        dueAt: item.dueAt,
      );

      if (success == null) {
        _findAndUpdateItemState(item.id, !newState);
        notifyListeners();
        Logger.debug('Failed to update action item state on server');
      } else {
        // Cancel notification if the action item is marked as completed
        if (newState == true) {
          await ActionItemNotificationHandler.cancelNotification(item.id);
        }
        _pushUpdateToAppleReminder(item, completed: newState);
      }
    } catch (e) {
      _findAndUpdateItemState(item.id, !newState);
      notifyListeners();
      Logger.debug('Error updating action item state: $e');
    }
  }

  Future<void> updateActionItemDescription(ActionItemWithMetadata item, String newDescription) async {
    try {
      final itemInList = _findAndUpdateItemDescription(item.id, newDescription);
      if (itemInList != null) {
        notifyListeners();
      }

      final updatedItem = await api.updateActionItem(item.id, description: newDescription);

      if (updatedItem != null) {
        // Update the local item with server response
        final index = _actionItems.indexWhere((i) => i.id == item.id);
        if (index != -1) {
          _actionItems[index] = updatedItem;
          notifyListeners();
        }
        _pushUpdateToAppleReminder(item, title: newDescription);
      } else {
        // Revert on failure
        _findAndUpdateItemDescription(item.id, item.description);
        notifyListeners();
        Logger.debug('Failed to update action item description on server');
      }
    } catch (e) {
      _findAndUpdateItemDescription(item.id, item.description);
      notifyListeners();
      Logger.debug('Error updating action item description: $e');
    }
  }

  Future<void> updateActionItemDueDate(ActionItemWithMetadata item, DateTime? dueDate) async {
    // Optimistic update: update locally first for instant UI feedback
    final index = _actionItems.indexWhere((i) => i.id == item.id);
    ActionItemWithMetadata? originalItem;
    if (index != -1) {
      originalItem = _actionItems[index];
      _actionItems[index] = ActionItemWithMetadata(
        id: originalItem.id,
        description: originalItem.description,
        completed: originalItem.completed,
        createdAt: originalItem.createdAt,
        updatedAt: originalItem.updatedAt,
        dueAt: dueDate,
        completedAt: originalItem.completedAt,
        conversationId: originalItem.conversationId,
        isLocked: originalItem.isLocked,
        exported: originalItem.exported,
        exportDate: originalItem.exportDate,
        exportPlatform: originalItem.exportPlatform,
        sortOrder: originalItem.sortOrder,
        indentLevel: originalItem.indentLevel,
      );
      notifyListeners();
    }

    try {
      final updatedItem = await api.updateActionItem(item.id, dueAt: dueDate, clearDueAt: dueDate == null);

      if (updatedItem != null) {
        final idx = _actionItems.indexWhere((i) => i.id == item.id);
        if (idx != -1) {
          _actionItems[idx] = updatedItem;
          notifyListeners();
        }
        _pushUpdateToAppleReminder(item, dueDate: dueDate);
      } else {
        // Revert on failure
        if (index != -1 && originalItem != null) {
          _actionItems[index] = originalItem;
          notifyListeners();
        }
        Logger.debug('Failed to update action item due date on server');
      }
    } catch (e) {
      // Revert on error
      if (index != -1 && originalItem != null) {
        _actionItems[index] = originalItem;
        notifyListeners();
      }
      Logger.debug('Error updating action item due date: $e');
    }
  }

  Future<int> clearTodayDeadlinesForIncompleteTasks() async {
    final now = DateTime.now();
    final startOfTomorrow = DateTime(now.year, now.month, now.day + 1);

    final itemsToClear = _actionItems.where((item) {
      final dueAt = item.dueAt;
      if (item.completed || dueAt == null) return false;
      // Keep clean behavior aligned with the tasks listed under "Today" in UI.
      return dueAt.isBefore(startOfTomorrow);
    }).toList();

    if (itemsToClear.isEmpty) return 0;

    final originalItemsById = <String, ActionItemWithMetadata>{};
    for (final item in itemsToClear) {
      final index = _actionItems.indexWhere((i) => i.id == item.id);
      if (index != -1) {
        originalItemsById[item.id] = _actionItems[index];
        _actionItems[index] = _actionItems[index].copyWith(dueAt: null);
      }
    }
    notifyListeners();

    int successCount = 0;
    for (final item in itemsToClear) {
      try {
        final updatedItem = await api.updateActionItem(item.id, clearDueAt: true);

        final index = _actionItems.indexWhere((i) => i.id == item.id);
        if (updatedItem != null) {
          if (index != -1) {
            _actionItems[index] = updatedItem;
          }
          successCount++;
        } else if (index != -1) {
          final originalItem = originalItemsById[item.id];
          if (originalItem != null) {
            _actionItems[index] = originalItem;
          }
        }
      } catch (e) {
        final index = _actionItems.indexWhere((i) => i.id == item.id);
        if (index != -1) {
          final originalItem = originalItemsById[item.id];
          if (originalItem != null) {
            _actionItems[index] = originalItem;
          }
        }
        Logger.debug('Error clearing today deadline for item ${item.id}: $e');
      }
    }

    notifyListeners();
    return successCount;
  }

  Future<bool> deleteActionItem(ActionItemWithMetadata item) async {
    // Delete linked Apple Reminder if one exists
    _deleteAppleReminderIfLinked(item);

    // Remove immediately to prevent dismissed Dismissible from being rebuilt
    _actionItems.removeWhere((actionItem) => actionItem.id == item.id);
    notifyListeners();

    try {
      final success = await api.deleteActionItem(item.id);

      if (!success) {
        Logger.debug('Failed to delete action item on server');
      }
      return success;
    } catch (e) {
      Logger.debug('Error deleting action item: $e');
      return false;
    }
  }

  Future<ActionItemWithMetadata?> createActionItem({
    required String description,
    DateTime? dueAt,
    String? conversationId,
    bool completed = false,
  }) async {
    final optimisticItem = ActionItemWithMetadata(
      id: 'temp_${DateTime.now().millisecondsSinceEpoch}',
      description: description,
      completed: completed,
      dueAt: dueAt,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      conversationId: conversationId,
    );

    _actionItems.insert(0, optimisticItem);
    notifyListeners();

    try {
      final newItem = await api.createActionItem(
        description: description,
        dueAt: dueAt,
        conversationId: conversationId,
        completed: completed,
      );

      if (newItem != null) {
        final index = _actionItems.indexWhere((item) => item.id == optimisticItem.id);
        if (index != -1) {
          _actionItems[index] = newItem;
          notifyListeners();
        }
        // Direct sync to Apple Reminders — no FCM roundtrip needed
        _syncToAppleRemindersIfNeeded(newItem);
        return newItem;
      } else {
        _actionItems.removeWhere((item) => item.id == optimisticItem.id);
        notifyListeners();
        Logger.debug('Failed to create action item on server');
        return null;
      }
    } catch (e) {
      _actionItems.removeWhere((item) => item.id == optimisticItem.id);
      notifyListeners();
      Logger.debug('Error creating action item: $e');
      return null;
    }
  }

  /// Directly create an Apple Reminder without waiting for FCM roundtrip.
  /// Fire-and-forget — doesn't block the UI.
  void _syncToAppleRemindersIfNeeded(ActionItemWithMetadata item) {
    if (!PlatformService.isApple) return;

    final service = AppleRemindersService();
    if (!service.isAvailable) return;

    () async {
      try {
        if (!await service.hasPermission()) return;

        final calendarItemId = await service.addReminder(
          title: item.description,
          notes: 'From Omi',
          dueDate: item.dueAt,
          listName: 'Reminders',
        );

        if (calendarItemId != null) {
          await api.updateActionItem(
            item.id,
            exported: true,
            exportPlatform: 'apple_reminders',
            appleReminderId: calendarItemId,
          );
          MixpanelManager().appleReminderDirectSync(actionItemId: item.id);
        }
      } catch (e) {
        Logger.debug('Direct Apple Reminders sync failed: $e');
      }
    }();
  }

  /// Push a field update to the linked Apple Reminder immediately.
  void _pushUpdateToAppleReminder(ActionItemWithMetadata item, {bool? completed, String? title, DateTime? dueDate}) {
    if (!PlatformService.isApple) return;
    if (item.appleReminderId == null || item.appleReminderId!.isEmpty) return;

    AppleRemindersService().updateReminderById(
      item.appleReminderId!,
      completed: completed,
      title: title,
      dueDate: dueDate,
    );
  }

  /// Delete the linked Apple Reminder when action item is deleted.
  void _deleteAppleReminderIfLinked(ActionItemWithMetadata item) {
    if (!PlatformService.isApple) return;
    if (item.appleReminderId == null || item.appleReminderId!.isEmpty) return;

    AppleRemindersService().deleteReminderById(item.appleReminderId!);
    MixpanelManager().appleReminderDeleted(actionItemId: item.id);
  }

  // Sort order and indent level persistence

  void _updateItemInPlace(String id, {int? sortOrder, int? indentLevel}) {
    final index = _actionItems.indexWhere((item) => item.id == id);
    if (index != -1) {
      _actionItems[index] = _actionItems[index].copyWith(sortOrder: sortOrder, indentLevel: indentLevel);
    }
  }

  void updateItemSortOrder(String id, int sortOrder) {
    _updateItemInPlace(id, sortOrder: sortOrder);
    _pendingSortUpdates[id] = sortOrder;
    notifyListeners();
    _sortDebounce?.cancel();
    _sortDebounce = Timer(const Duration(milliseconds: 500), _flushSortUpdates);
  }

  void updateItemIndentLevel(String id, int indentLevel) {
    _updateItemInPlace(id, indentLevel: indentLevel);
    _pendingIndentUpdates[id] = indentLevel;
    notifyListeners();
    _indentDebounce?.cancel();
    _indentDebounce = Timer(const Duration(milliseconds: 500), _flushIndentUpdates);
  }

  void batchUpdateSortOrders(Map<String, int> updates) {
    for (final entry in updates.entries) {
      _updateItemInPlace(entry.key, sortOrder: entry.value);
      _pendingSortUpdates[entry.key] = entry.value;
    }
    notifyListeners();
    _sortDebounce?.cancel();
    _sortDebounce = Timer(const Duration(milliseconds: 500), _flushSortUpdates);
  }

  Future<void> _flushSortUpdates() async {
    if (_pendingSortUpdates.isEmpty) return;
    final updates = Map<String, int>.from(_pendingSortUpdates);
    _pendingSortUpdates.clear();

    final items = updates.entries.map((e) => {'id': e.key, 'sort_order': e.value}).toList();
    await api.batchUpdateActionItems(items);
  }

  Future<void> _flushIndentUpdates() async {
    if (_pendingIndentUpdates.isEmpty) return;
    final updates = Map<String, int>.from(_pendingIndentUpdates);
    _pendingIndentUpdates.clear();

    final items = updates.entries.map((e) => {'id': e.key, 'indent_level': e.value}).toList();
    await api.batchUpdateActionItems(items);
  }

  ActionItemWithMetadata? _findAndUpdateItemState(String itemId, bool newState) {
    final mainIndex = _actionItems.indexWhere((item) => item.id == itemId);
    if (mainIndex != -1) {
      _actionItems[mainIndex] = _actionItems[mainIndex].copyWith(completed: newState);
      return _actionItems[mainIndex];
    }

    return null;
  }

  ActionItemWithMetadata? _findAndUpdateItemDescription(String itemId, String newDescription) {
    final mainIndex = _actionItems.indexWhere((item) => item.id == itemId);
    if (mainIndex != -1) {
      _actionItems[mainIndex] = _actionItems[mainIndex].copyWith(description: newDescription);
      return _actionItems[mainIndex];
    }

    return null;
  }

  void toggleCompletedActionItems() {
    _includeCompleted = !_includeCompleted;
    fetchActionItems(showShimmer: true);
    // TODO: Add analytics for completed action items toggle
  }

  void toggleShowCompletedView() {
    _showCompletedView = !_showCompletedView;
    notifyListeners();
  }

  void setDateRangeFilter(DateTime? startDate, DateTime? endDate) {
    _startDate = startDate;
    _endDate = endDate;
    fetchActionItems(showShimmer: true);
  }

  void clearDateRangeFilter() {
    _startDate = null;
    _endDate = null;
    fetchActionItems(showShimmer: true);
  }

  Future<void> refreshActionItems() async {
    final now = DateTime.now();
    if (_lastRefreshTime != null && now.difference(_lastRefreshTime!) < _refreshCooldown) {
      Logger.debug('Skipping action items refresh - too soon since last refresh');
      return;
    }

    _refreshDebounceTimer?.cancel();
    _refreshDebounceTimer = Timer(const Duration(milliseconds: 500), () {
      _lastRefreshTime = DateTime.now();
      _fetchNewActionItems();
    });
  }

  /// Force refresh bypassing debounce
  Future<void> forceRefreshActionItems() async {
    _refreshDebounceTimer?.cancel();
    _lastRefreshTime = DateTime.now();
    await _fetchNewActionItems();
  }

  Future<void> _fetchNewActionItems() async {
    await fetchActionItems();
  }

  // Selection methods
  void startSelection() {
    _isSelectionMode = true;
    _selectedItems.clear();
    notifyListeners();
  }

  void endSelection() {
    _isSelectionMode = false;
    _selectedItems.clear();
    notifyListeners();
  }

  void toggleItemSelection(String itemId) {
    if (_selectedItems.contains(itemId)) {
      _selectedItems.remove(itemId);
    } else {
      final item = _actionItems.where((i) => i.id == itemId).firstOrNull;
      if (item != null && item.exported) return;
      _selectedItems.add(itemId);
    }
    notifyListeners();
  }

  void selectItem(String itemId) {
    final item = _actionItems.where((i) => i.id == itemId).firstOrNull;
    if (item != null && item.exported) return;
    if (!_selectedItems.contains(itemId)) {
      _selectedItems.add(itemId);
      notifyListeners();
    }
  }

  void deselectItem(String itemId) {
    if (_selectedItems.contains(itemId)) {
      _selectedItems.remove(itemId);
      notifyListeners();
    }
  }

  void selectAllItems() {
    _selectedItems.clear();
    for (final item in _actionItems) {
      if (!item.exported) _selectedItems.add(item.id);
    }
    notifyListeners();
  }

  void selectAllItemsFromTab(int tabIndex) {
    _selectedItems.clear();
    List<ActionItemWithMetadata> itemsToSelect = [];

    switch (tabIndex) {
      case 0:
        itemsToSelect = todoItems;
        break;
      case 1:
        itemsToSelect = doneItems;
        break;
      case 2:
        itemsToSelect = snoozedItems;
        break;
    }

    for (final item in itemsToSelect) {
      if (!item.exported) _selectedItems.add(item.id);
    }
    notifyListeners();
  }

  void clearSelection() {
    _selectedItems.clear();
    notifyListeners();
  }

  void clearUserData() {
    _actionItems = [];
    _selectedItems = {};
    _pendingSortUpdates.clear();
    _pendingIndentUpdates.clear();
    notifyListeners();
  }

  bool isItemSelected(String itemId) {
    return _selectedItems.contains(itemId);
  }

  // Bulk operations
  Future<bool> deleteSelectedItems() async {
    if (_selectedItems.isEmpty) return false;

    final itemsToDelete = _actionItems.where((item) => _selectedItems.contains(item.id)).toList();

    // Dismiss UI immediately — don't wait for API
    _actionItems.removeWhere((item) => _selectedItems.contains(item.id));
    _selectedItems.clear();
    _isSelectionMode = false;
    notifyListeners();

    final results = await Future.wait(itemsToDelete.map((item) => deleteActionItem(item)));
    return results.every((success) => success);
  }

  Future<bool> clearCompletedItems() async {
    final completed = _actionItems.where((item) => item.completed).toList();
    if (completed.isEmpty) return true;

    final results = await Future.wait(completed.map((item) => deleteActionItem(item)));
    return results.every((success) => success);
  }

  void startSelectionWithItem(String itemId) {
    final item = _actionItems.where((i) => i.id == itemId).firstOrNull;
    if (item != null && item.exported) return;
    _isSelectionMode = true;
    _selectedItems = {itemId};
    notifyListeners();
  }

  // Search methods
  void setSearchQuery(String query) {
    final next = query.trim();
    if (next == _searchQuery) return;
    _searchQuery = next;
    notifyListeners();
  }

  void clearSearchQuery() {
    if (_searchQuery.isEmpty) return;
    _searchQuery = '';
    notifyListeners();
  }

  /// Fan-out export of every currently selected item to [platform].
  /// Snackbar feedback is posted via [context]; selection mode exits when done.
  Future<void> bulkExportSelected(BuildContext context, TaskIntegrationApp platform) async {
    if (_selectedItems.isEmpty) return;

    final ids = _selectedItems.toList(growable: false);
    final items = _actionItems.where((i) => ids.contains(i.id)).toList(growable: false);
    final total = items.length;

    final messenger = ScaffoldMessenger.of(context);
    messenger.clearSnackBars();
    messenger.showSnackBar(
      SnackBar(
        content: Text(context.l10n.bulkExportInProgress),
        duration: const Duration(seconds: 30),
        backgroundColor: Colors.blue,
      ),
    );

    final results = await Future.wait(items.map((i) => ActionItemExportService.export(i, platform)));
    final successCount = results.where((r) => r == ExportResult.success).length;

    // Refresh from server so newly-flipped `exported`/`exportPlatform` fields surface.
    await fetchActionItems();
    endSelection();

    if (!context.mounted) return;
    messenger.clearSnackBars();
    final message = successCount == total
        ? context.l10n.bulkExportSuccess(successCount, platform.displayName)
        : context.l10n.bulkExportPartial(successCount, total, platform.displayName);
    messenger.showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: successCount == total ? Colors.green : Colors.orange,
        duration: const Duration(seconds: 3),
      ),
    );
  }

  @override
  void dispose() {
    _refreshDebounceTimer?.cancel();
    _sortDebounce?.cancel();
    _indentDebounce?.cancel();
    _flushSortUpdates();
    _flushIndentUpdates();
    super.dispose();
  }
}
