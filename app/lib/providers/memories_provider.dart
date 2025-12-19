import 'dart:async';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/constants.dart';
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
  bool _excludeInteresting = false;
  List<Tuple2<MemoryCategory, int>> categories = [];
  MemoryCategory? selectedCategory;

  List<Memory> get memories => _memories;
  List<Memory> get unreviewed => _unreviewed;
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

  void setCategoryFilter(MemoryCategory? category) {
    _categoryFilter = category;
    _excludeInteresting = false; // Reset exclude filter when setting a category filter
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

    if (DevConstants.useMockData) {
      _memories = _generateMockMemories();
    } else {
      _memories = await getMemories();
    }

    _unreviewed = _memories
        .where(
            (memory) => !memory.reviewed && memory.createdAt.isAfter(DateTime.now().subtract(const Duration(days: 1))))
        .toList();

    _loading = false;
    _setCategories();
  }

  List<Memory> _generateMockMemories() {
    const uuid = Uuid();
    const mockUid = 'mock-user-123';

    return [
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Flutter is a cross-platform framework developed by Google for building mobile, web, and desktop applications.',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(hours: 1)),
        updatedAt: DateTime.now().subtract(const Duration(hours: 1)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Remembered to buy groceries: milk, eggs, bread, and coffee for the week.',
        category: MemoryCategory.manual,
        createdAt: DateTime.now().subtract(const Duration(hours: 3)),
        updatedAt: DateTime.now().subtract(const Duration(hours: 3)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Team meeting scheduled for next Monday at 10 AM to discuss Q4 objectives.',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(days: 1)),
        updatedAt: DateTime.now().subtract(const Duration(days: 1)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Favorite programming quote: "Code is like humor. When you have to explain it, it\'s bad."',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(days: 1, hours: 5)),
        updatedAt: DateTime.now().subtract(const Duration(days: 1, hours: 5)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Learned about Provider state management in Flutter. It simplifies passing data through the widget tree.',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(days: 2)),
        updatedAt: DateTime.now().subtract(const Duration(days: 2)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Birthday reminder: Mom\'s birthday is on the 15th. Need to plan something special.',
        category: MemoryCategory.manual,
        createdAt: DateTime.now().subtract(const Duration(days: 2, hours: 12)),
        updatedAt: DateTime.now().subtract(const Duration(days: 2, hours: 12)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Great coffee shop recommendation: The Local Brew on Main Street. Amazing espresso!',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(days: 3)),
        updatedAt: DateTime.now().subtract(const Duration(days: 3)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Project deadline: Submit final report by Friday 5 PM. Need to finish sections 3 and 4.',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(days: 3, hours: 8)),
        updatedAt: DateTime.now().subtract(const Duration(days: 3, hours: 8)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Interesting fact: The first computer bug was an actual bug - a moth found in a computer in 1947.',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(days: 4)),
        updatedAt: DateTime.now().subtract(const Duration(days: 4)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Gym membership renewal due next month. Check for any new promotional rates.',
        category: MemoryCategory.manual,
        createdAt: DateTime.now().subtract(const Duration(days: 4, hours: 6)),
        updatedAt: DateTime.now().subtract(const Duration(days: 4, hours: 6)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Book recommendation from Sarah: "The Pragmatic Programmer" - must read for developers.',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(days: 5)),
        updatedAt: DateTime.now().subtract(const Duration(days: 5)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Dentist appointment scheduled for next Wednesday at 2 PM. Remember to floss beforehand!',
        category: MemoryCategory.manual,
        createdAt: DateTime.now().subtract(const Duration(days: 5, hours: 10)),
        updatedAt: DateTime.now().subtract(const Duration(days: 5, hours: 10)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'New feature idea: Add dark mode toggle to improve user experience in low-light environments.',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(days: 6)),
        updatedAt: DateTime.now().subtract(const Duration(days: 6)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Password for Netflix changed. New password saved in password manager.',
        category: MemoryCategory.system,
        createdAt: DateTime.now().subtract(const Duration(days: 6, hours: 4)),
        updatedAt: DateTime.now().subtract(const Duration(days: 6, hours: 4)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
      Memory(
        id: uuid.v4(),
        uid: mockUid,
        content: 'Vacation plans: Thinking about visiting Japan in spring to see the cherry blossoms.',
        category: MemoryCategory.interesting,
        createdAt: DateTime.now().subtract(const Duration(days: 7)),
        updatedAt: DateTime.now().subtract(const Duration(days: 7)),
        visibility: MemoryVisibility.private,
        reviewed: true,
      ),
    ];
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
    _unreviewed.remove(memory);
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
    if (!_lastDeletedMemory!.reviewed &&
        _lastDeletedMemory!.createdAt.isAfter(DateTime.now().subtract(const Duration(days: 1)))) {
      _unreviewed.add(_lastDeletedMemory!);
    }

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
    _unreviewed.clear();
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
        reviewed: false,
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
      _unreviewed.removeWhere((m) => m.id == memory.id);

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

        // Remove from unreviewed if it was there
        final unreviewedIdx = _unreviewed.indexWhere((m) => m.id == memory.id);
        if (unreviewedIdx != -1) {
          _unreviewed.removeAt(unreviewedIdx);
        }

        _setCategories();
      }
    }

    return success;
  }

  void reviewMemory(Memory memory, bool approved, String source) async {
    MixpanelManager().memoryReviewed(memory, approved, source);

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
