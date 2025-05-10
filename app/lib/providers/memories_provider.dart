import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

class MemoriesProvider extends ChangeNotifier {
  List<Memory> _memories = [];
  List<Memory> _unreviewed = [];
  bool _loading = true;
  String _searchQuery = '';
  MemoryCategory? _categoryFilter;
  List<Tuple2<MemoryCategory, int>> categories = [];
  MemoryCategory? selectedCategory;

  List<Memory> get memories => _memories;
  List<Memory> get unreviewed => _unreviewed;
  bool get loading => _loading;
  String get searchQuery => _searchQuery;
  MemoryCategory? get categoryFilter => _categoryFilter;

  List<Memory> get filteredMemories {
    return _memories.where((memory) {
      // Apply search filter
      final matchesSearch = _searchQuery.isEmpty ||
        memory.content.decodeString.toLowerCase().contains(_searchQuery.toLowerCase());

      // Apply category filter
      final matchesCategory = _categoryFilter == null ||
        memory.category == _categoryFilter;

      return matchesSearch && matchesCategory;
    }).toList()..sort((a, b) => b.createdAt.compareTo(a.createdAt));
  }

  void setCategory(MemoryCategory? category) {
    selectedCategory = category;
    notifyListeners();
  }

  void setSearchQuery(String query) {
    _searchQuery = query.toLowerCase();
    notifyListeners();
  }

  void setCategoryFilter(MemoryCategory? category) {
    _categoryFilter = category;
    notifyListeners();
  }

  void _setCategories() {
    categories = MemoryCategory.values.map((category) {
      final count = memories.where((memory) => memory.category == category).length;
      return Tuple2(category, count);
    }).toList();
    notifyListeners();
  }

  Future<void> init() async {
    await loadMemories();
  }

  Future<void> loadMemories() async {
    _loading = true;
    notifyListeners();

    _memories = await getMemories();
    _unreviewed = _memories
      .where((memory) => !memory.reviewed && memory.createdAt.isAfter(DateTime.now().subtract(const Duration(days: 1))))
      .toList();

    _loading = false;
    _setCategories();
  }

  void deleteMemory(Memory memory) async {
    await deleteMemoryServer(memory.id);
    _memories.remove(memory);
    _unreviewed.remove(memory);
    _setCategories();
  }

  void deleteAllMemories() async {
    await deleteAllMemoriesServer();
    _memories.clear();
    _unreviewed.clear();
    _setCategories();
  }

  void createMemory(String content, [MemoryVisibility visibility = MemoryVisibility.public, MemoryCategory category = MemoryCategory.core]) async {
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

    await createMemoryServer(content, visibility.name);
    _memories.add(newMemory);
    _unreviewed.add(newMemory);
    _setCategories();
  }

  void updateMemoryVisibility(Memory memory, MemoryVisibility visibility) async {
    await updateMemoryVisibilityServer(memory.id, visibility.name);

    final idx = _memories.indexWhere((m) => m.id == memory.id);
    if (idx != -1) {
      memory.visibility = visibility;
      _memories[idx] = memory;
      _unreviewed.remove(memory);
      _setCategories();
    }
  }

  void editMemory(Memory memory, String value, [MemoryCategory? category]) async {
    await editMemoryServer(memory.id, value);

    final idx = _memories.indexWhere((m) => m.id == memory.id);
    if (idx != -1) {
      memory.content = value;
      if (category != null) {
        memory.category = category;
      }
      memory.updatedAt = DateTime.now();
      memory.edited = true;
      _memories[idx] = memory;

      // Remove from unreviewed if it was there
      final unreviewedIdx = _unreviewed.indexWhere((m) => m.id == memory.id);
      if (unreviewedIdx != -1) {
        _unreviewed.removeAt(unreviewedIdx);
      }

      _setCategories();
    }
  }

  void reviewMemory(Memory memory, bool approved) async {
    await reviewMemoryServer(memory.id, approved);

    final idx = _memories.indexWhere((m) => m.id == memory.id);
    if (idx != -1) {
      memory.reviewed = true;
      memory.userReview = approved;

      if (!approved) {
        memory.deleted = true;
        _memories.removeAt(idx);
        _unreviewed.remove(memory);
        // Don't call deleteMemory again because it would be a duplicate deletion
      } else {
        _memories[idx] = memory;

        // Remove from unreviewed list
        final unreviewedIdx = _unreviewed.indexWhere((m) => m.id == memory.id);
        if (unreviewedIdx != -1) {
          _unreviewed.removeAt(unreviewedIdx);
        }
      }

      _setCategories();
    }
  }
}
