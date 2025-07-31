import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/conversations.dart' as api;
import 'package:omi/backend/schema/schema.dart';

class ActionItemsProvider extends ChangeNotifier {
  List<ActionItemWithMetadata> _actionItems = [];
  
  bool _isLoading = false;
  bool _isFetching = false;
  bool _hasMore = false;
  int _totalCount = 0;
  
  bool _includeCompleted = true;
  
  DateTime? _selectedStartDate;
  DateTime? _selectedEndDate;
  
  // Debounce mechanism for refresh
  Timer? _refreshDebounceTimer;
  DateTime? _lastRefreshTime;
  static const Duration _refreshCooldown = Duration(seconds: 30);

  // Getters
  List<ActionItemWithMetadata> get actionItems => _actionItems;
  bool get isLoading => _isLoading;
  bool get isFetching => _isFetching;
  bool get hasMore => _hasMore;
  int get totalCount => _totalCount;
  bool get includeCompleted => _includeCompleted;
  DateTime? get selectedStartDate => _selectedStartDate;
  DateTime? get selectedEndDate => _selectedEndDate;

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
        includeCompleted: _includeCompleted,
        startDate: _selectedStartDate,
        endDate: _selectedEndDate,
      );

      _actionItems = response.actionItems;
      _hasMore = response.hasMore;
      _totalCount = response.totalCount;
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
        includeCompleted: _includeCompleted,
        startDate: _selectedStartDate,
        endDate: _selectedEndDate,
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

      final success = await api.updateActionItemStateByMetadata(
        item.conversationId,
        item.index,
        newState,
      );

      if (!success) {
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
    final itemInList = _findAndUpdateItemDescription(item.id, newDescription);
    if (itemInList != null) {
      notifyListeners();
    }
  }

  Future<bool> deleteActionItem(ActionItemWithMetadata item) async {
    try {
      final success = await api.deleteConversationActionItem(
        item.conversationId,
        ActionItem(
          item.description,
          completed: item.completed,
          deleted: false,
        ),
      );

      if (success) {
        _actionItems.removeWhere((actionItem) => actionItem.id == item.id);
        _totalCount = _totalCount > 0 ? _totalCount - 1 : 0;
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

  Future<void> setDateFilter(DateTime? startDate, DateTime? endDate) async {
    _selectedStartDate = startDate;
    _selectedEndDate = endDate;
    
    await fetchActionItems(showShimmer: true);
  }

  Future<void> clearDateFilter() async {
    _selectedStartDate = null;
    _selectedEndDate = null;
    
    await fetchActionItems(showShimmer: true);
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