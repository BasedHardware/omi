import 'dart:async';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

class MemoriesProvider extends ChangeNotifier {
  List<Memory> _memories = [];
  bool _loading = true;
  String _searchQuery = '';
  MemoryCategory? _categoryFilter;
  bool _excludeInteresting = false;
  List<Tuple2<MemoryCategory, int>> categories = [];
  MemoryCategory? selectedCategory;

  List<Memory> get memories => _memories;
  bool get loading => _loading;
  String get searchQuery => _searchQuery;
  MemoryCategory? get categoryFilter => _categoryFilter;
  bool get excludeInteresting => _excludeInteresting;

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
      } else if (_categoryFilter != null) {
        // Show only selected category
        categoryMatch = memory.category == _categoryFilter;
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

  void setCategoryFilter(MemoryCategory? category) async {
    _categoryFilter = category;
    _excludeInteresting = false; // Reset exclude filter when setting a category filter
    notifyListeners();

    final prefs = await SharedPreferences.getInstance();
    if (category == null) {
      await prefs.setString('memories_filter', 'all');
    } else {
      await prefs.setString('memories_filter', category.name);
    }
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
  }

  Future<void> _loadFilter() async {
    final prefs = await SharedPreferences.getInstance();
    final filter = prefs.getString('memories_filter');
    if (filter != null) {
      if (filter == 'all') {
        _categoryFilter = null;
      } else {
        try {
          _categoryFilter = MemoryCategory.values.firstWhere((e) => e.name == filter);
        } catch (_) {
          _categoryFilter = null;
        }
      }
    }
  }

  Future<void> loadMemories() async {
    _loading = true;
    notifyListeners();

    _memories = await getMemories();

    _loading = false;
    _setCategories();
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
    _deletionTimer = Timer(const Duration(seconds: 10), () {
      _executeServerDeletion();
    });
  }

  Future<void> _executeServerDeletion() async {
    if (_pendingDeletionId != null) {
      await deleteMemoryServer(_pendingDeletionId!);
      _pendingDeletionId = null;
    }
  }

  // Restore the last deleted memory
  Future<bool> restoreLastDeletedMemory() async {
    if (_lastDeletedMemory == null) return false;

    _cancelDeletionTimer();
    _pendingDeletionId = null;

    _memories.add(_lastDeletedMemory!);

    _setCategories();
    notifyListeners();

    final restoredMemory = _lastDeletedMemory;
    _lastDeletedMemory = null;

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

  Future<bool> createMemory(String content,
      [MemoryVisibility visibility = MemoryVisibility.public,
      MemoryCategory category = MemoryCategory.interesting]) async {
    final success = await createMemoryServer(content, visibility.name, category.name);

    if (success) {
      final newMemory = Memory(
        id: const Uuid().v4(),
        uid: SharedPreferencesUtil().uid,
        content: content,
        category: category,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        conversationId: null,
        reviewed: true,
        manuallyAdded: true,
        visibility: visibility,
      );
      _memories.add(newMemory);
      _setCategories();
    }

    return success;
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
