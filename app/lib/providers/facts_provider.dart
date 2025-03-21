import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/backend/http/api/facts.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/fact.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';

class FactsProvider extends BaseProvider {
  List<Fact> facts = [];
  List<Fact> filteredFacts = [];
  List<Tuple2<FactCategory, int>> categories = [];
  FactCategory? selectedCategory;
  String searchQuery = '';

  List<Fact> get unreviewed =>
      facts.where((f) => !f.reviewed && f.createdAt.isAfter(DateTime.now().subtract(const Duration(days: 1)))).toList();

  void setCategory(FactCategory? category) {
    selectedCategory = category;
    _filterFacts();
    notifyListeners();
  }

  void setSearchQuery(String query) {
    searchQuery = query.toLowerCase();
    _filterFacts();
    notifyListeners();
  }

  void _filterFacts() {
    if (searchQuery.isNotEmpty) {
      filteredFacts = facts.where((fact) => fact.content.decodeString.toLowerCase().contains(searchQuery)).toList();
    } else {
      filteredFacts = facts;
    }
    filteredFacts.sort((a, b) => b.createdAt.compareTo(a.createdAt));
  }

  void _setCategories() {
    categories = FactCategory.values.map((category) {
      final count = facts.where((fact) => fact.category == category).length;
      return Tuple2(category, count);
    }).toList();
    _filterFacts();
    notifyListeners();
  }

  Future<void> init() async {
    await loadFacts();
  }

  Future loadFacts() async {
    loading = true;
    notifyListeners();
    facts = await getFacts();
    loading = false;
    _setCategories();
  }

  void deleteFact(Fact fact) async {
    deleteFactServer(fact.id);
    facts.remove(fact);
    _setCategories();
    notifyListeners();
  }

  void deleteAllFacts() async {
    deleteAllFactServer();
    facts.clear();
    filteredFacts.clear();
    _setCategories();
    notifyListeners();
  }

  void createFact(String content, [FactVisibility visibility = FactVisibility.public]) async {
    createFactServer(content, visibility.name);
    facts.add(Fact(
      id: const Uuid().v4(),
      uid: SharedPreferencesUtil().uid,
      content: content,
      category: FactCategory.other,
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

  void updateFactVisibility(Fact fact, FactVisibility visibility) async {
    var idx = facts.indexWhere((f) => f.id == fact.id);
    updateFactVisibilityServer(fact.id, visibility.name);
    fact.visibility = visibility;
    facts[idx] = fact;
    _setCategories();
  }

  void editFact(Fact fact, String value, [FactCategory? category]) async {
    var idx = facts.indexWhere((f) => f.id == fact.id);
    editFactServer(fact.id, value);
    fact.content = value;
    if (category != null) {
      fact.category = category;
    }
    fact.updatedAt = DateTime.now();
    fact.edited = true;
    facts[idx] = fact;
    _setCategories();
  }

  void reviewFact(Fact fact, bool approved) async {
    var idx = facts.indexWhere((f) => f.id == fact.id);
    if (idx != -1) {
      fact.reviewed = true;
      fact.userReview = approved;
      if (!approved) {
        fact.deleted = true;
        facts.removeAt(idx);
        deleteFact(fact);
      } else {
        facts[idx] = fact;
        reviewFactServer(fact.id, approved);
      }
      _setCategories();
      notifyListeners();
    }
  }
}
