import 'dart:async';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

class MemoriesProvider extends ChangeNotifier {
  List<Memory> _memories = [];
  bool _loading = true;
  String _searchQuery = '';
  Set<MemoryCategory> _selectedCategories = {};
  bool _excludeInteresting = false;
  List<Tuple2<MemoryCategory, int>> categories = [];
  MemoryCategory? selectedCategory;
  
  // Connectivity handling for offline sync
  ConnectivityProvider? _connectivityProvider;
  bool _isSyncing = false;

  List<Memory> get memories => _memories;
  bool get loading => _loading;
  String get searchQuery => _searchQuery;
  Set<MemoryCategory> get selectedCategories => _selectedCategories;
  bool get excludeInteresting => _excludeInteresting;
  bool get hasPendingMemories => SharedPreferencesUtil().pendingMemories.isNotEmpty;
  int get pendingMemoriesCount => SharedPreferencesUtil().pendingMemories.length;

  List<Memory> get filteredMemories {
    return _memories.where((memory) {
      // Apply search filter
      final matchesSearch =
          _searchQuery.isEmpty || memory.content.decodeString.toLowerCase().contains(_searchQuery.toLowerCase());

      // Apply category filter or exclusion logic
      bool categoryMatch;
      if (_excludeInteresting) {
        // Show all categories except interesting
        categoryMatch = memory.category != MemoryCategory.interesting;
      } else if (_selectedCategories.isNotEmpty) {
        // Show only selected categories
        categoryMatch = _selectedCategories.contains(memory.category);
      } else {
        // Show all categories if no filter is applied
        categoryMatch = true;
      }

      return matchesSearch && categoryMatch;
    }).toList()
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
  }

  void setExcludeInteresting(bool exclude) {
    _excludeInteresting = exclude;
    notifyListeners();
  }

  void setCategory(MemoryCategory? category) {
    selectedCategory = category;
    notifyListeners();
  }

  void setSearchQuery(String query) {
    _searchQuery = query.toLowerCase();
    notifyListeners();
  }

  void toggleCategoryFilter(MemoryCategory category) async {
    if (_selectedCategories.contains(category)) {
      _selectedCategories.remove(category);
    } else {
      _selectedCategories.add(category);
    }
    _excludeInteresting = false; // Reset exclude filter when setting a category filter
    notifyListeners();

    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList('memories_filter_categories', _selectedCategories.map((e) => e.name).toList());
  }

  void clearCategoryFilter() async {
    _selectedCategories.clear();
    _excludeInteresting = false;
    notifyListeners();

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('memories_filter_categories');
    // Clear old single filter key as well to be clean
    await prefs.remove('memories_filter');
  }

  // Deprecated/Modified: kept as alias if needed but unused internally now
  void setCategoryFilter(MemoryCategory? category) {
      // Do nothing or migrate logic if called from legacy code?
      // Assuming we are updating all call sites.
  }

  void _setCategories() {
    categories = MemoryCategory.values.map((category) {
      final count = memories.where((memory) => memory.category == category).length;
      return Tuple2(category, count);
    }).toList();
    notifyListeners();
  }

  Future<void> init() async {
    await _loadFilter();
    await loadMemories();
    // Try to sync any pending memories on init
    await syncPendingMemories();
  }

  /// Set the connectivity provider to listen for connection changes
  void setConnectivityProvider(ConnectivityProvider provider) {
    _connectivityProvider = provider;
    _connectivityProvider?.addListener(_onConnectivityChanged);
  }

  void _onConnectivityChanged() {
    if (_connectivityProvider?.isConnected == true) {
      // Connection restored, try to sync pending memories
      syncPendingMemories();
    }
  }

  @override
  void dispose() {
    _connectivityProvider?.removeListener(_onConnectivityChanged);
    super.dispose();
  }

