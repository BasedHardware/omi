import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/action_items.dart' as api;
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/services/notifications/action_item_notification_handler.dart';

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

  // Multi-selection state
  bool _isSelectionMode = false;
  Set<String> _selectedItems = {};

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
      debugPrint('Error fetching action items: $e');
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
      debugPrint('Error loading more action items: $e');
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
        debugPrint('Failed to update action item state on server');
      } else {
        // Cancel notification if the action item is marked as completed
        if (newState == true) {
          await ActionItemNotificationHandler.cancelNotification(item.id);
        }
      }
    } catch (e) {
      _findAndUpdateItemState(item.id, !newState);
      notifyListeners();
      debugPrint('Error updating action item state: $e');
    }
  }

  Future<void> updateActionItemDescription(ActionItemWithMetadata item, String newDescription) async {
    try {
      final itemInList = _findAndUpdateItemDescription(item.id, newDescription);
      if (itemInList != null) {
        notifyListeners();
      }

      final updatedItem = await api.updateActionItem(
        item.id,
        description: newDescription,
      );

      if (updatedItem != null) {
        // Update the local item with server response
        final index = _actionItems.indexWhere((i) => i.id == item.id);
        if (index != -1) {
          _actionItems[index] = updatedItem;
          notifyListeners();
        }
      } else {
        // Revert on failure
        _findAndUpdateItemDescription(item.id, item.description);
        notifyListeners();
        debugPrint('Failed to update action item description on server');
      }
    } catch (e) {
      _findAndUpdateItemDescription(item.id, item.description);
      notifyListeners();
      debugPrint('Error updating action item description: $e');
    }
  }

  Future<void> updateActionItemDueDate(ActionItemWithMetadata item, DateTime? dueDate) async {
    try {
      final updatedItem = await api.updateActionItem(
        item.id,
        dueAt: dueDate,
        clearDueAt: dueDate == null, // Explicitly clear if null
      );

      if (updatedItem != null) {
        // Update the local item with server response
        final index = _actionItems.indexWhere((i) => i.id == item.id);
        if (index != -1) {
          _actionItems[index] = updatedItem;
          notifyListeners();
        }
      } else {
        debugPrint('Failed to update action item due date on server');
      }
    } catch (e) {
      debugPrint('Error updating action item due date: $e');
    }
  }

  Future<bool> deleteActionItem(ActionItemWithMetadata item) async {
    try {
      final success = await api.deleteActionItem(
        item.id,
      );

      if (success) {
        _actionItems.removeWhere((actionItem) => actionItem.id == item.id);
        notifyListeners();
        return true;
      } else {
        debugPrint('Failed to delete action item on server');
        return false;
      }
    } catch (e) {
      debugPrint('Error deleting action item: $e');
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
        return newItem;
      } else {
        _actionItems.removeWhere((item) => item.id == optimisticItem.id);
        notifyListeners();
        debugPrint('Failed to create action item on server');
        return null;
      }
    } catch (e) {
      _actionItems.removeWhere((item) => item.id == optimisticItem.id);
      notifyListeners();
      debugPrint('Error creating action item: $e');
      return null;
    }
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
      debugPrint('Skipping action items refresh - too soon since last refresh');
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
      _selectedItems.add(itemId);
    }
    notifyListeners();
  }

  void selectItem(String itemId) {
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
      _selectedItems.add(item.id);
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
      _selectedItems.add(item.id);
    }
    notifyListeners();
  }

  void clearSelection() {
    _selectedItems.clear();
    notifyListeners();
  }

  bool isItemSelected(String itemId) {
    return _selectedItems.contains(itemId);
  }

  // Bulk operations
  Future<bool> deleteSelectedItems() async {
    if (_selectedItems.isEmpty) return false;

    final itemsToDelete = _actionItems.where((item) => _selectedItems.contains(item.id)).toList();
    final success = await Future.wait(itemsToDelete.map((item) => deleteActionItem(item)))
        .then((results) => results.every((success) => success));

    if (success) {
      _selectedItems.clear();
      _isSelectionMode = false;
    }

    return success;
  }

  @override
  void dispose() {
    _refreshDebounceTimer?.cancel();
    super.dispose();
  }
}
