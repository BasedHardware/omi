import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/action_items.dart' as api;
import 'package:omi/backend/schema/schema.dart';

class ActionItemsProvider extends ChangeNotifier {
  List<ActionItemWithMetadata> _actionItems = [];
  
  bool _isLoading = false;
  bool _isFetching = false;
  bool _hasMore = false;
  
  bool _includeCompleted = true;
  

  
  // Debounce mechanism for refresh
  Timer? _refreshDebounceTimer;
  DateTime? _lastRefreshTime;
  static const Duration _refreshCooldown = Duration(seconds: 30);

  // Getters
  List<ActionItemWithMetadata> get actionItems => _actionItems;
  bool get isLoading => _isLoading;
  bool get isFetching => _isFetching;
  bool get hasMore => _hasMore;
  bool get includeCompleted => _includeCompleted;


  // Group action items by completion status
  List<ActionItemWithMetadata> get incompleteItems => 
      _actionItems.where((item) => item.completed == false).toList();
  
  List<ActionItemWithMetadata> get completedItems => 
      _actionItems.where((item) => item.completed == true).toList();

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

  @override
  void dispose() {
    _refreshDebounceTimer?.cancel();
    super.dispose();
  }
} 