  Future<void> _loadFilter() async {
    final prefs = await SharedPreferences.getInstance();
    
    final filterList = prefs.getStringList('memories_filter_categories');
    
    if (filterList == null) {
      _selectedCategories = {MemoryCategory.interesting, MemoryCategory.manual};
    } else {
      _selectedCategories = filterList
          .map((e) => MemoryCategory.values.firstWhere(
                (c) => c.name == e,
                orElse: () => MemoryCategory.interesting,
              ))
          .toSet();
    }
    notifyListeners();
  }

  Future<void> loadMemories({int limit = 100}) async {
    _loading = true;
    notifyListeners();

    _memories = await getMemories(limit: limit);

    // Merge pending memories that haven't synced yet
    final pendingMemories = SharedPreferencesUtil().pendingMemories;
    for (var pending in pendingMemories) {
      if (!_memories.any((m) => m.id == pending.id)) {
        _memories.add(pending);
      }
    }

    _loading = false;
    _setCategories();
  }

  /// Sync pending memories to server when online
  Future<void> syncPendingMemories() async {
    if (_isSyncing) return;
    
    final pendingMemories = SharedPreferencesUtil().pendingMemories;
    if (pendingMemories.isEmpty) return;

    _isSyncing = true;
    debugPrint('MemoriesProvider: Syncing ${pendingMemories.length} pending memories...');

    for (var memory in List.from(pendingMemories)) {
      try {
        final serverMemory = await createMemoryServer(
          memory.content,
          memory.visibility.name,
          memory.category.name,
        );
        
        if (serverMemory != null) {
          SharedPreferencesUtil().removePendingMemory(memory.id);
          final idx = _memories.indexWhere((m) => m.id == memory.id);
          if (idx != -1) {
            _memories[idx].id = serverMemory.id;
          }
        }
      } catch (e) {
        debugPrint('MemoriesProvider: Failed to sync memory ${memory.id}: $e');
        // Keep in pending list for next sync attempt
      }
    }

    _isSyncing = false;
    notifyListeners();
  }

  Memory? _lastDeletedMemory;
  Timer? _deletionTimer;
  String? _pendingDeletionId;

  Memory? get lastDeletedMemory => _lastDeletedMemory;

  void deleteMemory(Memory memory) {
    _cancelDeletionTimer();

    _lastDeletedMemory = memory;
    _pendingDeletionId = memory.id;

    _memories.remove(memory);
    _setCategories();
    notifyListeners();

    _startDeletionTimer();
  }

  void _cancelDeletionTimer() {
    if (_deletionTimer != null && _deletionTimer!.isActive) {
      _deletionTimer!.cancel();
      _deletionTimer = null;
    }
  }

  void _startDeletionTimer() {
    _deletionTimer = Timer(const Duration(seconds: 4), () async {
      await _finalizeDeletion();
    });
  }

  Future<void> _finalizeDeletion() async {
    if (_pendingDeletionId == null) {
      _lastDeletedMemory = null;
      return;
    }

    final id = _pendingDeletionId!;

    // If memory was created offline and not yet synced
    if (SharedPreferencesUtil().pendingMemories.any((m) => m.id == id)) {
      SharedPreferencesUtil().removePendingMemory(id);
    } else {
      // Memory exists on server
      await deleteMemoryServer(id);
    }

    _pendingDeletionId = null;
    _lastDeletedMemory = null;
  }

  Future<void> confirmPendingDeletion() async {
    _cancelDeletionTimer();
    await _finalizeDeletion();
  }

  // Restore the last deleted memory
  Future<bool> restoreLastDeletedMemory() async {
    if (_lastDeletedMemory == null) return false;

    _cancelDeletionTimer();
    _pendingDeletionId = null;

    _memories.add(_lastDeletedMemory!);
    _lastDeletedMemory = null;

    _setCategories();
    notifyListeners();

    return true;
  }

