import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';

class MemoriesProvider extends BaseProvider {
  List<Memory> memories = [];
  List<Memory> filteredMemories = [];
  List<Tuple2<MemoryCategory, int>> categories = [];
  MemoryCategory? selectedCategory;
  String searchQuery = '';

  List<Memory> get unreviewed => memories
      .where((f) => !f.reviewed && f.createdAt.isAfter(DateTime.now().subtract(const Duration(days: 1))))
      .toList();

  void setCategory(MemoryCategory? category) {
    selectedCategory = category;
    _filterMemories();
    notifyListeners();
  }

  void setSearchQuery(String query) {
    searchQuery = query.toLowerCase();
    _filterMemories();
    notifyListeners();
  }

  void _filterMemories() {
    if (searchQuery.isNotEmpty) {
      filteredMemories =
          memories.where((memory) => memory.content.decodeString.toLowerCase().contains(searchQuery)).toList();
    } else {
      filteredMemories = memories;
    }
    filteredMemories.sort((a, b) => b.createdAt.compareTo(a.createdAt));
  }

  void _setCategories() {
    categories = MemoryCategory.values.map((category) {
      final count = memories.where((memory) => memory.category == category).length;
      return Tuple2(category, count);
    }).toList();
    _filterMemories();
    notifyListeners();
  }

  Future<void> init() async {
    await loadMemories();
  }

  Future loadMemories() async {
    loading = true;
    notifyListeners();
    memories = await getMemories();
    loading = false;
    _setCategories();
  }

  void deleteMemory(Memory memory) async {
    deleteMemoryServer(memory.id);
    memories.remove(memory);
    _setCategories();
    notifyListeners();
  }

  void deleteAllMemories() async {
    deleteAllMemoriesServer();
    memories.clear();
    filteredMemories.clear();
    _setCategories();
    notifyListeners();
  }

  void createMemory(String content, [MemoryVisibility visibility = MemoryVisibility.public]) async {
    createMemoryServer(content, visibility.name);
    memories.add(Memory(
      id: const Uuid().v4(),
      uid: SharedPreferencesUtil().uid,
      content: content,
      category: MemoryCategory.other,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
      manuallyAdded: true,
      edited: false,
      reviewed: false,
      userReview: null,
      conversationId: null,
      conversationCategory: null,
      deleted: false,
      visibility: visibility,
    ));
    _setCategories();
  }

  void updateMemoryVisibility(Memory memory, MemoryVisibility visibility) async {
    var idx = memories.indexWhere((f) => f.id == memory.id);
    updateMemoryVisibilityServer(memory.id, visibility.name);
    memory.visibility = visibility;
    memories[idx] = memory;
    _setCategories();
  }

  void editMemory(Memory memory, String value, [MemoryCategory? category]) async {
    var idx = memories.indexWhere((f) => f.id == memory.id);
    editMemoryServer(memory.id, value);
    memory.content = value;
    if (category != null) {
      memory.category = category;
    }
    memory.updatedAt = DateTime.now();
    memory.edited = true;
    memories[idx] = memory;
    _setCategories();
  }

  void reviewMemory(Memory memory, bool approved) async {
    var idx = memories.indexWhere((f) => f.id == memory.id);
    if (idx != -1) {
      memory.reviewed = true;
      memory.userReview = approved;
      if (!approved) {
        memory.deleted = true;
        memories.removeAt(idx);
        deleteMemory(memory);
      } else {
        memories[idx] = memory;
        reviewMemoryServer(memory.id, approved);
      }
      _setCategories();
      notifyListeners();
    }
  }
}