  void deleteAllMemories() async {
    final int countBeforeDeletion = _memories.length;
    await deleteAllMemoriesServer();
    _memories.clear();
    if (countBeforeDeletion > 0) {
      MixpanelManager().memoriesAllDeleted(countBeforeDeletion);
    }
    _setCategories();
  }

  Future<void> reviewMemory(Memory memory, bool approve, String source) async {
    await reviewMemoryServer(memory.id, approve);
    
    if (!approve) {
      _memories.remove(memory);
    } else {
      final idx = _memories.indexWhere((m) => m.id == memory.id);
      if (idx != -1) {
        _memories[idx].reviewed = true;
      }
    }
    
    _setCategories();
    notifyListeners();
  }

  /// Create a memory - works offline by saving locally first, then syncing
  Future<bool> createMemory(String content,
      [MemoryVisibility visibility = MemoryVisibility.public,
      MemoryCategory category = MemoryCategory.interesting]) async {
    // Create the memory object first
    final newMemory = Memory(
      id: const Uuid().v4(),
      uid: SharedPreferencesUtil().uid,
      content: content,
      category: category,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      conversationId: null,
      reviewed: false,
      manuallyAdded: true,
      visibility: visibility,
    );

    // Add to local list immediately (optimistic update)
    _memories.add(newMemory);
    _setCategories();
    notifyListeners();

    // Save to pending memories for persistence across app restarts
    SharedPreferencesUtil().addPendingMemory(newMemory);

    // Try to sync to server immediately
    final serverMemory = await createMemoryServer(
      content,
      visibility.name,
      category.name,
    );

    if (serverMemory != null) {
      // Remove from pending and update local memory with server ID
      SharedPreferencesUtil().removePendingMemory(newMemory.id);
      final idx = _memories.indexWhere((m) => m.id == newMemory.id);
      if (idx != -1) {
        _memories[idx].id = serverMemory.id;
      }
    }

    // Return true since memory is saved locally regardless of server sync
    return true;
  }

  Future<void> updateMemoryVisibility(Memory memory, MemoryVisibility visibility) async {
    await updateMemoryVisibilityServer(memory.id, visibility.name);

    final idx = _memories.indexWhere((m) => m.id == memory.id);
    if (idx != -1) {
      Memory memoryToUpdate = _memories[idx];
      memoryToUpdate.visibility = visibility;
      _memories[idx] = memoryToUpdate;

      MixpanelManager().memoryVisibilityChanged(memoryToUpdate, visibility);
      _setCategories();
    }
  }

  Future<bool> editMemory(Memory memory, String value, [MemoryCategory? category]) async {
    final success = await editMemoryServer(memory.id, value);

    if (success) {
      final idx = _memories.indexWhere((m) => m.id == memory.id);
      if (idx != -1) {
        memory.content = value;
        if (category != null) {
          memory.category = category;
        }
        memory.updatedAt = DateTime.now();
        memory.edited = true;
        _memories[idx] = memory;

        _setCategories();
      }
    }

    return success;
  }

  Future<void> updateAllMemoriesVisibility(bool makePrivate) async {
    final visibility = makePrivate ? MemoryVisibility.private : MemoryVisibility.public;
    int updatedCount = 0;
    List<Memory> memoriesSuccessfullyUpdated = [];

    for (var memory in List.from(_memories)) {
      if (memory.visibility != visibility) {
        try {
          await updateMemoryVisibilityServer(memory.id, visibility.name);
          final idx = _memories.indexWhere((m) => m.id == memory.id);
          if (idx != -1) {
            _memories[idx].visibility = visibility;
            memoriesSuccessfullyUpdated.add(_memories[idx]);
            updatedCount++;
          }
        } catch (e) {
          print('Failed to update visibility for memory ${memory.id}: $e');
        }
      }
    }

    if (updatedCount > 0) {
      MixpanelManager().memoriesAllVisibilityChanged(visibility, updatedCount);
    }

    _setCategories();
  }
}
